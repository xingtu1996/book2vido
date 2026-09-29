"""Book2Vido GUI —— 本地 Web 界面入口。

Architecture:
  - Python ThreadingHTTPServer (stdlib, zero deps)
  - Single-page HTML frontend (index.html)
  - Background threads run pipeline / install, frontend polls status

Start:
  python -m book2vido.gui        # default port 8765
  python -m book2vido.gui --port 9000
"""
from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from book2vido import outline as outline_mod
from book2vido.paths import project_root

# 共享状态下沉到 gui/state.py：handlers/env.py 与 handlers/tasks.py 也要用，
# 而它们不能 import server（server 会 import handlers → 成环）。
from book2vido.gui.state import GUI_DIR, _install_jobs, _install_lock  # noqa: F401

CONFIG_PATH = str(project_root() / "config.yaml")
_current_doc = {"path": "", "text": ""}  # 当前上传文档，供 chat 用


def _images_manifest() -> list:
    """读取 uploads/manifest.json（用户上传图片清单）。缺失/损坏返回空列表。"""
    p = project_root() / "uploads" / "manifest.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _add_image(name: str, path: str) -> None:
    """把一张上传图片登记进 manifest（供渲染时作铺底素材）。"""
    p = project_root() / "uploads" / "manifest.json"
    data = _images_manifest()
    data.append({"name": name, "path": str(path)})
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif")


# ── Environment checks ──


# ── Handlers (split into modules) ──
from book2vido.gui.handlers.env import (
    _check_env, _run_install
)
from book2vido.gui.handlers.tasks import _run_pipeline, _jobs, _job_lock

class GuiHandler(BaseHTTPRequestHandler):
    """Single-page GUI + API."""

    def _json(self, data: dict, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def _file(self, path: Path, content_type: str):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(path.read_bytes())

    def log_message(self, *args):
        pass

    # ── GET ──
    def do_GET(self):
        try:
            self._do_GET_inner()
        except Exception as e:
            import traceback
            import sys
            traceback.print_exc(file=sys.stderr)
            try:
                self._json({"ok": False, "error": str(e)}, 500)
            except Exception:
                pass

    def _do_GET_inner(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # Home
        if path == "/" or path == "/index.html":
            self._file(GUI_DIR / "index.html", "text/html; charset=utf-8")
            return

        # Static assets
        if path == "/style.css":
            self._file(GUI_DIR / "style.css", "text/css; charset=utf-8")
            return
        if path == "/app.js":
            self._file(GUI_DIR / "app.js", "application/javascript; charset=utf-8")
            return

        # Environment check (full dashboard version)
        if path == "/api/check-env":
            self._json(_check_env())
            return

        # Uploaded background images (铺底素材清单)
        if path == "/api/images":
            self._json({"ok": True, "images": _images_manifest()})
            return

        # Chapter outline
        if path == "/api/outline":
            qs = parse_qs(parsed.query)
            fpath = qs.get("path", [""])[0]
            if not fpath or not Path(fpath).exists():
                self._json({"ok": False, "error": "File not found"})
                return
            try:
                doc = outline_mod.build(fpath)
                chapters = []
                for i, ch in enumerate(doc.chapters):
                    chapters.append({
                        "index": i,
                        "title": ch.title,
                        "pages": f"p{ch.start_page}-p{ch.end_page}" if ch.start_page else "",
                        "start_page": ch.start_page,
                        "end_page": ch.end_page,
                    })
                self._json({"ok": True, "chapters": chapters})
            except Exception:
                self._json({"ok": True, "chapters": [{
                    "index": 0,
                    "title": Path(fpath).stem,
                    "pages": "",
                    "start_page": 0,
                    "end_page": 0,
                }]})
            return

        # Job status
        if path == "/api/status":
            qs = parse_qs(parsed.query)
            job_id = qs.get("job_id", [""])[0]
            with _job_lock:
                job = _jobs.get(job_id, {})
            self._json({
                "progress": job.get("progress", 0),
                "message": job.get("message", ""),
                "step": job.get("step", 0),
                "total_steps": 6,
                "elapsed": job.get("elapsed", 0),
                "eta": job.get("eta", 0),
                "logs": job.get("logs", [])[-30:],
                "done": job.get("done", False),
                "results": job.get("results", []),
            })
            return

        # Install status
        if path == "/api/install-status":
            qs = parse_qs(parsed.query)
            install_id = qs.get("install_id", [""])[0]
            with _install_lock:
                job = _install_jobs.get(install_id, {})
            self._json({
                "progress": job.get("progress", 0),
                "message": job.get("message", ""),
                "logs": job.get("logs", [])[-30:],
                "done": job.get("done", False),
                "error": job.get("error", None),
            })
            return

        # Voice list
        if path == "/api/voices":
            voices = []
            # 在线音色
            online_dir = GUI_DIR / "voices" / "online"
            if online_dir.exists():
                for f in sorted(online_dir.glob("*.mp3")):
                    voices.append({
                        "name": f.stem,
                        "url": f"/api/voices/online/{f.name}",
                        "type": "online",
                    })
            # 离线音色
            local_dir = GUI_DIR / "voices" / "local"
            if local_dir.exists():
                for f in sorted(local_dir.glob("*.mp3")):
                    voices.append({
                        "name": f.stem,
                        "url": f"/api/voices/local/{f.name}",
                        "type": "local",
                    })
            self._json({"voices": voices})
            return

        # Voice audio file
        if path.startswith("/api/voices/"):
            from urllib.parse import unquote
            vpath_str = unquote(path.split("/api/voices/", 1)[1])
            vpath = GUI_DIR / "voices" / vpath_str
            if vpath.exists():
                self.send_response(200)
                self.send_header("Content-Type", "audio/mpeg")
                self.end_headers()
                self.wfile.write(vpath.read_bytes())
            else:
                self._json({"error": "not found"}, 404)
            return

        # Video history
        if path == "/api/history":
            out_dir = Path.home() / "Movies" / "Book2Vido"
            videos = []
            if out_dir.exists():
                for v in sorted(out_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True):
                    # 用 ffprobe 取时长
                    import subprocess
                    try:
                        r = subprocess.run(
                            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(v)],
                            capture_output=True, text=True, timeout=5
                        )
                        import json as _json
                        dur = float(_json.loads(r.stdout)["format"]["duration"])
                    except Exception:
                        dur = 0
                    videos.append({
                        "name": v.stem,
                        "file": v.name,
                        "duration": round(dur, 1),
                        "size_kb": round(v.stat().st_size / 1024),
                        "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(v.stat().st_mtime)),
                        "url": f"/api/video/{v.name}",
                    })
            self._json({"videos": videos})
            return

        # Open output folder in Finder
        if path == "/api/open-folder":
            import subprocess
            out_dir = Path.home() / "Movies" / "Book2Vido"
            out_dir.mkdir(exist_ok=True)
            subprocess.Popen(["open", str(out_dir)])
            self._json({"ok": True})
            return

        # Video stream
        if path.startswith("/api/video/"):
            fname = path.split("/api/video/", 1)[1]
            vpath = Path.home() / "Movies" / "Book2Vido" / fname
            if not vpath.exists():
                self._json({"error": "not found"}, 404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(vpath.stat().st_size))
            self.end_headers()
            self.wfile.write(vpath.read_bytes())
            return

        self._json({"error": "not found"}, 404)

    # ── POST ──
    def do_POST(self):
        try:
            self._do_POST_inner()
        except Exception as e:
            import traceback
            import sys
            traceback.print_exc(file=sys.stderr)
            try:
                self._json({"ok": False, "error": str(e)}, 500)
            except Exception:
                pass

    def _do_POST_inner(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # Upload file
        if path == "/api/upload":
            length = int(self.headers.get("Content-Length", 0))
            upload_dir = project_root() / "uploads"
            upload_dir.mkdir(exist_ok=True)
            
            # 零依赖 multipart 解析（Python 3.13 已移除 cgi 模块）
            content_type = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in content_type:
                self._json({"ok": False, "error": "Expected multipart"})
                return
            
            # 提取 boundary
            boundary = content_type.split("boundary=")[1].strip('"')
            body = self.rfile.read(length)
            
            # 解析 multipart
            boundary_bytes = b"--" + boundary.encode()
            parts = body.split(boundary_bytes)
            
            fname = None
            file_data = None
            
            for part in parts:
                if b"Content-Disposition" not in part:
                    continue
                # 提取 filename
                if b'filename="' in part:
                    fname_start = part.index(b'filename="') + 10
                    fname_end = part.index(b'"', fname_start)
                    fname = part[fname_start:fname_end].decode("utf-8", errors="replace")
                    # 提取文件内容（跳过 headers 后面的空行）
                    header_end = part.find(b"\r\n\r\n")
                    if header_end > 0:
                        file_data = part[header_end+4:-2]  # 去掉末尾的 \r\n
            
            if not fname or not file_data:
                self._json({"ok": False, "error": "No file found"})
                return
            
            save_path = upload_dir / fname
            with open(save_path, "wb") as f:
                f.write(file_data)

            # 图片类：登记为可铺底素材，不做文本抽取（chat 用的 _current_doc 保持空）
            if fname.lower().endswith(IMG_EXTS):
                _add_image(fname, str(save_path))
                self._json({"ok": True, "path": str(save_path), "name": fname,
                            "type": "image",
                            "message": "已加入背景图素材，生成时自动铺底"})
                return

            # 提取全文存到全局，供 chat 用
            chapters = []
            try:
                from ..extractor import extract as _extract
                _current_doc["path"] = str(save_path)
                _current_doc["text"] = _extract(str(save_path))[:30000]  # 截前3万字，够 qwen3:8b 上下文
                
                # 提取目录（简单按 ## 或 # 标题提取）
                for line in _current_doc["text"].split("\n"):
                    line = line.strip()
                    if line.startswith("# ") or line.startswith("## "):
                        title = line.lstrip("# ").strip()
                        if title and len(title) < 50:
                            chapters.append({"title": title})
            except Exception as e:
                print(f"[warn] extract doc text failed: {e}")
            
            self._json({
                "ok": True, 
                "path": str(save_path), 
                "name": fname,
                "chapters": chapters
            })
            return


        # Chat with local model about current doc
        if path == "/api/chat":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            question = body.get("message", "")
            if not question:
                self._json({"ok": False, "error": "No question"})
                return
            if not _current_doc["text"]:
                self._json({"ok": False, "error": "请先上传一个文档"})
                return

            # 调 Ollama 流式
            import urllib.request
            prompt = """你是一个读书助手。根据下面这本书的内容，简洁地回答用户的问题。
如果书中没有相关信息，就说"这本书里没提到"。回答控制在200字以内。

=== 书的内容（节选）===
""" + _current_doc["text"][:20000] + """
=== 内容结束 ===

用户问题：""" + question + """

回答："""
            try:
                t_start = time.time()
                payload = {"model": "qwen3:8b", "prompt": prompt, "stream": True, "think": False}
                req = urllib.request.Request(
                    "http://localhost:11434/api/generate",
                    data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"},
                )
                
                # 流式响应头
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                
                # 读 Ollama 流式响应，逐行转发
                resp = urllib.request.urlopen(req, timeout=120)
                done_info = None
                
                for line in resp:
                    line = line.decode().strip()
                    if not line:
                        continue
                    chunk = json.loads(line)
                    
                    # 转发内容块
                    if "response" in chunk:
                        self.wfile.write(("data: " + json.dumps({"type": "content", "text": chunk["response"]}) + "\n\n").encode())
                    
                    # 完成时保存指标
                    if chunk.get("done"):
                        done_info = chunk
                
                # 最后发送性能指标
                if done_info:
                    eval_count = done_info.get("eval_count", 0)
                    eval_duration = done_info.get("eval_duration", 0) / 1e9
                    prompt_eval_count = done_info.get("prompt_eval_count", 0)
                    load_duration = done_info.get("load_duration", 0) / 1e9
                    total_time = time.time() - t_start
                    tps = round(eval_count / eval_duration, 1) if eval_duration > 0 else 0
                    
                    metrics = {
                        "type": "metrics",
                        "tps": tps,
                        "tokens": eval_count,
                        "prompt_tokens": prompt_eval_count,
                        "load_time": round(load_duration, 2),
                        "total_time": round(total_time, 2),
                    }
                    self.wfile.write(("data: " + json.dumps(metrics) + "\n\n").encode())
                
                # 结束
                self.wfile.write(("data: " + json.dumps({"type": "done"}) + "\n\n").encode())
                
            except Exception as e:
                err = {"type": "error", "message": str(e)}
                self.wfile.write(("data: " + json.dumps(err) + "\n\n").encode())
            return

        # Run pipeline
        if path == "/api/run":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            fpath = body.get("path", "")
            chapters = body.get("chapters", [])
            voice = body.get("voice", None)
            if not fpath or not Path(fpath).exists():
                self._json({"ok": False, "error": "File not found"})
                return

            job_id = f"job_{int(time.time())}"
            with _job_lock:
                _jobs[job_id] = {
                    "progress": 0, "message": "Queued...", "logs": [],
                    "done": False, "results": [],
                }

            t = threading.Thread(
                target=_run_pipeline,
                args=(job_id, fpath, chapters, voice),
                daemon=True,
            )
            t.start()
            self._json({"ok": True, "job_id": job_id})
            return

        # Trigger install
        if path.startswith("/api/install/"):
            component = path.split("/api/install/", 1)[1]
            if component not in ("ollama", "model", "ffmpeg"):
                self._json({"ok": False, "error": "Unknown component"})
                return

            install_id = f"inst_{int(time.time())}"
            with _install_lock:
                _install_jobs[install_id] = {
                    "progress": 0, "message": "Starting...", "logs": [],
                    "done": False,
                }

            t = threading.Thread(
                target=_run_install,
                args=(component, install_id),
                daemon=True,
            )
            t.start()
            self._json({"ok": True, "install_id": install_id})
            return

        self._json({"error": "not found"}, 404)


def start_server(port: int = 8765, open_browser: bool = True):
    """Start the GUI server.

    自动探测空闲端口：从 `port` 起顺延尝试（最多 20 个），避免与本机已占用端口冲突。
    此前写死 8765 且用 `pkill -9 -f book2vido.gui` 兜底——但 8765 常被其他常驻服务
    （如行途工作台）占用，pkill 杀不掉占用者，第二次 bind 仍失败。改为客户端式探测，
    谁占着就让位，互不误杀。
    """
    actual_port = None
    for candidate in range(port, port + 20):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", candidate))
            actual_port = candidate
            break
        except OSError:
            pass
        finally:
            probe.close()
    if actual_port is None:
        actual_port = port  # 探测全失败（极端情况），回退原端口由其自行报错

    server = ThreadingHTTPServer(("127.0.0.1", actual_port), GuiHandler)
    url = f"http://127.0.0.1:{actual_port}"
    print(f"Book2Vido GUI running at {url}")

    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


def main():
    parser = argparse.ArgumentParser(description="Book2Vido GUI")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on")
    parser.add_argument("--no-browser", action="store_true", help="Don't auto-open browser")
    args = parser.parse_args()
    start_server(port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()

"""Background pipeline execution — job queue + run loop."""
from __future__ import annotations

import json
import time
import threading
from pathlib import Path

from book2vido.config import load
# GUI_DIR 在 gui/state.py（不在 server.py）—— 本模块被 server import，反向 import 会成环。
# 少了这一行，起子进程那步会抛 `NameError: name 'GUI_DIR' is not defined`。
from book2vido.gui.state import GUI_DIR
from book2vido.paths import project_root

CONFIG_PATH = str(project_root() / "config.yaml")

# ── Job state (single-queue) ──
_jobs: dict = {}
_job_lock = threading.Lock()

# ── 每步预计耗时（秒），基于实测经验 ──
STEP_ETA = {
    1: 2,      # Loading config
    2: 3,      # Parsing input file
    3: 60,     # LLM generating script (最慢，qwen3:8b)
    4: 20,     # TTS voiceover
    5: 15,     # FFmpeg render
    6: 1,      # Finished
}
STEP_LABEL = {
    1: "加载配置",
    2: "解析文件",
    3: "AI 生成文案",
    4: "配音合成",
    5: "渲染视频",
    6: "完成",
}


def _run_pipeline(job_id: str, input_path: str, chapter_indices: list, voice: str = None):
    """Background thread: run the video generation pipeline."""
    t_start = time.time()

    def log(msg: str, ltype: str = "info"):
        with _job_lock:
            _jobs[job_id]["logs"].append({"type": ltype, "text": msg})

    def set_progress(step: int, pct: float, msg: str = ""):
        elapsed = time.time() - t_start
        # 算剩余时间：当前步及之后步的预计耗时 - 已过时间
        remaining = sum(STEP_ETA.get(s, 10) for s in range(step, 7))
        with _job_lock:
            _jobs[job_id]["progress"] = pct
            _jobs[job_id]["message"] = msg or STEP_LABEL.get(step, "处理中")
            _jobs[job_id]["step"] = step
            _jobs[job_id]["elapsed"] = round(elapsed, 1)
            _jobs[job_id]["eta"] = max(0, round(remaining - elapsed, 0))

    out_dir = Path.home() / "Movies" / "Book2Vido"
    out_dir.mkdir(exist_ok=True)

    try:
        # Step 1/6: 初始化
        set_progress(1, 5, "第 1/6 步 · 加载配置")
        log(f"Input: {input_path}")
        log(f"Chapters: {chapter_indices}")

        cfg = load(CONFIG_PATH)

        # 用户上传的背景图（铺底素材）：从 uploads/manifest.json 取出，
        # 既写入内存 cfg（供非子进程路径），也通过环境变量交给子进程。
        manifest = project_root() / "uploads" / "manifest.json"
        bg_paths = []
        if manifest.exists():
            try:
                bg_paths = [m["path"] for m in json.loads(manifest.read_text(encoding="utf-8"))]
            except Exception:
                bg_paths = []
        if bg_paths:
            cfg["visual"]["bg_images"] = bg_paths

        if voice:
            # 映射界面名 → edge-tts voice ID
            voice_map = {
                "Xiaoyi_女声·活泼": "zh-CN-XiaoyiNeural",
                "Xiaoxiao_女声·温暖": "zh-CN-XiaoxiaoNeural",
                "Yunjian_男声·解说": "zh-CN-YunjianNeural",
                "Yunxi_男声·新闻": "zh-CN-YunxiNeural",
                "Yunxia_男声·少年": "zh-CN-YunxiaNeural",
                "Yunyang_男声·专业": "zh-CN-YunyangNeural",
                "mac_Tingting_女声·中文": "Tingting",
            }
            mapped = voice_map.get(voice, voice)
            if voice.startswith("mac_"):
                cfg["tts"]["provider"] = "say"
                cfg["tts"]["voice"] = voice.replace("mac_", "").split("_")[0]
            else:
                cfg["tts"]["provider"] = "edge"
                cfg["tts"]["voice"] = mapped
            log(f"配音: {cfg['tts']['provider']} / {cfg['tts']['voice']}")
        output_path = out_dir / (Path(input_path).stem + ".mp4")

        # Step 2/6: 解析输入文件
        set_progress(2, 15, "第 2/6 步 · 解析文档目录")
        log("Reading input file...")

        # Step 3/6: LLM 生成文案（最长的一步）
        set_progress(3, 30, "第 3/6 步 · AI 生成全书总览文案")
        log("Calling local model...")

        if len(chapter_indices) == 0 or chapter_indices == [0]:
            # 用子进程跑 pipeline，避免 GUI 后台线程的 Broken pipe 问题
            import subprocess
            import sys
            import os
            py = sys.executable
            env = dict(os.environ)
            env["PYTHONPATH"] = str(GUI_DIR.parent.parent)  # src/
            # 背景图铺底经环境变量交给子进程（子进程重新 load config，内存 cfg 不生效）
            env["BOOK2VIDO_BG_IMAGES"] = json.dumps(bg_paths)
            cmd = [
                py, "-c",
                f"""
import sys, json, os
sys.path.insert(0, '{str(GUI_DIR.parent.parent)}')
from book2vido import pipeline
bg = json.loads(os.environ.get("BOOK2VIDO_BG_IMAGES", "[]")) or None
r = pipeline.run('{input_path}', '{str(output_path)}', '{CONFIG_PATH}', think=None, bg_images=bg)
print(json.dumps({{'scenes': r['scenes'], 'seconds': r['seconds']}}))
"""
            ]
            log("Starting pipeline subprocess...")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env)
            if result.returncode != 0:
                log(f"Subprocess stderr: {result.stderr[-500:]}", "error")
                raise RuntimeError(f"Pipeline failed (exit {result.returncode})")
            # 解析结果
            import json
            r = json.loads(result.stdout.strip().split("\n")[-1])
            log(f"Done: {r['scenes']} scenes, {r['seconds']}s", "ok")
            with _job_lock:
                _jobs[job_id]["results"].append({
                    "out": str(output_path),
                    "title": Path(input_path).stem,
                    "scenes": r["scenes"],
                    "seconds": r["seconds"],
                    "size": f"{round(output_path.stat().st_size / 1024)} KB" if output_path.exists() else "-",
                    "url": f"/api/video/{output_path.name}",
                })
        else:
            pass

        # Step 6/6: 完成
        set_progress(6, 100, "第 6/6 步 · 完成")
    except Exception as e:
        log(f"Pipeline error: {e}", "error")
    finally:
        with _job_lock:
            _jobs[job_id]["done"] = True

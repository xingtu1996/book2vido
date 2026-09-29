#!/usr/bin/env python3
"""
macOS `say` 音色浏览器
=====================
一个零依赖（仅 Python 标准库）的本地 Web 界面，用来试听和选择
本机已安装的 macOS `say` 语音合成音色。

运行：
    python3 tts_voice_browser.py

然后浏览器打开：
    http://127.0.0.1:8765

关闭：在终端按 Ctrl+C。
"""

from __future__ import annotations

import http.server
import json
import os
import re
import subprocess
import tempfile
import urllib.parse
from pathlib import Path

PORT = 8765

# say -v ? 输出示例：
# Tingting              zh_CN    # 你好！我叫婷婷。
# Eddy (中文（中国大陆）)       zh_CN    # 你好！我叫Eddy。
SAY_VOICES_RE = re.compile(r"^(.*?)\s+([a-zA-Z]{2}_[A-Z0-9]{2,4})\s+#\s+(.*)$")


def list_voices() -> list[dict[str, str]]:
    """调用 `say -v ?` 解析出本机所有已安装音色。"""
    result = subprocess.run(
        ["say", "-v", "?"],
        capture_output=True,
        text=True,
        check=False,
    )
    voices: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        m = SAY_VOICES_RE.match(line)
        if not m:
            continue
        name = m.group(1).strip()
        lang = m.group(2).strip()
        sample = m.group(3).strip()
        if name and lang:
            voices.append({"name": name, "lang": lang, "sample": sample})
    return voices


def synthesize(text: str, voice: str) -> bytes:
    """用指定音色朗读文本，返回 WAV 字节。"""
    with tempfile.TemporaryDirectory() as tmp:
        txt_path = os.path.join(tmp, "input.txt")
        aiff_path = os.path.join(tmp, "out.aiff")
        wav_path = os.path.join(tmp, "out.wav")

        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(text)

        subprocess.run(
            ["say", "-v", voice, "-f", txt_path, "-o", aiff_path],
            check=True,
        )
        # 转成浏览器兼容性更好的 WAV
        subprocess.run(
            ["afconvert", aiff_path, wav_path, "-f", "WAVE", "-d", "LEI16@44100"],
            check=True,
        )

        with open(wav_path, "rb") as f:
            return f.read()


HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>macOS say 音色浏览器</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 760px; margin: 40px auto; padding: 0 20px; background: #f7f8fa; color: #111; }
  h1 { font-size: 26px; margin-bottom: 6px; }
  .hint { color: #666; font-size: 14px; margin-bottom: 22px; }
  label { display: block; margin: 16px 0 6px; font-weight: 600; font-size: 14px; }
  select, textarea, button, input { width: 100%; box-sizing: border-box; padding: 10px; border: 1px solid #c5c5c7; border-radius: 6px; font-size: 15px; }
  textarea { min-height: 90px; resize: vertical; }
  .row { display: flex; gap: 12px; align-items: flex-end; }
  .row > * { flex: 1; }
  .row input { max-width: 180px; flex: 0 0 180px; }
  button { background: #056DE8; color: #fff; border: none; cursor: pointer; font-weight: 600; }
  button:hover { background: #0558bd; }
  button:disabled { opacity: .6; cursor: not-allowed; }
  .actions { display: flex; gap: 10px; margin-top: 14px; }
  .actions a { flex: 1; text-decoration: none; }
  .actions button { width: 100%; }
  audio { width: 100%; margin-top: 18px; }
  #status { margin-top: 12px; font-size: 13px; color: #666; }
  .error { color: #c41; }
  .success { color: #1a6; }
  .muted { color: #888; font-size: 13px; }
  code { background: #eef; padding: 1px 4px; border-radius: 4px; font-size: 13px; }
</style>
</head>
<body>
<h1>macOS say 音色浏览器</h1>
<p class="hint">本机已安装的 <code>say</code> 音色试听。选一个音色、输入文字，点击试听即可生成 WAV。<span id="count" class="muted"></span></p>

<label for="voice">音色</label>
<div class="row">
  <select id="voice"></select>
  <input id="filter" type="text" placeholder="筛选：zh_CN / 中文 / Tingting" autocomplete="off">
</div>

<label for="text">朗读文本</label>
<textarea id="text">你好，我叫婷婷，这是本地 macOS 音色。</textarea>

<div class="actions">
  <button id="playBtn">试听</button>
  <a id="download" download="tts.wav"><button type="button">下载音频</button></a>
</div>

<audio id="player" controls style="display:none;"></audio>
<p id="status"></p>

<script>
const voiceSel = document.getElementById('voice');
const filterIn = document.getElementById('filter');
const textIn = document.getElementById('text');
const playBtn = document.getElementById('playBtn');
const player = document.getElementById('player');
const statusEl = document.getElementById('status');
const countEl = document.getElementById('count');
const downloadEl = document.getElementById('download');

let allVoices = [];

function escapeHtml(s) {
  return s.replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
}

async function loadVoices() {
  statusEl.textContent = '加载音色列表…';
  try {
    const res = await fetch('/voices');
    if (!res.ok) throw new Error(await res.text());
    allVoices = await res.json();
    countEl.textContent = ` 共 ${allVoices.length} 个`;
    renderVoices();
    statusEl.textContent = '';
  } catch (e) {
    statusEl.innerHTML = `<span class="error">加载失败：${e.message}</span>`;
  }
}

function renderVoices() {
  const f = filterIn.value.trim().toLowerCase();
  const voices = allVoices.filter(v => {
    if (!f) return true;
    return v.lang.toLowerCase().includes(f) ||
           v.name.toLowerCase().includes(f) ||
           v.sample.toLowerCase().includes(f);
  });
  voiceSel.innerHTML = voices.map(v =>
    `<option value="${escapeHtml(v.name)}">${escapeHtml(v.name)} — ${escapeHtml(v.lang)} — ${escapeHtml(v.sample)}</option>`
  ).join('');
  if (!voices.length) {
    voiceSel.innerHTML = '<option>无匹配音色</option>';
  }
}

filterIn.addEventListener('input', renderVoices);

playBtn.addEventListener('click', async () => {
  const voice = voiceSel.value;
  const text = textIn.value.trim();
  if (!voice || voice === '无匹配音色') { statusEl.textContent = '请先选择音色'; return; }
  if (!text) { statusEl.textContent = '请输入朗读文本'; return; }

  statusEl.textContent = '生成音频中…';
  playBtn.disabled = true;
  try {
    const url = `/speak?${new URLSearchParams({voice, text})}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(await res.text());
    const blob = await res.blob();
    const blobUrl = URL.createObjectURL(blob);
    player.src = blobUrl;
    player.style.display = 'block';
    player.play();
    downloadEl.href = blobUrl;
    downloadEl.download = `tts_${voice.replace(/\s+/g, '_')}_${Date.now()}.wav`;
    statusEl.innerHTML = '<span class="success">已生成，正在播放。</span>';
  } catch (e) {
    statusEl.innerHTML = `<span class="error">生成失败：${e.message}</span>`;
  } finally {
    playBtn.disabled = false;
  }
});

loadVoices();
</script>
</body>
</html>
"""


class RequestHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # 静默访问日志
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        if path == "/":
            self._send_html(HTML)
        elif path == "/voices":
            self._send_json(list_voices())
        elif path == "/speak":
            voice = params.get("voice", [""])[0]
            text = params.get("text", [""])[0]
            self._handle_speak(voice, text)
        else:
            self._send_error(404, "Not found")

    def _handle_speak(self, voice: str, text: str):
        if not voice or not text:
            self._send_error(400, "缺少 voice 或 text 参数")
            return

        allowed = {v["name"] for v in list_voices()}
        if voice not in allowed:
            self._send_error(400, f"未知音色：{voice}")
            return

        try:
            wav = synthesize(text, voice)
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(wav)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(wav)
        except subprocess.CalledProcessError as e:
            self._send_error(500, f"say/afconvert 执行失败：{e}")
        except Exception as e:
            self._send_error(500, str(e))

    def _send_html(self, content: str):
        data = content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_error(self, code: int, message: str):
        data = message.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    server = http.server.HTTPServer(("127.0.0.1", PORT), RequestHandler)
    print(f"启动 macOS say 音色浏览器：http://127.0.0.1:{PORT}")
    print("按 Ctrl+C 关闭。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n关闭服务器。")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

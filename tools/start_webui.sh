#!/usr/bin/env bash
# 行途 · 本地模型台 —— 一键启动（零依赖，只用 macOS 自带 python3 + ollama）
#
# 为什么不能双击 HTML 直接开？
#   file:// 页面的 Origin 是 null，Ollama 的 CORS 白名单不含 null → 浏览器拦请求。
#   必须从 http://localhost 起，才和 Ollama 的白名单（localhost 任意端口）对上。
#
# 本脚本只保证一件事：**要么真的把服务起起来，要么明确说清为什么没起来。**
#   曾经的写法是裸调 `ollama serve` 然后 sleep 4：
#     · Finder 双击 / 窄 PATH 下 `ollama` 不在 PATH 里 → 命令根本没执行；
#     · `(cmd &)` 的失败 `set -e` 抓不住（后台化本身是成功的）；
#     · 于是脚本一路走到底，开出一个「未连接」的页面，终端却全绿。
#   与 doc/17 §S-1 的 parents[2] 同族：**本机环境把它兜住了，所以永远测不出来**。
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
PORT="${1:-8123}"
URL="http://localhost:${PORT}/ollama_webui.html"

# ---- 二进制定位：不写死路径，也不依赖 PATH（Finder 启动时 PATH 极窄）----
# 与 src/book2vido/binpaths.py 的 _COMMON_DIRS 同源理念。
resolve_bin() {
  local name="$1"; shift
  local d
  for d in "$@"; do
    if [ -x "$d/$name" ]; then echo "$d/$name"; return 0; fi
  done
  if command -v "$name" >/dev/null 2>&1; then command -v "$name"; return 0; fi
  return 1
}

BIN_DIRS=(/opt/homebrew/bin /usr/local/bin /opt/local/bin "$HOME/.local/bin"
          /Applications/Ollama.app/Contents/Resources)

OLLAMA_BIN="$(resolve_bin ollama "${BIN_DIRS[@]}")" || OLLAMA_BIN=""
PY_BIN="$(resolve_bin python3 /opt/homebrew/bin /usr/local/bin /usr/bin)" || PY_BIN=""

# ---- 1/3 · Ollama 服务 ----
if curl -s --max-time 2 http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "[1/3] Ollama 已在运行"
elif [ -z "$OLLAMA_BIN" ]; then
  echo "[1/3] ✗ 找不到 ollama 可执行文件 —— 无法启动"
  echo "        装一个：brew install ollama（或 https://ollama.com/download 装 GUI 版）"
  echo "        装好后重跑本脚本；页面里的引导卡也会一直提示。"
else
  echo "[1/3] Ollama 未运行，正在启动 → $OLLAMA_BIN"
  (nohup "$OLLAMA_BIN" serve >/tmp/ollama.log 2>&1 &)
  for _ in 1 2 3 4 5 6 7 8 9 10; do          # 轮询而不是死等一个固定 sleep
    sleep 1
    curl -s --max-time 1 http://localhost:11434/api/tags >/dev/null 2>&1 && break
  done
  if curl -s --max-time 2 http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo "      ✓ 已就绪"
  else
    echo "      ✗ 启动失败（等了 10 秒仍无响应）。日志尾部："
    tail -5 /tmp/ollama.log 2>/dev/null | sed 's/^/        | /' || true
    echo "        页面仍会打开，并显示对应的引导。"
  fi
fi

# ---- 2/3 · Python 与端口 ----
if [ -z "$PY_BIN" ]; then
  echo "[2/3] ✗ 找不到 python3。执行 xcode-select --install，或 brew install python"
  exit 1
fi

if curl -s --max-time 2 -o /dev/null "$URL" 2>/dev/null; then
  echo "[2/3] 端口 ${PORT} 上已有本页在服务，直接打开"
  open "$URL"
  exit 0
fi
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "[2/3] ✗ 端口 ${PORT} 被别的程序占用，且那里不是本页（避免打开成别的东西）"
  echo "        换一个端口：bash tools/start_webui.sh 8124"
  exit 1
fi

# ---- 3/3 · 本地静态服务 ----
# 只绑回环：这个目录没有任何鉴权，不该对局域网开放（浏览器里也是访问 localhost）。
echo "[3/3] 起服务并打开浏览器 → $URL"
"$PY_BIN" -m http.server "$PORT" --bind 127.0.0.1 --directory "$DIR" >/dev/null 2>&1 &
SRV=$!
trap 'kill $SRV 2>/dev/null || true' EXIT INT TERM
sleep 1
open "$URL"

echo
echo "本地模型台运行中。按 Ctrl+C 关闭。"
wait $SRV

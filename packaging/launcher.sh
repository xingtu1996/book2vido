#!/bin/bash
# Book2Vido.app 主入口（.app/Contents/MacOS/Book2Vido）
#
# 两种用法：
#   · 双击图标           → 弹文件选择器（选完即开始；取消则看说明 + 打开输出目录）
#   · 把 PDF/MD/TXT 拖到图标上 → 逐个转成竖版短视频，完成后通知
#
# 设计原则：
#   1) 双击启动时 PATH 极窄（没有 /opt/homebrew/bin），所有依赖走随包 Resources/
#   2) 模型不随包分发，但**复用系统已有的 ~/.ollama/models**，不重复占 4.9GB
#   3) 任何失败都留可见痕迹（通知 + 日志），不静默
#   4) **面向非技术用户**：一拖就是 1–2 分钟静默期，必须让"卡住了吗"这个问题
#      一直被回答——按阶段发系统通知（见 stage_notify）。等待本身没问题，
#      "不知道还要等多久"才是问题。
set -uo pipefail

# ---------- 路径定位 ----------
MACOS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RES_DIR="$(cd "$MACOS_DIR/../Resources" && pwd)"
RUNTIME="$RES_DIR/runtime"
VENDOR="$RES_DIR/vendor"
APP_PY="$RES_DIR/app"
PY="$RUNTIME/bin/python3"

OUT_DIR="${BOOK2VIDO_OUT:-$HOME/Movies/Book2Vido}"
LOG_DIR="$HOME/Library/Logs/Book2Vido"
mkdir -p "$OUT_DIR" "$LOG_DIR" 2>/dev/null
LOG="$LOG_DIR/run-$(date +%Y%m%d).log"

# ---------- 环境隔离（关键：别让用户的 PATH 影响打包内运行时）----------
export BOOK2VIDO_VENDOR="$VENDOR"
export PYTHONPATH="$APP_PY"
export PATH="$RUNTIME/bin:$VENDOR:/usr/bin:/bin:/usr/sbin:/sbin"
# Ollama：与系统共享模型目录（不设 OLLAMA_MODELS 即默认 ~/.ollama/models）
OLLAMA_BIN="$VENDOR/ollama"
[ -x "$OLLAMA_BIN" ] || OLLAMA_BIN="$(command -v ollama 2>/dev/null || true)"
export OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}"

# ---------- 输出工具 ----------
log() { echo "[$(date +%H:%M:%S)] $*" >>"$LOG"; }

notify() {
  local title="$1" msg="$2" sub="${3:-}"
  osascript -e "display notification \"$msg\" with title \"$title\" subtitle \"$sub\"" >/dev/null 2>&1 || true
}

alert() {
  local msg="$1"
  osascript -e "display dialog \"$msg\" buttons {\"好\"} default button 1 with title \"文本转视频\" with icon note" >/dev/null 2>&1 || true
}

die() { alert "$1"; log "FATAL: $1"; exit 1; }

# ---------- 面向非技术用户的交互 ----------
# 文件选择器：非技术用户普遍不会"把文件拖到图标上"这一手，但都会"选文件"。
pick_files() {
  osascript <<'APPLESCRIPT' 2>/dev/null
set outText to ""
try
  set theFiles to choose file with prompt "选择要转成视频的书 / 文章（可多选）" with multiple selections allowed
  repeat with f in theFiles
    set outText to outText & (POSIX path of f) & linefeed
  end repeat
end try
return outText
APPLESCRIPT
}

# 阶段通知：把 pipeline 的打印串翻成"人话"，只在**阶段变化时**发一条，避免刷屏。
# 分镜那一步最慢（整篇 2500 字 / think=true 实测 **~50s 起**，冷启动更久），
# 所以专门说明"慢是正常的"——等待本身不是问题，"不知道还要等多久"才是。
#
# ⚠️ 时长口径（别凭感觉写）：本节全部数字来自本机实测，改文案前先重测。
#    整篇 2500 字 / think=true：冷启动 **146.9s**、热模型 **80.9s**（12 句成片）。
#    早先写的"约 1 分钟"低估了近一半，会让用户在最后 1 分钟以为程序卡死了。
STAGE=""
stage_notify() {
  local s=""
  case "$1" in
    *大纲*) s="正在解析目录" ;;
    *分镜*) s="正在生成口播稿（最慢一步，约 1 分钟，慢是正常的）" ;;
    *画面*) s="正在绘制信息卡" ;;
    *配音*) s="正在合成配音" ;;
    *合成*) s="正在拼接视频" ;;
    *) return 0 ;;
  esac
  [ "$s" = "$STAGE" ] && return 0
  STAGE="$s"
  notify "正在处理 ${CUR_NAME:-}" "$s" ""
}

# ---------- 依赖解析 ----------
ollama_alive() { curl -s --max-time 3 "http://$OLLAMA_HOST/api/tags" >/dev/null 2>&1; }

# ffmpeg 定位：内置 → 常见包管理器路径 → PATH。
# 注意：.app 双击时 PATH 不含 /opt/homebrew/bin，所以必须显式探这几个目录
# （Python 层 src/book2vido/binpaths.py 用同一套优先级，两处别写歪）
resolve_ffmpeg() {
  [ -x "$VENDOR/ffmpeg" ] && { echo "$VENDOR/ffmpeg"; return 0; }
  local c
  for c in /opt/homebrew/bin/ffmpeg /usr/local/bin/ffmpeg /opt/local/bin/ffmpeg; do
    [ -x "$c" ] && { echo "$c"; return 0; }
  done
  command -v ffmpeg 2>/dev/null || return 1
}

# ---------- 自检 ----------
selftest() {
  echo "Book2Vido 自检"
  echo "  app        : $RES_DIR"
  printf '  runtime    : %s' "$PY"
  [ -x "$PY" ] && echo "  ✓ $("$PY" -V 2>&1)" || echo "  ✗ 缺失"
  printf '  python 依赖: '
  "$PY" -c "import PIL, pypdf, yaml, edge_tts; print('✓ 全部可 import')" 2>/dev/null || echo "✗ 缺失"
  printf '  ollama     : %s' "${OLLAMA_BIN:-（无）}"
  [ -x "$OLLAMA_BIN" ] && echo "  ✓" || echo "  ✗"
  printf '  ollama 服务: '
  ollama_alive && echo "✓ 在跑" || echo "✗ 未运行（首次出片会自动拉起）"
  printf '  ffmpeg     : '
  local ff; ff="$(resolve_ffmpeg)" && echo "✓ $ff" || echo "✗ 未找到（需 brew install ffmpeg，或构建时注入 static build）"
  printf '  模型       : '
  "$OLLAMA_BIN" list 2>/dev/null | grep -q "${MODEL%%:*}" && echo "✓ $MODEL" || echo "✗ $MODEL（首次运行会下载）"
  printf '  图标缓存   : '
  [ -d "$RES_DIR/assets/icons" ] && echo "✓ $(ls "$RES_DIR/assets/icons"/*.png 2>/dev/null | wc -l | tr -d ' ') 个" || echo "（无，退化为纯色块）"
  echo "  输出目录   : $OUT_DIR"
  echo "  日志       : $LOG"
}

ensure_ollama() {
  ollama_alive && return 0
  [ -n "$OLLAMA_BIN" ] || die "找不到 Ollama 运行组件。安装包可能不完整，请重新下载。"
  log "启动 ollama serve（$OLLAMA_BIN）"
  nohup "$OLLAMA_BIN" serve >>"$LOG" 2>&1 &
  for _ in $(seq 1 20); do
    sleep 1
    ollama_alive && return 0
  done
  die "Ollama 启动失败，详见日志：$LOG"
}

ensure_ffmpeg() {
  resolve_ffmpeg >/dev/null && return 0
  # 技术话写日志，人话给用户。让非技术用户"去终端执行 brew install" = 让他放弃。
  log "缺 ffmpeg：作者侧修法 -> brew install ffmpeg，或用 BOOK2VIDO_FFMPEG_SRC 注入 static build 后重新打包（见 packaging/build_app.sh --check）"
  die "这个安装包不完整：缺少视频合成组件。\n\n请联系给你安装包的人，换一个完整版本再来一次。\n这一步不需要你懂命令行。\n\n日志：$LOG"
}

# 模型：没有则下载（首次约 4.9GB）
MODEL="${BOOK2VIDO_MODEL:-qwen3:8b}"
ensure_model() {
  if "$OLLAMA_BIN" list 2>/dev/null | grep -q "${MODEL%%:*}"; then return 0; fi
  log "模型 $MODEL 缺失，开始下载"
  notify "首次运行 · 需下载模型" "正在下载本地模型，约 4.9GB" "视网速 5–30 分钟，只需一次，期间可以正常用电脑"
  # caffeinate 防止下载到一半被系统睡眠打断（4.9GB 被中断要从头再来）
  if command -v caffeinate >/dev/null 2>&1; then
    "$OLLAMA_BIN" pull "$MODEL" 2>&1 | tee -a "$LOG" | caffeinate -i cat >/dev/null
    pull_rc=${PIPESTATUS[0]}
  else
    "$OLLAMA_BIN" pull "$MODEL" >>"$LOG" 2>&1; pull_rc=$?
  fi
  if [ "$pull_rc" -ne 0 ]; then
    die "模型下载失败（$MODEL）。\n\n可在终端手动执行：ollama pull $MODEL\n日志：$LOG"
  fi
  notify "模型就绪" "$MODEL 下载完成" ""
}

# ---------- 主流程 ----------
show_intro() {
  alert "把 PDF / Markdown / TXT 文件拖到本图标上，即可转成竖版短视频。\n\n结果保存在：\n$OUT_DIR\n\n全程本地运行，不联网、不上传、零费用。"
  open "$OUT_DIR" 2>/dev/null || true
}

main() {
  [ "${1:-}" = "--selftest" ] && { selftest; exit 0; }

  log "=== 启动，参数 $# 个，模型 $MODEL，输出 $OUT_DIR ==="

  # 双击（无参数）：先给文件选择器。取消 = 想看说明，走原来的路径。
  if [ "$#" -eq 0 ]; then
    local picked_line
    local -a picked=()
    while IFS= read -r picked_line; do
      [ -n "$picked_line" ] && picked+=("$picked_line")
    done <<< "$(pick_files)"
    if [ "${#picked[@]}" -eq 0 ]; then
      show_intro
      exit 0
    fi
    set -- "${picked[@]}"
    log "选择器返回 ${#picked[@]} 个文件"
  fi

  [ -x "$PY" ] || die "内置运行时缺失：$PY\n安装包可能不完整，请重新下载。"
  ensure_ollama
  ensure_ffmpeg
  ensure_model

  local ok=0 fail=0 last_out=""
  for f in "$@"; do
    [ -f "$f" ] || continue
    local stem out
    stem="$(basename "$f")"; stem="${stem%.*}"
    out="$OUT_DIR/${stem}.mp4"
    log "处理：$f → $out"
    CUR_NAME="$stem"
    STAGE=""
    # 时长按实测给区间，并且**明说"首次更慢"**：首次要加载 4.9GB 模型进内存，
    # 比热启动慢近一倍。给出上限比给出乐观值好——用户按最坏情况等，提前完成是惊喜。
    notify "已开始处理" "$stem" "预计 1.5–3 分钟（首次运行更慢），完成后会自动通知"
    # tee 到日志的同时逐行喂给 stage_notify —— 让 1–2 分钟的等待"看得见"。
    # pipefail 保证 python 的非零退出码仍能被 if 捕获（不被 while 的 0 盖掉）。
    if "$PY" -m book2vido run --input "$f" --out "$out" 2>&1 \
         | tee -a "$LOG" | while IFS= read -r line; do stage_notify "$line"; done; then
      ok=$((ok + 1)); last_out="$out"
    else
      fail=$((fail + 1)); log "失败：$f"
    fi
  done

  if [ "$ok" -gt 0 ]; then
    notify "出片完成" "$ok 个文件已生成" "$OUT_DIR"
    [ -n "$last_out" ] && open -R "$last_out" 2>/dev/null || open "$OUT_DIR" 2>/dev/null || true
  fi
  if [ "$fail" -gt 0 ]; then
    notify "部分失败" "$fail 个文件未能处理" "详见日志"
    alert "$fail 个文件处理失败。\n\n日志：$LOG"
  fi
  log "=== 结束：成功 $ok / 失败 $fail ==="
}

main "$@"

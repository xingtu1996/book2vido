#!/usr/bin/env bash
# book2vido 一键安装（macOS / Linux）
#
# 用法（在仓库根执行）：
#     bash scripts/install.sh                # 建 .venv 并装好，`book2vido` 命令可用
#     VENV_DIR=/tmp/b2v-venv bash scripts/install.sh
#     bash scripts/install.sh --no-venv      # 装进当前 python（不建 venv）
#
# 设计取舍：
#   · 缺 ffmpeg / ollama **不阻断退出码** —— 它们是「出片」的前置，不是「装包」的前置。
#     装包失败才该红；缺外部工具只打印可复制的补救命令（否则同事在 CI 里也被卡住）。
#   · 全程 `set -euo pipefail`，任何一步真失败都会立刻以非 0 退出，不会留下半成品 venv。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VENV_DIR="${VENV_DIR:-$ROOT/.venv}"
USE_VENV=1
for arg in "$@"; do
  case "$arg" in
    --no-venv) USE_VENV=0 ;;
    -h|--help) sed -n '2,12p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "🔴 未知参数：$arg（只支持 --no-venv）" >&2; exit 2 ;;
  esac
done

say()  { printf '%s\n' "$*"; }
step() { printf '\n\033[1m▶ %s\033[0m\n' "$*"; }
warn() { printf '\033[33m⚠  %s\033[0m\n' "$*"; }
die()  { printf '\033[31m🔴 %s\033[0m\n' "$*" >&2; exit 1; }

# ── 1. Python 版本 ────────────────────────────────────────────────
step "1/4 检查 Python 版本（需要 >= 3.10）"
PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || die "找不到 python3。macOS：brew install python@3.12 ｜ Linux：apt install python3-venv"
PY_VERSION="$("$PY" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')"
PY_OK="$("$PY" -c 'import sys; print(1 if sys.version_info >= (3, 10) else 0)')"
say "    python3 = $PY_VERSION（$("$PY" -c 'import sys; print(sys.executable)')）"
[ "$PY_OK" = "1" ] || die "Python 版本过低（$PY_VERSION）。本项目 requires-python >= 3.10"

# ── 2. venv ───────────────────────────────────────────────────────
if [ "$USE_VENV" = "1" ]; then
  step "2/4 建虚拟环境 → $VENV_DIR"
  if [ ! -x "$VENV_DIR/bin/python" ]; then
    "$PY" -m venv "$VENV_DIR" || die "创建 venv 失败。Linux 可能需要：apt install python3-venv"
  fi
  PY="$VENV_DIR/bin/python"
else
  step "2/4 跳过 venv（--no-venv），直接装进 $PY"
fi

# ── 3. 装包（可编辑安装 + dev 依赖）─────────────────────────────────
step "3/4 安装包：pip install -e .[dev]"
"$PY" -m pip install --upgrade pip -q
"$PY" -m pip install -e ".[dev]" || die "pip install 失败（见上方 pip 输出）"

# 装完立刻自检：**命令在不在** 与 **gui 子包在不在**（后者曾被 packages 写死漏掉过）
"$PY" -c "import book2vido, book2vido.gui, book2vido.cli" \
  || die "包装上了但 import 失败（book2vido.gui / book2vido.cli 缺失？）"
BIN="$VENV_DIR/bin/book2vido"
[ "$USE_VENV" = "0" ] && BIN="$(command -v book2vido || echo book2vido)"
say "    ✅ 已装好：$BIN"

# ── 4. 外部工具体检（缺失只警告，给出补救命令）────────────────────────
step "4/4 外部依赖体检"

if command -v ffmpeg >/dev/null 2>&1; then
  say "    ✅ ffmpeg：$(command -v ffmpeg)"
else
  warn "未找到 ffmpeg —— 合成环节会失败（出片必需）"
  say "       macOS：  brew install ffmpeg"
  say "       Linux：  sudo apt install ffmpeg"
  say "       （装完可用 BOOK2VIDO_FFMPEG=/path/to/ffmpeg 强制指定）"
fi

if command -v ollama >/dev/null 2>&1; then
  say "    ✅ ollama：$(command -v ollama)"
  if curl -fsS -m 3 http://localhost:11434/api/tags >/dev/null 2>&1; then
    say "    ✅ ollama 服务在跑（localhost:11434）"
  else
    warn "ollama 装了但服务没起 —— 分镜会降级为 rule（不出错，但句子质量下降）"
    say "       启动：  ollama serve &"
  fi
else
  warn "未找到 ollama —— 分镜自动降级为 rule 规则版（能出片，句子质量下降；不是故障）"
  say "       macOS：  brew install ollama   然后 ollama pull qwen3:8b"
  say "       Linux：  curl -fsSL https://ollama.com/install.sh | sh"
fi

command -v rsvg-convert >/dev/null 2>&1 \
  && say "    ✅ rsvg-convert：$(command -v rsvg-convert)" \
  || { warn "未找到 rsvg-convert —— 图标层自动降级为「关键词首字大字」版式（不影响出片）";
       say "       macOS：  brew install librsvg"; }

# ── 收尾：把「下一步该敲什么」直接打出来 ──────────────────────────────
cat <<EOF

$(printf '\033[1m✅ 安装完成\033[0m')

接下来（venv 模式请先激活，或直接用下面的全路径命令）：
    source $VENV_DIR/bin/activate
    book2vido --help
    book2vido run --input samples/产品自述_book2vido_20260916.md --out /tmp/book2vido_fresh.mp4

不开 venv 也能跑：
    $VENV_DIR/bin/book2vido run --input samples/产品自述_book2vido_20260916.md --out /tmp/book2vido_fresh.mp4
EOF

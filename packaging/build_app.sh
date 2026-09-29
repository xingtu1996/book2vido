#!/bin/bash
# Book2Vido.app 构建脚本（macOS / Apple Silicon）
#
# 产物：dist/Book2Vido.app —— 自带 Python 运行时 + 依赖 + Ollama 二进制 + 代码 + 图标缓存
# 不含：qwen3:8b 模型（4.9GB，首次运行自动下载，且复用系统已有 ~/.ollama/models）
#
# .app 内部布局（config.yaml / assets 依赖 __file__ 回溯到 Resources/，勿随意挪动）：
#   Contents/
#     Info.plist
#     MacOS/Book2Vido            ← launcher.sh
#     Resources/
#       runtime/                 ← python-build-standalone（sys.prefix）
#       vendor/                  ← ollama / ffmpeg（可选）/ rsvg-convert（可选）
#       app/book2vido/           ← 源码
#       config.yaml              ← parents[2]/config.yaml
#       prompts/                 ← parents[2]/prompts/（分镜提示词资产，T2V-007）
#       assets/icons/            ← 图标缓存
#
# 用法：
#   bash packaging/build_app.sh            # 构建
#   bash packaging/build_app.sh --check    # 只做自检不做构建
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 源：可由环境变量覆盖，便于在别的机器上构建
PY_SRC="${BOOK2VIDO_PY_SRC:-$HOME/.workbuddy/binaries/python/versions/3.13.12}"
OLLAMA_SRC="${BOOK2VIDO_OLLAMA_SRC:-$(ls -d /opt/homebrew/Cellar/ollama/*/libexec/ollama 2>/dev/null | head -1 || true)}"
FFMPEG_SRC="${BOOK2VIDO_FFMPEG_SRC:-}"     # 可选：static build（homebrew 版绑 18 个 dylib，不可分发）
RSVG_SRC="${BOOK2VIDO_RSVG_SRC:-$(command -v rsvg-convert 2>/dev/null || true)}"

DIST="$REPO/dist"
APP="$DIST/Book2Vido.app"
RES="$APP/Contents/Resources"

# 可分发性（shippable）：这个包能不能真交给「没有任何技术背景的人」。
# 为什么要有这个状态位：FFMPEG_SRC 默认空 + 只 warn 不报错 → 构建**每次都"成功"**，
# 但产出的包一拖书就在用户机器上停住（作者本机有 brew 装好的 ffmpeg，所以本地永远绿）。
# **静默降级 = 把失败从构建期推迟到用户期。**
SHIPPABLE=1
UNSHIPPABLE_KEYS=""
UNSHIPPABLE_WHY=""

say() { printf '\033[1;34m▸\033[0m %s\n' "$*"; }
ok()  { printf '\033[1;32m  ✓\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m  ⚠\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m  ✗\033[0m %s\n' "$*" >&2; exit 1; }

# 记一次"降级"：$1=去重键，$2=人话说明。同一原因只记一次。
degrade() {
  SHIPPABLE=0
  case " $UNSHIPPABLE_KEYS " in *" $1 "*) return 0 ;; esac
  UNSHIPPABLE_KEYS="$UNSHIPPABLE_KEYS $1"
  UNSHIPPABLE_WHY="${UNSHIPPABLE_WHY}${UNSHIPPABLE_WHY:+；}$2"
}

# ---------- 自检 ----------
say "环境自检"
[ -d "$REPO/src/book2vido" ] || die "找不到源码：$REPO/src/book2vido"
ok "源码 $REPO/src/book2vido"
[ -x "$PY_SRC/bin/python3" ] || die "找不到 python 运行时：$PY_SRC/bin/python3（用 BOOK2VIDO_PY_SRC 指定）"
ok "python 运行时 $("$PY_SRC/bin/python3" -V 2>&1)"
[ -n "$OLLAMA_SRC" ] && [ -f "$OLLAMA_SRC" ] || die "找不到 ollama 二进制（用 BOOK2VIDO_OLLAMA_SRC 指定）"
ok "ollama 二进制 $(du -h "$OLLAMA_SRC" | cut -f1)"
[ -f "$REPO/packaging/Info.plist" ] || die "缺少 packaging/Info.plist"
[ -f "$REPO/packaging/launcher.sh" ] || die "缺少 packaging/launcher.sh"
# 提示词是**必需资产**（T2V-007 起它不在源码里了）：缺了它，ollama 路径一上来就报错。
# 所以这里是 die 而不是 warn —— 宁可构建失败，也别发出一个"拖书就报错"的包
# （与 ffmpeg 那条同理：静默降级 = 把失败从构建期推迟到用户期）。
[ -f "$REPO/prompts/scriptwriter.md" ] || die "缺少 prompts/scriptwriter.md（分镜提示词资产）"
[ -d "$REPO/assets/icons" ] || warn "assets/icons 不存在——图标层将退化为纯色块（可先跑 fetch-icons）"
if [ -n "$FFMPEG_SRC" ]; then
  ok "ffmpeg（$FFMPEG_SRC）"
else
  warn "未提供 static ffmpeg（环境变量 BOOK2VIDO_FFMPEG_SRC）——安装包将不含 ffmpeg"
  degrade ffmpeg "vendor 缺 ffmpeg（用户需自装，非技术用户装不了）"
fi
AVAIL=$(df -m /Users | tail -1 | awk '{print $4}')
ok "可用磁盘 ${AVAIL}MB"
[ "$AVAIL" -gt 600 ] || die "磁盘不足（需 >600MB）"

ALLOW_UNSHIPPABLE=0
for _a in "$@"; do
  case "$_a" in
    --allow-unshippable) ALLOW_UNSHIPPABLE=1 ;;
    --check) say "仅自检，退出"; exit 0 ;;
  esac
done

# ---------- 组装 ----------
say "清理旧产物"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$RES/vendor" "$RES/app"
ok "$APP"

say "① 复制 Python 运行时（可 relocate，已实测）"
cp -R "$PY_SRC" "$RES/runtime"
rm -rf "$RES/runtime/lib/python3.13/site-packages"/{torch,mlx,playwright,scipy,pandas,numba,llvmlite,sympy,jieba,matplotlib}* 2>/dev/null || true
find "$RES/runtime" -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true
ok "runtime 就绪（$(du -sh "$RES/runtime" | cut -f1)）"

say "② 安装最小依赖（只 4 个直接依赖，实测 ~25MB）"
"$RES/runtime/bin/python3" -m pip install --no-cache-dir --quiet --no-warn-script-location \
  pypdf Pillow pyyaml edge-tts 2>&1 | tail -3 || die "pip 安装失败（需联网）"
"$RES/runtime/bin/python3" -c "import PIL, pypdf, yaml, edge_tts; print('  ✓ 四个依赖均可 import')"

say "③ 复制源码 / 配置 / 提示词 / 图标缓存"
cp -R "$REPO/src/book2vido" "$RES/app/book2vido"
find "$RES/app" -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true
cp "$REPO/config.yaml" "$RES/config.yaml"
# 提示词必须随包，位置与 config.yaml 同级（两者都靠 parents[2] 从 Resources/ 回溯）。
# T2V-007 起它不住在 src 里了 —— 漏拷这一行的后果是运行时 promptlib.load() 报错，
# 所以自检段也加了对应的 die（构建期就拦住，别等用户拖书）。
cp -R "$REPO/prompts" "$RES/prompts"
if [ -d "$REPO/assets/icons" ]; then
  mkdir -p "$RES/assets"
  cp -R "$REPO/assets/icons" "$RES/assets/icons"
  ok "源码 + config.yaml + 提示词 $(ls "$RES/prompts"/*.md 2>/dev/null | wc -l | tr -d ' ') 份 + 图标 $(ls "$RES/assets/icons"/*.png 2>/dev/null | wc -l | tr -d ' ') 个"
else
  ok "源码 + config.yaml + 提示词 $(ls "$RES/prompts"/*.md 2>/dev/null | wc -l | tr -d ' ') 份"
fi

say "④ 放置原生二进制"
cp "$OLLAMA_SRC" "$RES/vendor/ollama"; chmod +x "$RES/vendor/ollama"
ok "ollama（$(du -h "$RES/vendor/ollama" | cut -f1)）"
if [ -n "$FFMPEG_SRC" ] && [ -f "$FFMPEG_SRC" ]; then
  cp "$FFMPEG_SRC" "$RES/vendor/ffmpeg"; chmod +x "$RES/vendor/ffmpeg"
  ok "ffmpeg（$(du -h "$RES/vendor/ffmpeg" | cut -f1)）"
else
  warn "未内置 ffmpeg —— 这个包**不能**交给不懂命令行的用户（他会停在 brew install 上）"
  degrade ffmpeg "vendor 缺 ffmpeg（用户需自装，非技术用户装不了）"
fi
if [ -n "$RSVG_SRC" ] && [ -f "$RSVG_SRC" ]; then
  cp "$RSVG_SRC" "$RES/vendor/rsvg-convert"; chmod +x "$RES/vendor/rsvg-convert"
  ok "rsvg-convert（$(du -h "$RES/vendor/rsvg-convert" | cut -f1)）"
fi

say "⑤ 安装 Info.plist / 启动器 / PkgInfo"
cp "$REPO/packaging/Info.plist" "$APP/Contents/Info.plist"
cp "$REPO/packaging/launcher.sh" "$APP/Contents/MacOS/Book2Vido"
chmod +x "$APP/Contents/MacOS/Book2Vido"
printf 'APPL????' > "$APP/Contents/PkgInfo"
ok "启动器 + Info.plist"

say "⑥ 生成应用图标（行途蓝）"
ICONSET="$DIST/AppIcon.iconset"
rm -rf "$ICONSET"; mkdir -p "$ICONSET"
"$RES/runtime/bin/python3" - "$ICONSET" <<'PY' || warn "图标生成失败（不影响功能）"
import sys
from pathlib import Path
from PIL import Image, ImageDraw
out = Path(sys.argv[1])
ACCENT = (5, 109, 232)

def draw(size: int) -> Image.Image:
    s = size * 4  # 超采样后缩小，边缘更干净
    img = Image.new("RGB", (s, s), "#FFFFFF")
    d = ImageDraw.Draw(img)
    r = int(s * 0.22)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=r, fill=ACCENT)
    # 白色播放三角（"文本 → 视频"）
    cx, cy, t = s / 2, s / 2, s * 0.26
    d.polygon([(cx - t * 0.62, cy - t), (cx - t * 0.62, cy + t), (cx + t * 0.78, cy)],
              fill="#FFFFFF")
    # 底部文本条（暗示"文本"来源）
    bw, bh = s * 0.44, s * 0.075
    d.rounded_rectangle([cx - bw / 2, cy + t * 1.5, cx + bw / 2, cy + t * 1.5 + bh],
                        radius=bh / 2, fill=(255, 255, 255, 200))
    return img.resize((size, size), Image.LANCZOS)

specs = [(16,"icon_16x16.png"),(32,"icon_16x16@2x.png"),(32,"icon_32x32.png"),
         (64,"icon_32x32@2x.png"),(128,"icon_128x128.png"),(256,"icon_128x128@2x.png"),
         (256,"icon_256x256.png"),(512,"icon_256x256@2x.png"),(512,"icon_512x512.png"),
         (1024,"icon_512x512@2x.png")]
for px, name in specs:
    draw(px).save(out / name)
print(f"  ✓ {len(specs)} 个尺寸")
PY
if iconutil -c icns "$ICONSET" -o "$RES/AppIcon.icns" 2>/dev/null; then
  /usr/libexec/PlistBuddy -c "Add :CFBundleIconFile string AppIcon" "$APP/Contents/Info.plist" 2>/dev/null || true
  ok "AppIcon.icns"
else
  warn "iconutil 转换失败，跳过图标"
fi
rm -rf "$ICONSET"

# 可选 ad-hoc 签名（对外分发时再开，默认不动，避免干扰 python 运行时）
if [ "${BOOK2VIDO_SIGN:-0}" = "1" ]; then
  say "⑦ ad-hoc 签名"
  codesign --force --deep --sign - "$APP" 2>&1 | tail -2 || warn "签名失败（本地使用不受影响）"
fi

# ---------- 报告 ----------
say "构建完成"
TOTAL=$(du -sm "$APP" | cut -f1)
echo
printf '  产物      : %s\n' "$APP"
printf '  体积      : %s MB\n' "$TOTAL"
printf '  组成      : runtime %s / vendor %s / app %s\n' \
  "$(du -sh "$RES/runtime" | cut -f1)" "$(du -sh "$RES/vendor" | cut -f1)" "$(du -sh "$RES/app" | cut -f1)"
echo
if [ "$SHIPPABLE" = "1" ]; then
  printf '  可分发性  : \033[1;32m✅ 可分发给无技术背景用户\033[0m\n'
else
  printf '  可分发性  : \033[1;31m❌ 不可分发\033[0m —— %s\n' "$UNSHIPPABLE_WHY"
  printf '              作者本机可跑，用户本机大概率卡住。先解决再发出去。\n'
fi
echo
printf '  自检      : "%s/Contents/MacOS/Book2Vido" --selftest 2>/dev/null || true\n' "$APP"
printf '  试运行    : 双击 %s，或把 PDF 拖到它上面\n' "$APP"
printf '  打开输出  : open ~/Movies/Book2Vido\n'
echo
printf '  提示      : 模型（qwen3:8b，4.9GB）不随包分发；\n'
printf '              首次运行自动下载，并复用已有的 ~/.ollama/models\n'

# ---------- 门禁 ----------
# 默认**拒绝产出不可分发的包**：让失败留在构建期，而不是退化成用户的"装不上"。
if [ "$SHIPPABLE" != "1" ] && [ "$ALLOW_UNSHIPPABLE" != "1" ]; then
  echo
  printf '\033[1;31m✗ 门禁未过\033[0m：产物不可分发（%s）\n' "$UNSHIPPABLE_WHY"
  printf '  仅自己机器上用，可加 --allow-unshippable 放行。\n'
  exit 1
fi

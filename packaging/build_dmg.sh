#!/bin/bash
# Book2Vido.dmg 打包脚本（macOS / Apple Silicon）
#
# 职责边界：**只做包装，不做构建**。
#   .dmg 不是"另一种应用"，它只是 .app 的**外层信封**——
#   把 Book2Vido.app + 一个 /Applications 软链装进压缩磁盘映像，
#   让用户看到的是"拖进去就装好了"，而不是"一个躺在 dist/ 里的文件夹"。
#   所以本脚本**必须先有 `dist/Book2Vido.app`**（跑 build_app.sh 产出），
#   它不会替你编译任何东西，也不会修复 .app 的任何问题。
#
# 用法：
#   bash packaging/build_dmg.sh                    # 打包
#   bash packaging/build_dmg.sh --out ~/Desktop/x.dmg
#   bash packaging/build_dmg.sh --skip-verify      # 跳过挂载校验（快，但不推荐）
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$REPO/dist/Book2Vido.app"
VOLNAME="文本转视频"          # 挂载后 Finder 里显示的卷名（= 用户看到的"安装盘"名字）
OUT="$REPO/dist/Book2Vido.dmg"
SKIP_VERIFY=0

say() { printf '\033[1;34m▸\033[0m %s\n' "$*"; }
ok()  { printf '\033[1;32m  ✓\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m  ⚠\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

# ---------- 参数 ----------
while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT="$2"; shift 2 ;;
    --volname) VOLNAME="$2"; shift 2 ;;
    --skip-verify) SKIP_VERIFY=1; shift ;;
    -h|--help) sed -n '2,17p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) die "未知参数：$1" ;;
  esac
done

# ---------- 前置检查 ----------
say "前置检查"
[ -d "$APP" ] || die "找不到 $APP —— 请先跑 bash packaging/build_app.sh"
[ -x "$APP/Contents/MacOS/Book2Vido" ] || die "$APP 已损坏（缺启动器）—— 请重新构建"
APP_MB=$(du -sm "$APP" | cut -f1)
ok "来源 app $APP（${APP_MB} MB）"

# 关键：app 里**必须**有随包运行时，否则 dmg 只是个空壳
[ -x "$APP/Contents/Resources/runtime/bin/python3" ] \
  || die "app 内缺随包 Python 运行时 —— dmg 打出来也装不了，先重新构建"
ok "随包运行时就绪"

# ffmpeg 是否随包 —— 直接影响**别人**能不能用（作者本机有 brew 版，本地永远绿）
if [ -x "$APP/Contents/Resources/vendor/ffmpeg" ]; then
  ok "ffmpeg 已随包（可分发给无技术背景用户）"
  FFMPEG_BUNDLED=1
else
  warn "ffmpeg **未随包** —— 本机可用（系统已有），但**发给别人会卡在合成那一步**"
  warn "如需可分发：构建时传 BOOK2VIDO_FFMPEG_SRC=<static build 路径>"
  FFMPEG_BUNDLED=0
fi

mkdir -p "$(dirname "$OUT")"

# ---------- 组装 staging ----------
say "组装磁盘映像内容"
STAGE="$(mktemp -d)"
cleanup() { rm -rf "$STAGE"; }
trap cleanup EXIT

# 用 ditto 而不是 cp -R：保留权限位与扩展属性。
# app 里有 python 运行时（含可执行文件），权限错一位就会"装上了但点不动"。
ditto "$APP" "$STAGE/Book2Vido.app"
ok "已复制 app"

ln -s /Applications "$STAGE/Applications"
ok "已放置 /Applications 软链（这是「拖进去就装好」的关键）"

# ---------- 生成 ----------
say "生成 dmg（UDZO 压缩）"
rm -f "$OUT"
hdiutil create -volname "$VOLNAME" -srcfolder "$STAGE" -ov -format UDZO \
  -fs HFS+ "$OUT" >/dev/null || die "hdiutil 生成失败"
ok "已生成 $OUT"

# ---------- 校验 ----------
if [ "$SKIP_VERIFY" = "1" ]; then
  warn "已跳过挂载校验"
else
  say "校验（真挂载一次，确认用户双击后看到的不是空盘）"
  MNT="$(mktemp -d)"
  if hdiutil attach "$OUT" -mountpoint "$MNT" -nobrowse -readonly -quiet 2>/dev/null; then
    [ -d "$MNT/Book2Vido.app" ] || { hdiutil detach "$MNT" -quiet 2>/dev/null; die "卷内没有 Book2Vido.app"; }
    [ -L "$MNT/Applications" ] || { hdiutil detach "$MNT" -quiet 2>/dev/null; die "卷内缺 Applications 软链"; }
    [ -x "$MNT/Book2Vido.app/Contents/MacOS/Book2Vido" ] \
      || { hdiutil detach "$MNT" -quiet 2>/dev/null; die "卷内启动器不可执行（权限在打包中丢了）"; }
    hdiutil detach "$MNT" -quiet 2>/dev/null
    ok "挂载校验通过：app + Applications 软链 + 启动器权限 均正常"
  else
    die "dmg 无法挂载 —— 这个包不能交给别人"
  fi
  rmdir "$MNT" 2>/dev/null || true
fi

# ---------- 报告 ----------
DMG_MB=$(du -sm "$OUT" | cut -f1)
echo
printf '  产物      : %s\n' "$OUT"
printf '  体积      : %s MB（来源 app %s MB，压缩率 %s%%）\n' \
  "$DMG_MB" "$APP_MB" "$((DMG_MB * 100 / APP_MB))"
printf '  用户怎么装: 双击 dmg → 把「文本转视频」拖进 Applications → 完成\n'
echo
if [ "$FFMPEG_BUNDLED" = "1" ]; then
  printf '  可分发性  : \033[1;32m✅ 可分发给无技术背景用户\033[0m\n'
else
  printf '  可分发性  : \033[1;33m⚠ 仅限本机/同类环境\033[0m（ffmpeg 依赖系统已装）\n'
  printf '              先跑一次自检确认：\n'
  printf '              "%s/Contents/MacOS/Book2Vido" --selftest | grep ffmpeg\n' "$APP"
fi
echo
printf '  注意      : 从网上下载的 dmg 会带隔离属性，Gatekeeper 可能拦截；\n'
printf '              本机自己打包的不受影响。对外分发需 Apple 开发者签名+公证。\n'
printf '  模型      : qwen3:8b（4.9GB）不随包，首次运行自动下载\n'

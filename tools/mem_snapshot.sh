#!/usr/bin/env bash
# 本机资源快照 —— 回答「现在机器什么状态 / 能不能跑本地模型」
# 只读，不改动任何应用。用法：bash tools/mem_snapshot.sh
set -u

pg=16384  # Apple Silicon 页大小
GB=$((1024*1024*1024))

echo "════════════════════════════════════════════════════════"
echo " 本机资源快照 · $(date '+%Y-%m-%d %H:%M:%S')"
echo "════════════════════════════════════════════════════════"

echo
echo "【1】内存去向（wired 是隐形黑洞，常态 2–4GB）"
vm_stat | awk -v pg=$pg -v gb=$GB '
/Pages free/ {f=$3} /Pages active/ {a=$3} /Pages inactive/ {i=$3}
/Pages wired down/ {w=$4} /Pages occupied by compressor/ {c=$5}
END {
  printf "   free        %6.2f GB\n", f*pg/gb
  printf "   active      %6.2f GB\n", a*pg/gb
  printf "   inactive    %6.2f GB\n", i*pg/gb
  printf "   wired       %6.2f GB  ← 内核/GPU 锁定，只能重启回收\n", w*pg/gb
  printf "   compressor  %6.2f GB  ← 压缩内存，内存压力的证据\n", c*pg/gb
  printf "   ─────────────────────────────\n"
  printf "   可动内存 ≈ %.2f GB（物理 − wired − compressor）\n", (16 - w*pg/gb - c*pg/gb)
}'

echo
echo "【2】swap 水位（>80% 危险，>95% 高危）"
sysctl -n vm.swapusage | sed 's/^/   /'

echo
echo "【3】负载（对比核数，超 100% 即超载）"
printf "   核数 %s ｜ load %s\n" "$(sysctl -n hw.ncpu)" "$(sysctl -n vm.loadavg)"

echo
echo "【4】磁盘"
df -h /System/Volumes/Data | tail -1 | awk '{printf "   已用 %s / %s（%s）可用 %s\n", $3,$2,$5,$4}'

echo
echo "【5】谁在吃内存 TOP 12（按应用聚合）"
ps -Ao rss,comm | tail -n +2 | awk '
{
  rss=$1/1024; cmd=$0
  if (cmd ~ /WorkBuddy/) k="WorkBuddy"
  else if (cmd ~ /Google Chrome/) k="Google Chrome"
  else if (cmd ~ /Safari|WebKit/) k="Safari/WebKit"
  else if (cmd ~ /WeChat/) k="微信"
  else if (cmd ~ /IntelliJ|jetbrains|idea/) k="IntelliJ IDEA"
  else if (cmd ~ /DingTalk/) k="钉钉"
  else if (cmd ~ /NeteaseMusic/) k="网易云音乐"
  else if (cmd ~ /ollama|llama-server/) k="Ollama"
  else if (cmd ~ /claude/) k="claude CLI"
  else if (cmd ~ /^\/System|^\/usr\/libexec|\.framework|DriverKit/) k="[系统后台]"
  else k="[其他]"
  m[k]+=rss; n[k]++
}
END { for (k in m) printf "%8.0f\t%s\t%d\n", m[k], k, n[k] }' \
  | sort -k1,1 -rn | head -12 \
  | awk -F'\t' '{printf "   %-18s %8s MB  (%s 进程)\n", $2, $1, $3}'

echo
echo "【6】进程总数"
printf "   %s 个\n" "$(ps -A | wc -l | tr -d ' ')"

echo
echo "【7】本地模型状态"
if curl -s --max-time 3 http://localhost:11434/api/tags >/dev/null 2>&1; then
  printf "   serve: 在跑\n"
  ollama ps 2>/dev/null | sed 's/^/   /'
  printf "   磁盘占用: %s\n" "$(du -sh ~/.ollama/models 2>/dev/null | cut -f1)"
else
  printf "   serve: 未运行\n"
fi

echo
echo "【8】提示"
echo "   · 卸载模型几乎不释放 free（mmap 机制）→ 想腾内存请关冗余浏览器/IDE"
echo "   · 冷加载实测 1.63s（页缓存热）→ 模型当弹性资源用，不必常驻"
echo "   · wired > 8GB 或 swap > 80% → 该重启了"
echo "════════════════════════════════════════════════════════"

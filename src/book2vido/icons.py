"""零成本画面资产层：Iconify 开源图标 → 本地 PNG 缓存。

为什么是 Iconify：
- 聚合 200k+ 开源图标，许可干净（Tabler MIT / Phosphor MIT / Carbon Apache-2.0 / MDI Apache-2.0）
- 支持 `?color=` 直接输出行途蓝，线描风格与品牌「黑白极简 + 行途蓝」一致（不用 emoji）
- 单张 SVG 仅几 KB，一次抓取永久复用，边际成本 ¥0，符合 CONSTITUTION「极致省资源」

设计：**离线优先**。运行时只用本地缓存（assets/icons/*.png）；联网抓取是显式的
`fetch`/prefetch 动作，失败不阻塞出片（静默降级为无图标版式）。
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

from . import binpaths
from .concepts import CONCEPTS

API = "https://api.iconify.design"
UA = {"User-Agent": "book2vido/0.1 (+https://github.com/xingtu1996/book2vido)"}

# 中文关键词 → Iconify 图标名（Tabler 线描，MIT）。
# 覆盖 AI / 工程化 / 效率 等本账号高频主题；命中规则见 resolve()。
# ⚠️ 本表**不得与 `concepts.CONCEPTS` 出现同名键**：两表在导入时合并（见文件末尾），
#    CONCEPTS 覆盖本表 —— 同名键等于**永远不生效的死词条**，而且不会有任何报错。
#    原先有 31 个这样的影子键（其中 5 个语义还不一样，如 `安全`→lock 被 CONCEPTS 的
#    `安全`→shield-lock 顶掉），已按「谁更准留谁」删除：**叙事概念归 concepts，
#    工程术语归本表，两表键不相交**。守护见 `tests/verify_icons.py`。
KEYWORD_ICONS: dict[str, str] = {
    # —— 省 Token / 成本 ——
    "省token": "tabler:coin-yuan", "token": "tabler:coin-yuan",
    "花钱": "tabler:coin-yuan", "免费": "tabler:gift", "账单": "tabler:receipt",
    "压缩": "tabler:arrows-minimize", "精简": "tabler:arrows-minimize",
    # —— 输入 / 输出 ——
    "输入": "tabler:keyboard", "输出": "tabler:arrow-up-right", "上传": "tabler:upload",
    "导出": "tabler:download", "粘贴": "tabler:clipboard",
    # —— 复用 ——
    "复用": "tabler:recycle", "重用": "tabler:recycle",
    "一次": "tabler:repeat", "聚合": "tabler:stack-2", "分层": "tabler:stack-2",
    "模板": "tabler:template", "规则": "tabler:checklist",
    # —— 提示词 ——
    "提示词": "tabler:message-2", "prompt": "tabler:message-2", "口播": "tabler:microphone",
    "skill": "tabler:puzzle", "插件": "tabler:puzzle",
    # —— 模型 / 智能 ——
    "大模型": "tabler:cpu", "llm": "tabler:cpu",
    "智能": "tabler:brain", "上下文": "tabler:database",
    "缓存": "tabler:database-cog", "检索": "tabler:search", "搜索": "tabler:search",
    "知识库": "tabler:books",
    # —— 工程 ——
    "流水线": "tabler:git-branch", "管线": "tabler:git-branch",
    "自动化": "tabler:robot", "编译": "tabler:hammer", "构建": "tabler:building-factory",
    "调试": "tabler:bug", "检查": "tabler:checklist", "测试": "tabler:flask",
    "部署": "tabler:rocket", "发布": "tabler:send",
    # —— 内容 / 表达 ——
    "文档": "tabler:file-text",
    "对话": "tabler:messages",
    "配图": "tabler:photo", "封面": "tabler:photo",
    "翻译": "tabler:language", "人话": "tabler:language",
    # —— 成长 ——
    "想法": "tabler:bulb", "增长": "tabler:trending-up",
    "提升": "tabler:trending-up", "榜单": "tabler:trophy", "排行": "tabler:trophy",
    # —— 风险 / 人 ——
    "坑": "tabler:alert-triangle", "陷阱": "tabler:alert-triangle",
    "快速": "tabler:bolt", "管理": "tabler:users-group",
    "路线": "tabler:route", "地图": "tabler:map", "钥匙": "tabler:key",
    "自省": "tabler:message-question",
    "判断": "tabler:scale", "取舍": "tabler:scale", "习惯": "tabler:repeat",
    # —— 抽象/内容型四字词（LLM 关键词常见形态）——
    "分布": "tabler:chart-pie", "占比": "tabler:chart-pie", "统计": "tabler:chart-bar",
    "结构": "tabler:sitemap", "三段": "tabler:sitemap",
    "命令": "tabler:terminal-2", "脚本": "tabler:terminal-2", "终端": "tabler:terminal-2",
    "会话": "tabler:messages",
    "优化": "tabler:adjustments", "调优": "tabler:adjustments", "参数": "tabler:adjustments",
    "经验": "tabler:notebook", "笔记": "tabler:notebook", "沉淀": "tabler:archive",
    "归档": "tabler:archive", "存": "tabler:archive",
    "诊断": "tabler:stethoscope", "排查": "tabler:stethoscope", "体检": "tabler:stethoscope",
    "无侵入": "tabler:shield", "不改": "tabler:shield", "只管": "tabler:shield",
    "隐性": "tabler:eye-off", "默认": "tabler:eye-off", "隐藏": "tabler:eye-off",
    "蒸馏": "tabler:filter", "过滤": "tabler:filter", "筛选": "tabler:filter",
    "包装": "tabler:package", "封装": "tabler:package",
    "术": "tabler:tool", "法": "tabler:list-check", "清单": "tabler:list-check",
    "底": "tabler:anchor", "根": "tabler:anchor",
    "表演": "tabler:masks-theater", "姿态": "tabler:masks-theater",
    "思维": "tabler:brain",
    "激活": "tabler:click", "触发": "tabler:click", "开关": "tabler:toggle-right",
    "离线": "tabler:cloud-off", "断网": "tabler:cloud-off", "本地": "tabler:device-desktop",
    "入库": "tabler:archive", "入库标准化": "tabler:archive",
    "门槛": "tabler:fence", "标准": "tabler:ruler-measure",
    "规范": "tabler:ruler-measure", "成熟度": "tabler:gauge", "评分": "tabler:gauge",
}

# 受控概念清单已提升为独立领域资产 → `concepts.py`（档 1 结构整改，2026-09-15）。
#
# 它同时服务两个消费者：分镜层要「有哪些合法概念」（注入提示词，防模型自由发挥），
# 画面层要「概念对应哪个图标」（渲染时查表）。**住在任何一方家里都是错的** ——
# 留在本模块时，`scriptwriter` 被迫 `import icons`（生成层跨界引用资产层，依赖被拉弯），
# 且 `models.Scene.concept` 的值域约束指向了另一个模块的内部常量。
# 现在两边平级依赖 concepts，依赖是直的。详见 `concepts.py` docstring 与
# `doc/17-结构诊断与重构方案.html` §S-2。

# 两表**合并**：叙事概念（concepts）+ 工程术语（本表）= 完整解析词表。
# ⚠️ 合并天然可以「后者覆盖前者」，但**不该依赖它** —— 覆盖是静默的：
#    读者得靠记忆才知道哪个键已死（铁律八：先写得让人改对）。
#    所以本表已清空全部与 CONCEPTS 同名的键，两表**键不相交**，
#    这条不变式由 `tests/verify_icons.py` 守住（冲突即报错，不再静默）。
KEYWORD_ICONS.update(CONCEPTS)

# 兜底图标：关键词表未命中时按关键词散列选一个，保证「每张卡都有画面」。
# 选语义中性、不误导的图形，避免「自省」错配成「金币」这类硬伤。
# 池子够大（22 个）才不会让多张卡撞成同一个图 —— 但兜底越少走越好，
# 真正的解法是 CONCEPTS 受控清单（见 concepts.py）。
#
# ⚠️ 池子里每一项都必须**本地实有**（assets/icons/*.png）。这不是洁癖：
#    缺失项不会报错，只会在离线时静默降级成「无图标版式」—— 用户拿到一张
#    缺图的卡，而日志全绿。守护见 `tests/verify_icons.py`。
#    本池原为 24 项，其中 crystal-ball / comet / planet / seo / infinity / meteor
#    六个本地从未存在过（词表改在了缓存前面），已换成本地已有的中性几何。
#
# ⚠️ 同时不要放**第三方品牌 logo**：本池原含 `tabler:brand-openai`，
#    它既不中性（讲《关键对话》时出现在卡上就很荒谬），也是别人的商标。
#    兜底图形只表达「这里有个概念」，不表达「这是谁的东西」。
FALLBACK_ICONS = [
    "tabler:sparkles", "tabler:bulb", "tabler:circle-dot", "tabler:flame",
    "tabler:star", "tabler:puzzle", "tabler:point", "tabler:hexagon",
    "tabler:diamond", "tabler:wave-sine", "tabler:atom", "tabler:grid-dots",
    "tabler:triangle", "tabler:square-rotated", "tabler:cone", "tabler:octagon",
    "tabler:shadow", "tabler:box", "tabler:ripple", "tabler:atom-2",
    "tabler:apps", "tabler:arrow-down-right",
]

# 命中优先级：长词优先，避免「大模型」被「模型」抢走
_SORTED = sorted(KEYWORD_ICONS.items(), key=lambda kv: -len(kv[0]))


def resolve(keyword: str) -> str | None:
    """中文关键词 → Iconify 图标名。无命中返回 None（上层降级为无图标版式）。"""
    if not keyword:
        return None
    k = keyword.lower()
    for zh, icon in _SORTED:
        if zh in k:
            return icon
    return None


def fallback_for(keyword: str) -> str:
    """关键词表未命中时的兜底图标：用稳定散列选一个（同一词每次同图）。

    注意：不能用内置 hash()——Python 字符串 hash 每进程随机化，会导致
    同一个词在不同次运行里换图标。
    """
    if not keyword:
        return FALLBACK_ICONS[0]
    import zlib
    return FALLBACK_ICONS[zlib.crc32(keyword.encode("utf-8")) % len(FALLBACK_ICONS)]


def _cache_name(icon_id: str) -> str:
    return icon_id.replace(":", "-") + ".png"


def render_svg(svg: bytes, size: int) -> bytes | None:
    """SVG → PNG。优先 rsvg-convert（随包内置 / brew / MacPorts），退 cairosvg，都没有则 None。"""
    with tempfile.TemporaryDirectory() as td:
        s = Path(td) / "i.svg"
        p = Path(td) / "i.png"
        s.write_bytes(svg)
        # 1) rsvg-convert
        rsvg = binpaths.rsvg_convert()
        if rsvg:
            try:
                r = subprocess.run(
                    [rsvg, "-w", str(size), "-h", str(size), str(s), "-o", str(p)],
                    capture_output=True, timeout=20,
                )
                if r.returncode == 0 and p.exists() and p.stat().st_size > 0:
                    return p.read_bytes()
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
        # 2) cairosvg（macOS 需 DYLD_LIBRARY_PATH 指向 brew/MacPorts 的 lib；动态探测而非写死）
        import os
        env = os.environ.copy()
        for lib in ("/opt/homebrew/lib", "/usr/local/lib", "/opt/local/lib"):
            if Path(lib).is_dir():
                env["DYLD_LIBRARY_PATH"] = lib
                break
        code = ("import cairosvg,sys;"
                "cairosvg.svg2png(url=sys.argv[1],write_to=sys.argv[2],"
                "output_width=int(sys.argv[3]),output_height=int(sys.argv[3]))")
        try:
            r = subprocess.run(
                [sys.executable, "-c", code, str(s), str(p), str(size)],
                capture_output=True, timeout=40, env=env,
            )
            if r.returncode == 0 and p.exists() and p.stat().st_size > 0:
                return p.read_bytes()
        except subprocess.TimeoutExpired:
            pass
        return None


class IconProvider:
    """离线优先的图标获取器：缓存命中直接返回，未命中才联网（且失败不抛错）。"""

    def __init__(self, cache_dir: str | Path, color: str = "#056DE8",
                 size: int = 440, allow_network: bool = True):
        self.dir = Path(cache_dir)
        self.color = color
        self.size = size
        self.allow_network = allow_network
        self._used_fallback: set[str] = set()
        self.dir.mkdir(parents=True, exist_ok=True)

    def get(self, keyword: str = "", concept: str | None = None) -> Path | None:
        """取图标。两级解析：受控 concept 优先，再退自由 keyword，最后兜底。

        concept 由 LLM 从 CONCEPTS 受控清单中选出（清单定义见 concepts.py，注入见 scriptwriter），
        语义命中率接近 100%；keyword 是自由生成的大标题词，仅作次选。
        """
        icon_id = resolve(concept or "") or resolve(keyword or "")
        if not icon_id:
            icon_id = self._fallback(concept or keyword or "")
        return self.get_by_id(icon_id) if icon_id else None

    def _fallback(self, seed: str) -> str:
        """兜底选图，并在同一次运行内避免撞车（多张卡不重复同一图形）。"""
        import zlib
        n = len(FALLBACK_ICONS)
        start = zlib.crc32(seed.encode("utf-8")) % n
        for i in range(n):
            c = FALLBACK_ICONS[(start + i) % n]
            if c not in self._used_fallback:
                self._used_fallback.add(c)
                return c
        return FALLBACK_ICONS[start]

    def get_by_id(self, icon_id: str) -> Path | None:
        cache = self.dir / _cache_name(icon_id)
        if cache.exists() and cache.stat().st_size > 0:
            return cache
        if not self.allow_network:
            return None
        png = self._download(icon_id)
        if png:
            cache.write_bytes(png)
            return cache
        return None

    def _download(self, icon_id: str) -> bytes | None:
        q = urllib.parse.urlencode({"color": self.color})
        url = f"{API}/{icon_id}.svg?{q}"
        try:
            req = urllib.request.Request(url, headers=UA)
            svg = urllib.request.urlopen(req, timeout=15).read()
        except Exception:
            return None
        return render_svg(svg, self.size)


def prefetch(keywords_or_ids, cache_dir, color: str = "#056DE8", size: int = 440) -> dict:
    """预热缓存：传入中文关键词或 `set:name` 图标名列表。返回 {key: 状态}。"""
    p = IconProvider(cache_dir, color=color, size=size)
    out = {}
    for k in keywords_or_ids:
        if ":" in k:
            out[k] = "ok" if p.get_by_id(k) else "fail"
        else:
            out[k] = "ok" if p.get(k) else "miss-or-fail"
    return out

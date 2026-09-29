"""零成本画面层：Pillow 生成信息卡（**色板由主题决定**）。不调用任何文生图 API。

配色：见 `THEMES` —— 默认 `ink`（深底炭黑红），另有 `paper` / `blue` / `custom`。
⚠️ `blue`（#056DE8 行途蓝）是**主题化之前的原配色**，现仅作回退 / A-B 对照，
**不是**当前默认。色板 SSoT：行途封面设计规则 V1.2「黑红灰」。

版式（1080×1920 竖版）：
    顶部色条 / 序号 / 关键词大标题
    ── 主视觉面板（关键词图标，线描，运行时按主题着色）──
    正文（自动换行、居中）
    品牌水印 / 底部色条

画面来源分级（见 doc/08-画面资产策略.md）：
    L1 关键词图标（本模块 + icons.py，Iconify 开源图标，¥0）
    L2 主视觉面板底色 + 版式节奏（本模块，¥0）
    L3 文生图插画（未来扩展位，需图像模型，暂不启用）
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import icons as _icons
from .paths import project_root

# macOS 自带中文字体候选链：PingFang 在部分系统缺失（本机即无），逐级回退。
FONT_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
]

INK = "#111111"
MUTED = "#B8B8B8"
PANEL = "#F2F7FF"

# ── 行途定档色板（SSoT：`03_运营工具箱/02_排版与设计/行途公众号封面设计规则_V1.md` V1.2）──
# 口径：**只借色系，不借版式**（boss 2026-09-13 上游原则，原针对 OpenDesign PPT，此处同样适用）。
# 黑红灰三色体系：大字压场；红只留给关键词；小字一律浅灰。
# 角色：bg 底 / ink 大字正文 / sub 次信息 / dim 更浅一档 / accent 强调红 / panel 主视觉面板 / faint 面板内占位
THEMES = {
    # 深底炭黑：竖屏信息流里最抓眼，红在黑上对比最强（短视频主流）
    "ink":   dict(bg="#1F2225", ink="#FFFFFF", sub="#9BA1A8", dim="#6E757D",
                  accent="#F2644F", panel="#2A2E33", faint="#3A3F45"),
    # 浅底纸白：与公众号浅底封面同源，亮环境友好
    "paper": dict(bg="#FFFFFF", ink="#1F2225", sub="#4C525A", dim="#8A9099",
                  accent="#F2644F", panel="#F2F2F2", faint="#E2E4E6"),
    # 行途蓝：主题化之前的原始配色，留作回退 / A-B 对照（不是黑红灰体系）
    "blue":  dict(bg="#FFFFFF", ink="#111111", sub="#B8B8B8", dim="#B8B8B8",
                  accent="#056DE8", panel="#F2F7FF", faint="#D8E6FA"),
}
DEFAULT_THEME = "ink"


def resolve_font(preferred: str | None = None) -> str | None:
    """返回第一个『存在且能加载』的字体路径；都不行则 None（调用方回退默认字体）。"""
    for p in ([preferred] if preferred else []) + FONT_CANDIDATES:
        if not p or not Path(p).exists():
            continue
        try:
            ImageFont.truetype(p, 32, index=0)
            return p
        except Exception:
            continue
    return None


def _tint(rgba: Image.Image, color: str) -> Image.Image:
    """单色线描图标重新着色（保留 alpha）。

    为什么必须有这一步：图标缓存键（icons._cache_name）只含 icon_id **不含 color**，
    且缓存里存的是 PNG 而非 SVG —— 不重着色的话，换主题后图标永远是旧品牌色，
    表现为「底色文字全换了、图标没换」（2026-09-16 预览实测抓到）。
    线描图标是单色 → 用 point 重写 RGB 三通道（C 实现，微秒级），alpha 原样保留；
    离线可用，也不产生第二份缓存。
    """
    c = color.lstrip("#")
    tgt = (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))
    r, g, b, a = rgba.split()
    r = r.point(lambda _: tgt[0])
    g = g.point(lambda _: tgt[1])
    b = b.point(lambda _: tgt[2])
    out = Image.merge("RGBA", (r, g, b, a))
    rgba.paste(out)
    return rgba


class PillowProvider:
    def __init__(self, accent: str = "#056DE8", font: str | None = None,
                 w: int = 1080, h: int = 1920, brand: str = "行途 XingTu",
                 icons: bool = True, icon_dir: str | None = None,
                 icon_size: int = 430, allow_network: bool = True,
                 theme: str = DEFAULT_THEME, bg_images: list | None = None):
        # 主题决定整套色板；`accent` 仅在 custom 主题下生效（见下）。
        # 为什么不让 accent 直接覆盖：单个色值撑不起一套体系，改一个不配套会撞对比度。
        if theme == "custom":
            self.pal = dict(THEMES["blue"])
            self.pal["accent"] = accent
        elif theme in THEMES:
            self.pal = dict(THEMES[theme])
        else:
            print(f"[warn] 未知画面主题 {theme!r} —— 回退 {DEFAULT_THEME!r}"
                  f"（可选：{', '.join(sorted(THEMES))}、custom）")
            self.pal = dict(THEMES[DEFAULT_THEME])
        self.theme = theme
        self.accent = self.pal["accent"]
        self.w, self.h = w, h
        # 用户上传的背景图（铺底素材）：循环使用到各分镜卡。空 = 纯色底。
        self.bg_images = list(bg_images or [])
        self.brand = brand
        self.font = resolve_font(font)
        if not self.font:
            print("[warn] 未找到可用中文字体（PingFang/Hiragino/STHeiti 均缺失）——"
                  "回退默认位图字体，中文可能显示异常。")

        # 图标层（可选）：离线缓存优先；渲染器缺失/未预热时自动跳过，不阻塞出片
        self.icons = None
        if icons:
            d = Path(icon_dir) if icon_dir else (project_root() / "assets" / "icons")
            # color 必须用 **主题解析后的** accent（不是入参）——否则主题切了、图标还是旧色。
            # 图标＝关键词的图形化，所以走 accent 正合 SSoT「红只留给关键词」。
            self.icons = _icons.IconProvider(d, color=self.accent, size=icon_size,
                                             allow_network=allow_network)

    def _load(self, size: int):
        if self.font:
            try:
                return ImageFont.truetype(self.font, size, index=0)
            except Exception as e:  # resolve 已验证过，此处仅兜底
                print(f"[warn] 字体加载失败 {self.font}: {e}")
        return ImageFont.load_default()

    def _load_bg(self, bg_path: str) -> Image.Image:
        """用户上传图片 → cover 裁剪到画布尺寸 + 轻量压暗，保证白字可读。"""
        im = Image.open(bg_path).convert("RGB")
        iw, ih = im.size
        scale = max(self.w / iw, self.h / ih)
        nw, nh = int(iw * scale), int(ih * scale)
        im = im.resize((nw, nh), Image.LANCZOS)
        left, top = (nw - self.w) // 2, (nh - self.h) // 2
        im = im.crop((left, top, left + self.w, top + self.h))
        # 压暗：白字 + 红关键词在压暗照片上对比最强；alpha=130 ≈ 半透明黑蒙版。
        scrim = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 130))
        return Image.alpha_composite(im.convert("RGBA"), scrim).convert("RGB")

    def card(self, scene, idx: int, out_dir, bg_image: str | None = None) -> str:
        # 铺底优先级：显式传入 > 轮询用户上传的背景图 > 主题纯色底。
        bg_path = (bg_image or (self.bg_images[(idx - 1) % len(self.bg_images)]
                                if self.bg_images else None))
        if bg_path:
            try:
                img = self._load_bg(bg_path)
            except Exception as e:
                print(f"[warn] 背景图加载失败 {bg_path}: {e} —— 回退纯色底")
                img = Image.new("RGB", (self.w, self.h), self.pal["bg"])
        else:
            img = Image.new("RGB", (self.w, self.h), self.pal["bg"])
        d = ImageDraw.Draw(img)
        cx = self.w // 2

        # 上下品牌色条（红：品牌框架，非关键词强调）
        d.rectangle([0, 0, self.w, 20], fill=self.accent)
        d.rectangle([0, self.h - 20, self.w, self.h], fill=self.accent)

        # 序号（左） + 品牌（右）—— 次信息走灰，把红留给关键词（SSoT 二、§红线）
        d.text((84, 96), f"{idx:02d}", font=self._load(46), fill=self.pal["sub"])
        d.text((self.w - 84, 108), self.brand, font=self._load(32),
               fill=self.pal["dim"], anchor="ra")

        # 关键词大标题（居中，自动缩放以适配 1~2 行）
        key = (scene.keyword or "").strip().lstrip("# ").strip()
        if key:
            ks = self._fit_size(key, max_w=900, max_lines=2, start=88, min_size=56)
            kf = self._load(ks)
            lines = self._wrap(key, ks, 900)[:2]
            y = 210
            for ln in lines:
                d.text((cx, y), ln, font=kf, fill=self.pal["ink"], anchor="ma")
                y += int(ks * 1.28)
            # 关键词下短分隔线（红：与关键词同组，属允许的两处红之一）
            d.rounded_rectangle([cx - 46, y + 14, cx + 46, y + 22], radius=4, fill=self.accent)
            top_limit = max(y + 96, 500)
        else:
            top_limit = 460

        # 正文先排（字号自适应 + 行数），因为它的高度决定整组居中位置
        bsize = self._fit_size(scene.text, max_w=880, max_lines=5, start=62, min_size=42)
        bf = self._load(bsize)
        line_h = int(bsize * 1.5)
        body_lines = self._wrap(scene.text, bsize, 880)
        body_h = len(body_lines) * line_h

        # 「主视觉面板 + 间距 + 正文」视为一个整体，在 [标题分隔线, 底部安全边距] 内垂直居中。
        # 原实现把面板钉死在固定 y、正文再在剩余空间里居中，短文案时下部会空出近 1/4 卡高
        # （实测 1080×1920 卡片下留白 440px，观感「头重脚轻」）。
        panel_h, gap = 680, 96
        bottom_limit = self.h - 190
        group_h = panel_h + gap + body_h
        panel_top = top_limit + max(0, (bottom_limit - top_limit - group_h) // 2)
        panel_bottom = panel_top + panel_h

        # 主视觉面板
        d.rounded_rectangle([110, panel_top, self.w - 110, panel_bottom],
                            radius=48, fill=self.pal["panel"])

        # 图标：受控 concept 优先，再退自由 keyword（见 concepts.CONCEPTS 与 icons.get）
        concept = getattr(scene, "concept", "") or ""
        icon = self.icons.get(scene.keyword or "", concept) if self.icons else None
        if icon:
            try:
                ic = Image.open(icon).convert("RGBA")
                _tint(ic, self.accent)          # 缓存图标可能是任意旧色 → 统一重着色
                side = 440
                ic = ic.resize((side, side), Image.LANCZOS)
                img.paste(ic, (cx - side // 2, panel_top + (panel_h - side) // 2), ic)
            except Exception as e:
                print(f"[warn] 图标合成失败 {icon}: {e}")
        else:
            # 无图标：面板中央放关键词首字（大号、淡蓝），仍保证「有画面」
            ch = (key or "行")[0]
            d.text((cx, panel_top + panel_h // 2), ch, font=self._load(320),
                   fill=self.pal["faint"], anchor="mm")

        # 正文（居中）
        y = panel_bottom + gap
        for ln in body_lines:
            d.text((cx, y), ln, font=bf, fill=self.pal["ink"], anchor="ma")
            y += line_h

        path = Path(out_dir) / f"card_{idx:03d}.png"
        img.save(path)
        return str(path)

    # —— 排版工具 ——
    def _wrap(self, text: str, size: int, max_w: int | None = None) -> list[str]:
        max_w = max_w or (self.w - 144)
        font = self._load(size)
        lines, cur = [], ""
        for ch in text:
            if font.getlength(cur + ch) > max_w:
                lines.append(cur)
                cur = ch
            else:
                cur += ch
        if cur:
            lines.append(cur)
        return lines

    def _fit_size(self, text: str, max_w: int, max_lines: int,
                  start: int, min_size: int) -> int:
        """从 start 起逐档降字号，直到文案在 max_lines 行内排得下。"""
        size = start
        while size > min_size:
            if len(self._wrap(text, size, max_w)) <= max_lines:
                return size
            size -= 4
        return min_size

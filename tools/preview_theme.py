"""画面主题预览 + 对比度体检（可复用）。

用法：
    python tools/preview_theme.py                 # 渲染全部主题到 /tmp/b2v_themes
    python tools/preview_theme.py --theme ink     # 只渲染一个
    python tools/preview_theme.py --no-icons      # 跳过图标（快，专看配色）

为什么单独有这个脚本：换配色是**视觉**改动，光看色值判断不了效果
——「灰字在炭黑上到底读不读得清」必须出图 + 算对比度才知道。
"""
from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace

from book2vido import visualizer


def luminance(hex_color: str) -> float:
    """WCAG 相对亮度。"""
    c = hex_color.lstrip("#")
    r, g, b = (int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))

    def lin(v: float) -> float:
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast(fg: str, bg: str) -> float:
    """WCAG 对比度 1..21。"""
    a, b = luminance(fg), luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


# 关键配对：改色后必须逐条满足最低对比度，否则小图/弱视下读不出
PAIRS = [
    ("ink", "bg", 4.5, "主标题大字"),
    ("sub", "bg", 3.0, "序号（次信息，可放宽）"),
    ("dim", "bg", 3.0, "品牌落款（最浅，可放宽）"),
    ("accent", "bg", 3.0, "强调红（色条/分隔线）"),
    ("ink", "panel", 4.5, "正文若落在面板上"),
]


def audit(theme: str) -> list[tuple[str, float, float, bool]]:
    pal = visualizer.THEMES[theme]
    rows = []
    for fg, bg, need, what in PAIRS:
        got = contrast(pal[fg], pal[bg])
        rows.append((f"{what}  ({fg} on {bg})", got, need, got >= need))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--theme", default=None, help="默认全部")
    ap.add_argument("--no-icons", action="store_true")
    ap.add_argument("--keyword", default="关键对话")
    ap.add_argument("--text", default="观点不同、风险很高、情绪激烈的对话，"
                                      "人们往往选择逃避，或者处理得很糟。")
    ap.add_argument("--out", default="/tmp/b2v_themes")
    a = ap.parse_args()

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    themes = [a.theme] if a.theme else ["ink", "paper", "blue"]

    print("═" * 66)
    print("对比度体检（WCAG；4.5 = 正文级，3.0 = 大字/次信息级）")
    print("═" * 66)
    for t in themes:
        rows = audit(t)
        bad = [r for r in rows if not r[3]]
        flag = "❌ 有未达标" if bad else "✓ 全部达标"
        print(f"\n【{t}】{visualizer.THEMES[t]['bg']} 底  —  {flag}")
        for what, got, need, ok in rows:
            print(f"   {'✓' if ok else '❌'} {what:34} {got:5.2f} : 1  (需 ≥{need})")

    print("\n" + "═" * 66)
    print("渲染预览卡")
    print("═" * 66)
    for t in themes:
        p = visualizer.PillowProvider(theme=t, icons=not a.no_icons, allow_network=False)
        scene = SimpleNamespace(keyword=a.keyword, text=a.text, concept="")
        path = p.card(scene, idx=1, out_dir=out)
        Path(path).rename(out / f"card_{t}.png")
        print(f"  ✓ {t:6} → {out}/card_{t}.png")

    print(f"\n全部产出在 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

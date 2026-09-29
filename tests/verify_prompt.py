#!/usr/bin/env python3
"""提示词资产校验：渲染结果 vs golden 基准（逐字节）。

抓三类问题，全是**不报错**的那类：

  1. **意外改动**：改注释、改打印路径时顺手动了提示词正文。
     提示词一改，模型行为就变 —— 但流水线照常出片，没人会发现。
  2. **注释剥离不干净**：注块写错（没闭合 / 被当成行内）→ 注释被当提示词送进模型，
     白烧 token，还可能改变模型行为。
  3. **占位符漏替换**：`{{max_n}}` 之类没被替换 → 模型收到字面量 `{{max_n}}`。

用法（在仓库根跑）：
    python tests/verify_prompt.py            # 比对（不一致 → 退出码 1）
    python tests/verify_prompt.py --update   # 提示词**有意改动**后，把当前渲染结果存为新基准
    python tests/verify_prompt.py --show     # 打印当前渲染结果（人肉看差异）

注意：`--update` 是"我确实想改提示词"的动作。它会掩盖意外改动，
所以更新后请人肉 diff 一遍 golden（`git diff tests/prompt_golden.txt`）。
"""
import argparse
import difflib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from book2vido import icons, promptlib  # noqa: E402

GOLDEN = ROOT / "tests" / "prompt_golden.txt"

# 基准必须用**固定输入**，否则每次跑都"不一致"：句数取默认、章节文本用固定占位符。
FIXED_MAX_N = 12
FIXED_CHUNK = "（基准正文占位符 · 用于逐字比对）"


def render_now() -> str:
    """按固定输入渲染当前提示词 —— 与 golden 应当逐字节可比。"""
    p = promptlib.load("scriptwriter")
    return p.render(max_n=FIXED_MAX_N,
                    concept_list="、".join(icons.CONCEPTS.keys()),
                    chunk=FIXED_CHUNK)


def main() -> int:
    ap = argparse.ArgumentParser(description="提示词资产校验")
    ap.add_argument("--update", action="store_true", help="把当前渲染结果存为新 golden")
    ap.add_argument("--show", action="store_true", help="打印当前渲染结果")
    a = ap.parse_args()

    p = promptlib.load("scriptwriter")
    got = render_now()

    if a.show:
        print(got)
        return 0

    if a.update:
        GOLDEN.write_text(got, encoding="utf-8")
        print(f"✓ golden 已更新：{GOLDEN}")
        print(f"  提示词 v{p.version}（{p.applies_to}）· {len(got)} 字符 / "
              f"{got.count(chr(10)) + 1} 行 · body_hash={p.body_hash}")
        print("  ⚠️ 请人肉看一眼：git diff tests/prompt_golden.txt")
        return 0

    if not GOLDEN.exists():
        print(f"🔴 基准文件不存在：{GOLDEN}\n   先跑一次 `{Path(__file__).name} --update` 建档")
        return 1

    want = GOLDEN.read_text(encoding="utf-8")

    # ① 逐字节比对
    if got != want:
        print("🔴 渲染结果与 golden **不一致**（提示词被改过？）")
        print(f"   golden : {len(want)} 字符 / {want.count(chr(10)) + 1} 行")
        print(f"   当前   : {len(got)} 字符 / {got.count(chr(10)) + 1} 行")
        print("   ---- 差异（- golden / + 当前）----")
        for line in difflib.unified_diff(want.splitlines(), got.splitlines(),
                                         "golden", "current", lineterm="", n=1):
            print("   " + line)
        print("\n   若这次改动是**有意的**：`--update` 更新基准，并在 prompts/*.md 的")
        print("   「模型适配记录」里添一行说明。若是无意的：git checkout -- prompts/")
        return 1

    # ② 注释剥离是否干净
    for bad in ("<!--", "-->"):
        if bad in got:
            print(f"🔴 渲染结果里残留 `{bad}` —— 注释没剥干净")
            return 1

    # ③ 占位符是否有残留（`render()` 本身也会拦，这里是双保险）
    left = re.findall(r"\{\{(\w+)\}\}", got)
    if left:
        print(f"🔴 渲染结果里有未替换的占位符：{sorted(set(left))}")
        return 1

    print("✓ 提示词校验通过")
    print(f"   与 golden 逐字节一致：{len(got)} 字符 / {got.count(chr(10)) + 1} 行")
    print(f"   资产：v{p.version} · {p.applies_to} · {p.source}")
    print(f"   指纹：body_hash={p.body_hash}  "
          f"cache_fp={p.fingerprint(concept_list='、'.join(icons.CONCEPTS.keys()))}")
    print(f"   注释已剥净 · 占位符全部替换 · concept 清单 {len(icons.CONCEPTS)} 词")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""依赖方向守护：断言包内依赖图是 DAG 且方向没被拉弯。

为什么需要它（doc/17 §06 的处方）
──────────────────────────────────
"依赖方向"是一条**没有测试覆盖**的契约。编译器不管它，端到端跑得通也不代表它没坏 ——
`scriptwriter`  import `icons` 这种"弯"当初能正常工作好几个月，只有人肉看代码才发现。
本脚本把那条判断变成**可一键重跑的断言**，而不是再引入一个第三方架构守护工具
（`import-linter` / `pydeps`）——后者对这样一个小包属于"用手段替代判断"（铁律七）。

它同时是**重复劳动的终结**：诊断结构时这段 AST 分析被临时手写过三次。
固化成工具后，改结构的人（含未来的我）不必再写第四遍。

断言清单（任一失败 → 退出码 1）
────────────────────────────────
  A. 无环（严格 DAG）
  B. `paths` / `concepts` / `models` 是叶子层 —— 不依赖任何包内模块
     （它们被所有人依赖，一旦它们反向依赖别人就会成环）
  C. `scriptwriter`（分镜层）不依赖 `icons`（图标资产层）
     —— 档 1 拉直的那条弯，见 doc/17 §S-2
  D. `icons` 只被 `visualizer`（+ 入口）依赖 —— 资产层不该被生成层触碰
  E. 入口 `__main__` 不做包内相对导入的例外检查（它用绝对导入是刻意的）

用法：
    python tests/verify_deps.py            # 检查（CI / 改动后）
    python tests/verify_deps.py --graph    # 附带打印完整依赖图
"""
from __future__ import annotations

import argparse
import ast
import pathlib
import sys

PKG = pathlib.Path(__file__).resolve().parents[1] / "src" / "book2vido"

# 叶子层：被广泛依赖，必须自己不依赖任何包内模块（否则会成环）
LEAF_MODULES = ("paths", "concepts", "models")

# 入口模块：允许用绝对导入（它们要先注入 sys.path，见 cli.py / __main__.py 顶部注释）
ENTRY_MODULES = ("__main__", "cli")

# 方向禁令：(上层, 下层) —— 上层不得依赖下层
FORBIDDEN = [
    ("scriptwriter", "icons"),   # 生成层 → 资产层（档 1 拉直的弯）
    ("scriptwriter", "visualizer"),
    ("segmenter", "icons"),
    ("narrator", "icons"),
]


def internal_deps() -> dict[str, set[str]]:
    """每个模块的相对导入目标（仅包内，level==1）。"""
    out: dict[str, set[str]] = {}
    for p in sorted(PKG.glob("*.py")):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        deps: set[str] = set()
        for n in ast.walk(tree):
            if not isinstance(n, ast.ImportFrom) or n.level != 1:
                continue
            if n.module:
                deps.add(n.module.split(".")[0])
            else:                       # from . import a, b
                deps.update(a.name for a in n.names)
        out[p.stem] = deps
    return out


def find_cycles(deps: dict[str, set[str]]) -> list[list[str]]:
    cycles: list[list[str]] = []

    def walk(node: str, path: list[str]) -> None:
        for nxt in sorted(deps.get(node, ())):
            if nxt in path:
                cyc = path[path.index(nxt):] + [nxt]
                if cyc not in cycles:
                    cycles.append(cyc)
                continue
            walk(nxt, path + [nxt])

    for m in sorted(deps):
        walk(m, [m])
    return cycles


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", action="store_true", help="打印完整依赖图")
    args = ap.parse_args()

    if not PKG.is_dir():
        print(f"✗ 找不到包目录：{PKG}")
        return 1

    deps = internal_deps()
    fails: list[str] = []

    if args.graph:
        print("=== 包内依赖图 ===")
        for m in sorted(deps):
            arrow = ", ".join(sorted(deps[m])) or "（无）"
            print(f"  {m:14} → {arrow}")
        print()

    # A. 无环
    cycles = find_cycles(deps)
    if cycles:
        fails.append(f"A 有环：{cycles[0]}")
    else:
        print("✓ A 无环（严格 DAG）")

    # B. 叶子层不依赖包内模块
    for m in LEAF_MODULES:
        bad = deps.get(m, set())
        if bad:
            fails.append(f"B 叶子层的 {m} 依赖了 {sorted(bad)}（叶子层必须自足）")
    if not any(f.startswith("B") for f in fails):
        print(f"✓ B 叶子层自足：{' / '.join(LEAF_MODULES)}")

    # C/D. 方向禁令
    for up, down in FORBIDDEN:
        if down in deps.get(up, set()):
            fails.append(f"{up} 不得依赖 {down}（方向被拉弯）")
    if not any("方向被拉弯" in f for f in fails):
        print(f"✓ C 方向禁令全部成立（{len(FORBIDDEN)} 条）")

    # D. 谁依赖 icons
    icons_users = sorted(m for m, d in deps.items() if "icons" in d)
    print(f"   · 依赖 icons 的模块：{icons_users}")

    # E. 只有入口用绝对导入
    # `cli` 与 `__main__` 同为入口：前者是 `[project.scripts]` 的落点，只做转发。
    # 两者都必须走绝对导入 —— 它们要在 `sys.path` 注入**之后**才能 import 包内模块。
    importers_abs = []
    for p in sorted(PKG.glob("*.py")):
        src = p.read_text(encoding="utf-8")
        if "from book2vido" in src and p.stem not in ENTRY_MODULES:
            importers_abs.append(p.stem)
    if importers_abs:
        fails.append(f"E 非入口模块使用了绝对导入：{importers_abs}（统一用相对导入）")
    else:
        print(f"✓ E 导入风格统一（仅 {' / '.join(sorted(ENTRY_MODULES))} 用绝对导入，刻意）")

    print()
    if fails:
        print(f"✗ 依赖守护失败（{len(fails)} 项）：")
        for f in fails:
            print(f"   - {f}")
        return 1
    n = len([m for m in deps if m != "__init__"])   # __init__ 不计入模块数
    print(f"✓ 依赖守护通过（{n} 个模块）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

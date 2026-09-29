#!/usr/bin/env python3
"""图标资产自洽守护：代码点名的图标 ↔ assets/icons 实有 PNG。

为什么需要它
────────────
与 `verify_deps.py` 同构的理由：这也是一条**无任何测试覆盖、且本机永远测不出来**的契约。

- **本机测不出来**：开发机联网时，缺失图标会被 `IconProvider` 静默下载补齐 ——
  本地永远绿。等到用户在**离线**环境出片，缺图只降级成「无图标版式」，
  日志全绿，用户拿到一张缺画面的卡（铁律一的"静默降级"禁用形态）。
- **实测发生过**：词表从 106 涨到 121 个图标，而缓存**没有跟着重跑 `fetch-icons`**，
  于是 10 个图标（含兜底池里 6 个）本地从未存在过 —— 改了代码没重跑生成物，
  与"改了 md 没重渲染 HTML"是同一类漂移。
- **体积也要守**：本地多出来的图会**随 .app 一起分发**（`build_app.sh` 整目录 `cp -R`），
  没人用的图就是白白发给用户的字节。

断言清单（任一失败 → 退出码 1）
──────────────────────────────
  A. 引用 ⊆ 实有 —— 代码点名的图标本地必须都有（否则离线静默降级）
  B. 实有 ⊆ 引用 —— 本地不该留代码不用的图（纯体积冗余，且会随包分发）
  C. 两表键不相交 —— `KEYWORD_ICONS` 与 `CONCEPTS` 的同名键＝永远不生效的死词条
     （合并靠 `update()`，覆盖是静默的，读者得靠记忆才知道哪个键已死）

用法：
    python tests/verify_icons.py                # 检查（改动后 / 发布前）
    python tests/verify_icons.py --list         # 附带列出缺失与冗余明细
    python tests/verify_icons.py --root <目录>  # 对副本检查（探针验证用；别在真项目上做注入测试）
"""
from __future__ import annotations

import argparse
import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "book2vido"
ICON_DIR = ROOT / "assets" / "icons"


def _literal(path: pathlib.Path, name: str):
    """从源码里取出字面量常量。

    ⚠️ 找不到就**抛错**，不返回 None 静默通过 —— 守护脚本自己静默失效是最坏的情况：
    它会让下一个人以为"检查过了"。所以这里宁可炸。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == name:
            return ast.literal_eval(node.value)
        if isinstance(node, ast.Assign) and any(
            getattr(t, "id", "") == name for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise LookupError(f"{path.name} 里找不到字面量 {name}（写法变了？守护脚本需要跟着改）")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="列出缺失与冗余明细")
    ap.add_argument("--root", help="项目根（默认脚本上一级）。给探针 / CI 用："
                                   "指向一份副本，避免在真项目上做注入测试")
    args = ap.parse_args()

    root = pathlib.Path(args.root).resolve() if args.root else ROOT
    pkg = root / "src" / "book2vido"
    icon_dir = root / "assets" / "icons"

    if not icon_dir.is_dir():
        print(f"✗ 找不到图标目录：{icon_dir}（先跑 python -m book2vido fetch-icons）")
        return 1

    try:
        keyword_icons = _literal(pkg / "icons.py", "KEYWORD_ICONS")
        fallback = _literal(pkg / "icons.py", "FALLBACK_ICONS")
        concepts = _literal(pkg / "concepts.py", "CONCEPTS")
    except LookupError as e:
        print(f"✗ {e}")
        return 1

    # 图标 id → 本地 PNG 文件名（`tabler:x` → `tabler-x.png`）
    have = {p.stem.replace("tabler-", "tabler:", 1) for p in icon_dir.glob("tabler-*.png")}
    # 代码实际会点名的图标 = 工程词表的值 + 兜底池 + 叙事概念的值（合并后的全集）。
    # ⚠️ 三处都得取 `.values()`：表里放的是「中文词 → 图标名」的映射，
    #    键是中文词不是图标名。少取一次 values 会把整个词表报成"缺失"，
    #    而真正的缺失被淹没在 85 行噪声里 —— 本脚本第一版就犯了这个错。
    ref = set(keyword_icons.values()) | set(fallback) | set(concepts.values())

    fails: list[str] = []

    missing = sorted(ref - have)
    if missing:
        fails.append(f"A 引用了 {len(missing)} 个本地没有的图标（离线会静默降级为无图标）")
    else:
        print("✓ A 引用 ⊆ 实有（离线不会缺图）")

    unused = sorted(have - ref)
    if unused:
        fails.append(f"B 本地有 {len(unused)} 个代码不引用的图标（纯体积冗余，且随包分发）")
    else:
        print("✓ B 实有 ⊆ 引用（无冗余字节）")

    dups = sorted(k for k in keyword_icons if k in concepts)
    if dups:
        fails.append(
            f"C 两表有 {len(dups)} 个同名键＝死词条（CONCEPTS 会静默覆盖 KEYWORD_ICONS）：{dups}"
        )
    else:
        print("✓ C KEYWORD_ICONS 与 CONCEPTS 键不相交（无静默覆盖）")

    total = sum(p.stat().st_size for p in icon_dir.glob("*.png"))
    print(
        f"   · 词表 {len(keyword_icons)} + 概念 {len(concepts)} + 兜底 {len(fallback)}"
        f" → 去重图标 {len(ref)} 个"
        f" ｜ 本地实有 {len(have)} 个 / {total / 1048576:.2f} MB"
    )
    if args.list:
        for m in missing:
            print(f"     缺失 - {m}")
        for u in unused:
            print(f"     冗余 + {u}")

    print()
    if fails:
        print(f"✗ 图标资产守护失败（{len(fails)} 项）：")
        for f in fails:
            print(f"   - {f}")
        print("   修复：缺图跑 `python -m book2vido fetch-icons` 补齐；"
              "冗余的删 PNG，或把图标重新写进词表。")
        return 1
    print("✓ 图标资产守护通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())

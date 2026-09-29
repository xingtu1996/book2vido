"""出片下限守卫的自检：`segmenter.insufficient_reason` 判据是否真的成立。

守的是什么（为什么需要这个脚本）：
  上游只有「空文本」的守卫，挡不住「只有 5 个字」的章节。而「出 N 句」是硬约束，
  料不够时模型只能同义反复或编造 —— 实测 22 字的「附录D」被出了 12 句
  （内容全是「附录D讲作者团队信息 / 附录D提供作者背景」这类重复），12 张卡同时退化到 2 个图标。
  **本机永远测不出来**：跑测试用的是正经长文，没人拿附录去测；只有 `--all` 跑整本书才踩到。

两类检查（第二类需要传书）：
  ① 判据函数本身 —— 边界、标点口径、空/纯标点。这些是**可证伪**的：
     谁把 _SENT_END 改成包含逗号、或把比较改成 `>`，这里就会红。
  ② 真实书上跑一遍 —— 断言「正文章零误伤」。这条独立于实现：
     判据收紧过头（比如阈值拉到 100 句）会让正文章被拦，这里会红。

用法：
    python tests/verify_gate.py                      # 只跑 ①（无外部依赖）
    python tests/verify_gate.py <book.pdf>           # ① + ②（真实书截面）

    python tests/verify_gate.py <book.pdf> --list    # 附带列出每条拦截明细
"""
from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from book2vido import extractor, outline, segmenter  # noqa: E402
from book2vido.config import load  # noqa: E402
from book2vido.paths import project_root  # noqa: E402

# 目标句数**从配置读，不在这里写死**：判据的核心就是「原文句数 ≥ max_sentences」。
# 配置改了 12→8 而这里还写 12，脚本就会去验证一个已经不再生效的口径——
# 本项目抓过多次「改了不生效」（错题库 L-17/L-19 同族），故前置堵死。
_CFG = project_root() / "config.yaml"
TARGET = load(str(_CFG) if _CFG.exists() else None)["limits"]["max_sentences"]


def _mk(n: int) -> str:
    """造 n 个完整的中文句子。"""
    return "".join(f"这是第{i}个完整的测试句子。" for i in range(1, n + 1))


# (说明, 文本, 目标句数, 期望够不够)
CASES: list[tuple[str, str, int, bool]] = [
    # —— 实测踩过的真实输入（回归锚点，这两条最重要）
    ("22 字标题（附录D，实测被编出 12 句）", "附录D 本书作者团队 其他畅销作品推荐", 12, False),
    ("5 字（参考文献）", "参考文献", 12, False),
    ("46 字单句（附录C）", "想让自己的人生变得更完美吗", 12, False),
    # —— 边界：正好 / 差一句
    ("恰好 12 句 → 放行", _mk(12), 12, True),
    ("11 句 → 拦（一句话换一句话）", _mk(11), 12, False),
    # —— 空与纯标点
    ("空串", "", 12, False),
    ("纯空白", "   \n\t ", 12, False),
    ("纯标点（切完没有内容）", "。。。。。。", 12, False),
    # —— 标点口径：句末才算，句内停顿不算
    ("逗号/分号/冒号不切句", "很长的一段话，中间有逗号；还有分号：但只有一个句号。", 12, False),
    ("英文问号/叹号算句末", "Really? Yes! Okay.", 3, True),
    ("问号叹号也算句末", "这样对吗？真的吗！好吧。", 3, True),
    # —— 半角点号刻意不收：它在中文里常是小数点/编号/缩写/URL。
    #    这条是**设计决策的钉子**：谁把 `.` 加进 _SENT_END，这里就会红。
    ("半角点号不切句（3.14 / 1.2.3 不算句末）", "圆周率是 3.14。版本号 1.2.3 而已。", 3, False),
    # —— 目标句数不同时的行为（判据不该写死 12）
    ("同一文本、目标降到 2 句 → 放行", "只有一句完整的话。还有第二句。", 2, True),
    ("同一文本、目标升到 3 句 → 拦", "只有一句完整的话。还有第二句。", 3, False),
]


def check_function() -> int:
    print("=" * 70)
    print("① 判据函数（可证伪的边界断言）")
    print("=" * 70)
    bad = 0
    for desc, text, target, expect_ok in CASES:
        reason = segmenter.insufficient_reason(text, target)
        got_ok = reason is None
        n = segmenter.sentence_count(text)
        flag = "✓" if got_ok == expect_ok else "✗"
        if got_ok != expect_ok:
            bad += 1
        print(f"  {flag} {desc}")
        print(f"      句数 {n} / 目标 {target} → {'放行' if got_ok else '拦'}"
              f"（期望 {'放行' if expect_ok else '拦'}）")
        if reason:
            print(f"      原因：{reason}")
    print(f"\n  {'✅ 全部通过' if not bad else f'🔴 {bad} 条不符'}")
    return bad


def check_book(pdf: str, show_list: bool) -> int:
    print()
    print("=" * 70)
    print(f"② 真实书截面：{pathlib.Path(pdf).name}")
    print("=" * 70)
    pages = extractor.resolve_pages(extractor.lazy_pages(pdf))
    doc = outline.build(pdf)

    rows, blocked = [], []
    for ch in doc.chapters:
        if ch.index == 0:                      # 0 = 小节，不参与出片
            continue
        text = segmenter.slice_chapter(pages, ch, 2500)
        n = segmenter.sentence_count(text)
        reason = segmenter.insufficient_reason(text, TARGET)
        rows.append((ch.index, ch.title, len(text), n, reason is None))
        if reason:
            blocked.append((ch.index, ch.title, len(text), n))

    print(f"  顶层条目 {len(rows)} 条 ｜ 拦下 {len(blocked)} 条")
    for idx, title, ln, n, ok in rows:
        mark = "✓" if ok else "⊘"
        print(f"  {mark} [{idx:>2}] {title[:26]:<26} {ln:>5} 字 / {n:>3} 句")

    # —— 独立断言：正文章零误伤（判据收紧过头会在这里红）
    body = [r for r in rows if "章" in r[1][:4] and r[1].startswith("第")]
    body_blocked = [r for r in body if not r[4]]
    print()
    print(f"  正文章 {len(body)} 条 ｜ 被拦 {len(body_blocked)} 条")
    if body_blocked:
        print("  🔴 正文章被误伤（判据过严）：")
        for idx, title, ln, n, _ in body_blocked:
            print(f"     · [{idx}] {title}（{ln} 字 / {n} 句）")
        return 1
    print("  ✅ 正文章零误伤")

    # —— 拦截项应全部是「一句话都凑不满」的料
    worst = max((n for _, _, _, n, _ in rows), default=0)
    if blocked and max(b[3] for b in blocked) >= TARGET:
        print("  🔴 拦下的条目里有句数达标的（实现与判据不一致）")
        return 1
    print(f"  ✅ 拦截项句数上界 {max((b[3] for b in blocked), default=0)} < 目标 {TARGET}"
          f"（全书最大 {worst} 句）")

    if show_list and blocked:
        print()
        print("  —— 拦截明细 ——")
        for idx, title, ln, n in blocked:
            print(f"     [{idx:>2}] {title} ｜ {ln} 字 / {n} 句"
                  f" ｜ 缺口 {TARGET - n} 句")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("book", nargs="?", help="可选：一本 PDF，跑真实截面检查")
    ap.add_argument("--list", action="store_true", help="列出拦截明细")
    a = ap.parse_args()

    bad = check_function()
    if a.book:
        p = pathlib.Path(a.book)
        if not p.exists():
            print(f"\n🔴 找不到书：{a.book}")
            return 1
        bad += check_book(str(p), a.list)

    print()
    print("=" * 70)
    print("✅ 全部通过" if not bad else f"🔴 {bad} 项不符")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

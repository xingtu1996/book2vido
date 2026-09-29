"""segmenter 可重跑验证：覆盖 5 条行为 + 真实样本 TC-07 长章均匀采样。

运行：
  PYTHONPATH=src python3 tests/verify_segmenter.py   # 在仓库根执行

注：TC-07 需要样例 PDF（samples/books/关键对话.pdf，版权原因不入库）。
    缺样本时该用例自动跳过，其余 5 条照常跑。
"""
import os
import sys
from pathlib import Path

# 自包含：即使没设 PYTHONPATH 也能导入 book2vido
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "src"))

from book2vido.models import Chapter, OutlineDoc  # noqa: E402
from book2vido.segmenter import slice_chapter, pick  # noqa: E402

PDF = str(Path(__file__).resolve().parent.parent / "samples" / "books" / "关键对话.pdf")


def test_short():
    # 短章：总量 <= max_chars → 原样返回，无省略标记
    pages = ["第一章开头\n\n这是第一段。\n\n这是第二段。"]
    ch = Chapter(index=1, title="短章", start_page=1, end_page=1)
    out = slice_chapter(pages, ch, max_chars=2500)
    assert out == pages[0], repr(out)
    assert "……" not in out
    print("✅ 行为1 短章原样返回")


def test_long():
    # 长章：34 页，远超 max_chars → 长度<=2500 且首/中/尾均被代表
    pages = []
    for i in range(34):
        marker = ""
        if i == 0:
            marker = " HEADMARK_0001"
        elif i == 17:
            marker = " MIDMARK_0002"
        elif i == 33:
            marker = " TAILMARK_0003"
        pages.append(
            f"第{i + 1}页第一段{marker}：" + ("内容" * 30) + "\n\n"
            f"第{i + 1}页第二段：" + ("内容" * 30) + "\n\n"
            f"第{i + 1}页第三段：" + ("内容" * 30)
        )
    ch = Chapter(index=2, title="长章", start_page=1, end_page=34)
    out = slice_chapter(pages, ch, max_chars=2500)
    assert len(out) <= 2500, len(out)
    assert "HEADMARK_0001" in out, "首段未代表"
    assert "MIDMARK_0002" in out, "中段未代表"
    assert "TAILMARK_0003" in out, "尾段未代表"
    print(f"✅ 行为2 长章均匀采样（{len(out)} 字，首中尾均代表）")


def test_oob():
    # 页码越界：end_page 超过 len(pages) → 裁剪到有效范围，不抛异常
    pages = ["仅此一页内容"]
    ch = Chapter(index=3, title="越界章", start_page=1, end_page=99)
    out = slice_chapter(pages, ch, max_chars=2500)
    assert out == pages[0], repr(out)
    print("✅ 行为3 页码越界裁剪")


def test_empty():
    # 空章：页码范围无文本（或只有空白）→ 返回 ""；完全越界也返回 ""
    pages = ["", "   ", ""]
    ch = Chapter(index=4, title="空章", start_page=1, end_page=3)
    out = slice_chapter(pages, ch, max_chars=2500)
    assert out == "", repr(out)
    ch2 = Chapter(index=5, title="全越界", start_page=50, end_page=60)
    assert slice_chapter(pages, ch2) == ""
    print("✅ 行为4 空章返回空串")


def test_pick():
    # pick 便捷封装：取得到返回片段，取不到（序号越界）返回 ""
    doc = OutlineDoc(source_path="x", total_pages=3, origin="whole-doc", chapters=[
        Chapter(index=1, title="甲", start_page=1, end_page=1),
        Chapter(index=2, title="乙", start_page=2, end_page=2),
    ])
    pages = ["甲内容", "乙内容", "丙内容"]
    assert pick(pages, doc, 1) == "甲内容"
    assert pick(pages, doc, 2) == "乙内容"
    assert pick(pages, doc, 9) == ""
    print("✅ 行为5 pick 便捷封装")


def load_pages(pdf: str) -> list[str]:
    # 优先用 Unit A 的 extractor.extract_pages；它并行未就绪时退回 pypdf 直接取页文本
    try:
        from book2vido import extractor
        return extractor.extract_pages(pdf)
    except Exception:
        from pypdf import PdfReader
        return [pg.extract_text() or "" for pg in PdfReader(pdf).pages]


def load_doc(pdf: str) -> OutlineDoc:
    # 优先用 Unit A 的 outline.build；未就绪时退回 pypdf 书签自己算页码区间
    try:
        from book2vido import outline
        return outline.build(pdf)
    except Exception:
        return _fallback_doc(pdf)


def _fallback_doc(pdf: str) -> OutlineDoc:
    from pypdf import PdfReader
    reader = PdfReader(pdf)
    flat = []

    def walk(nodes, depth):
        for node in nodes:
            if isinstance(node, list):
                walk(node, depth + 1)
                continue
            try:
                pg = reader.get_destination_page_number(node)  # 0-based
            except Exception:
                continue
            if pg is None:
                continue
            title = node.title
            if isinstance(title, bytes):
                title = title.decode("utf-8", "ignore")
            flat.append((depth, pg + 1, str(title)))

    walk(reader.outline, 0)
    flat.sort(key=lambda x: x[1])
    chs = []
    for i, (depth, sp, title) in enumerate(flat):
        ep = flat[i + 1][1] - 1 if i + 1 < len(flat) else len(reader.pages)
        chs.append(Chapter(index=i + 1, title=title, start_page=sp, end_page=ep,
                           depth=depth, source="outline"))
    return OutlineDoc(source_path=pdf, total_pages=len(reader.pages),
                      origin="pdf-outline", chapters=chs)


def test_tc07():
    # TC-07：真实样本里页数最多的顶层章，断言 ≤2500 且首中尾都有内容
    # 样例 PDF 不入库（版权）→ 缺样本时跳过，不影响其余用例
    if not os.path.exists(PDF):
        print(f"⏭  TC-07 跳过：缺样例 {PDF}")
        return
    pages = load_pages(PDF)
    doc = load_doc(PDF)
    top = doc.top()
    assert top, "无顶层章"
    long_ch = max(top, key=lambda c: c.pages)
    t = slice_chapter(pages, long_ch, max_chars=2500)
    print(f"TC-07 章「{long_ch.title}」{long_ch.pages} 页 → 片段 {len(t)} 字")
    assert len(t) <= 2500, len(t)
    head, mid, tail = t[:200], t[len(t) // 2 - 100:len(t) // 2 + 100], t[-200:]
    assert head.strip() and mid.strip() and tail.strip(), "首中尾有空"
    print(f"  首60: {head[:60]!r}")
    print(f"  中60: {mid[len(mid) // 2:len(mid) // 2 + 60]!r}")
    print(f"  尾60: {tail[-60:]!r}")
    print("✅ TC-07 长章均匀采样（真实样本）")


def main():
    test_short()
    test_long()
    test_oob()
    test_empty()
    test_pick()
    test_tc07()
    print("\n全部通过")


if __name__ == "__main__":
    main()

"""目录索引：文件 → 章节树。**零 LLM、零幻觉、毫秒级**。

三层兜底，每层都在 `OutlineDoc.origin` 留痕，让上层知道该不该信：
  1. `pdf-outline` —— PDF 内嵌书签（首选，零成本零幻觉）
  2. `regex`       —— 页文本里找页首的「第X章 / Chapter N / Part N」
  3. `whole-doc`   —— 两者皆失败 → 整本当一章。**不编造章节**

不用 LLM 生成目录（方案已否决，见 specs/2026091518-book2vido-chapter/01_analysis.md §三）：
4K ctx 装不下整本书、模型会编章名、还慢。结构本来就在文件里，**读出来比猜出来便宜**。
"""
from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader

from . import extractor
from .models import Chapter, OutlineDoc

# 章节标记（兜底用）。只在**页首**匹配，理由见 _regex_flat。
_CHAPTER_RE = re.compile(
    r"^\s*(第\s*[一二三四五六七八九十百零\d]+\s*[章篇部]"
    r"|Chapter\s+\d+"
    r"|Part\s+[IVXLCDM\d]+)\s*[^\n]{0,40}$"
)


def build(path: str) -> OutlineDoc:
    """文件 → 目录树。三层兜底，永不返回空（最差是「整本当一章」）。"""
    p = Path(path)
    pages = extractor.extract_pages(path)
    total = len(pages)

    # 分章需要「页边界 + 页级标记」两个要素，只有 PDF 具备。非 PDF（MD/长文）没有页
    # 边界，正则最多给出"所有章都在第 1 页"，`_to_chapters` 推出的范围全是 p1-p1，
    # 切片会把整篇重复给每一章——**比粒度粗更糟**。故非 PDF 一律落 whole-doc。
    if p.suffix.lower() == ".pdf":
        try:
            flat = _pdf_flat(PdfReader(str(p)))
        except Exception as e:
            print(f"[warn] PDF 目录读取失败（{e}），退回正则扫描")
            flat = []
        if flat:
            return OutlineDoc(str(p), total, "pdf-outline", _to_chapters(flat, total))

        flat = _regex_flat(pages)
        if flat:
            print(f"[warn] PDF 无内嵌目录，改用正则扫描（命中 {len(flat)} 条）")
            return OutlineDoc(str(p), total, "regex", _to_chapters(flat, total))

    return _whole(p, total)


def save(doc: OutlineDoc, path: str) -> str:
    """落盘。中文不转义——这是「人能读、人能改」的中间产物，不是给人看的摘要。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(doc.to_json(), encoding="utf-8")
    return str(p)


def load(path: str) -> OutlineDoc:
    """读回。文件不存在就让 `FileNotFoundError` 冒上去，不静默返回空目录树。"""
    return OutlineDoc.from_json(Path(path).read_text(encoding="utf-8"))


def render_tree(doc: OutlineDoc) -> str:
    """CLI `list` 的纯文本树。格式刻意做成**机器可断言**：顶层章以 `[ N]` 开头、
    小节以缩进 `·` 开头，验证脚本可 `grep -c '^\\['` 数章数，不必解析散文。"""
    lines = [
        f"目录来源: {doc.origin} ｜ {doc.total_pages} 页 ｜ "
        f"{len(doc.chapters)} 条（顶层 {len(doc.top())} 章）",
        "-" * 56,
    ]
    for c in doc.chapters:
        if c.depth == 0:
            lines.append(f"[{c.index:>3}] p{c.start_page:03d}-p{c.end_page:03d}  {c.title}")
        else:
            lines.append(f"       · p{c.start_page:03d}  {c.title}")
    return "\n".join(lines)


def _pdf_flat(reader: PdfReader) -> list[tuple[int, str, int]]:
    """PDF 内嵌书签 → `[(depth, title, page_1based)]`，保持文档顺序。

    **不能简单递归**：pypdf 的 `outline` 是「Destination 与 list 混排」的树——
    一条 Destination 是章，紧跟其后的 list 是它的小节。递归会把「排在章前面的 list」
    当成章的兄弟，层级就错了。故显式按「章 → 其后的 list」两段式解析。
    """
    try:
        raw = reader.outline
    except Exception:
        return []
    if not raw:
        return []

    out: list[tuple[int, str, int]] = []

    def _dest(item):
        try:
            title = str(getattr(item, "title", "")).strip()
            # pypdf 页码 0-based → 本项目统一 1-based 闭区间
            page = reader.get_destination_page_number(item) + 1
        except Exception:
            return None
        return (title, page) if title else None

    for it in raw:
        if isinstance(it, list):
            for sub in it:
                if isinstance(sub, list):
                    continue
                d = _dest(sub)
                if d:
                    # 前面还没有任何章 → 这些「小节」其实是顶层章（有些 PDF 直接给平铺列表）
                    out.append((1 if out else 0, d[0], d[1]))
        else:
            d = _dest(it)
            if d:
                out.append((0, d[0], d[1]))
    return out


def _looks_like_toc(lines: list[str]) -> bool:
    """判断一页是不是**目录页**：目录长得像清单——行多、且每行短。

    不用「章标记命中 ≥3 条」当判据，是因为目录行尾部带点线引导符 + 页码
    （「第 10 章 案例分析……143」），长度超出章节标题正则上限而匹配失败——实测只命中
    2 条，阈值 3 就漏网，「第 10 章」的页码被取成了目录页 p7。本判据与标记数量无关，
    绕不过去。阈值取自真实样本：目录页 21 行几乎全短行，正文页是 40–70 字的段落。
    """
    if len(lines) < 8:
        return False
    return sum(1 for ln in lines if len(ln) <= 25) >= len(lines) * 0.5


def _regex_flat(pages: list[str]) -> list[tuple[int, str, int]]:
    """扫章节标记。命中 < 2 条即判定失败（1 条多半只是正文提了一嘴）。

    两条启发式，都是被真实 PDF 教出来的：
      ① **只在页首匹配**：正文里「第 3 章讲过…」这类句子不能当章。
      ② **跳过目录页**：收进来会让整章的页码范围全算错（见 `_looks_like_toc`）。
    """
    out: list[tuple[int, str, int]] = []
    for no, text in enumerate(pages, start=1):
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines or _looks_like_toc(lines):
            continue
        if _CHAPTER_RE.match(lines[0]) and len(lines[0]) <= 50:
            if not out or lines[0] != out[-1][1]:
                out.append((0, lines[0], no))
    return out if len(out) >= 2 else []


def _whole(p: Path, total_pages: int) -> OutlineDoc:
    """两者皆失败 → 整本当一章。**宁可粒度粗，不可给错结构。**"""
    return OutlineDoc(str(p), total_pages, "whole-doc",
                      [Chapter(1, p.stem, 1, max(1, total_pages), 0, "whole")])


def _to_chapters(flat: list[tuple[int, str, int]], total_pages: int) -> list[Chapter]:
    """`(depth, title, page)` 扁平序列 → 带页码范围与序号的 `Chapter` 列表。

    ① **页码单调不降**：PDF 目录偶尔乱序或有 0 页项，钳一下；否则 `page_slice` 取到空区间。
    ② **`end_page` = 下一个同级条目 `start_page` - 1**：范围由**目录自身**推导，不靠猜；
       末条用 `total_pages` 收口。这样 `segmenter` 直接切片即可。
    """
    tops = [i for i, (d, _, _) in enumerate(flat) if d == 0]
    if not tops:
        return _whole(Path(""), total_pages).chapters

    pages, last = [], 1
    for _, _, pg in flat:
        last = max(last, max(1, min(total_pages, pg)))
        pages.append(last)

    chapters: list[Chapter] = []
    for n, i in enumerate(tops, start=1):
        stop = tops[n] if n < len(tops) else len(flat)
        start = pages[i]
        end = max(start, pages[tops[n]] - 1) if n < len(tops) else total_pages

        # 章本身（index = 顶层序号，`--chapter N` 以此为准）
        chapters.append(Chapter(n, flat[i][1], start, end, 0, "outline"))

        # 其小节（index 恒为 0：小节不参与点播，只用于 list 展示）
        secs = [j for j in range(i + 1, stop) if flat[j][0] == 1]
        for k, j in enumerate(secs):
            s_start = pages[j]
            s_end = max(s_start, pages[secs[k + 1]] - 1) if k + 1 < len(secs) else end
            chapters.append(Chapter(0, flat[j][1], s_start, s_end, 1, "outline"))
    return chapters


if __name__ == "__main__":
    # 自检：python -m book2vido.outline <文件>
    import sys

    print(render_tree(build(sys.argv[1])))

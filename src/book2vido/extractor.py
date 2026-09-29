"""文本抽取：PDF / Markdown / 长文 → 纯文本 / 页文本。本地，免费。"""
import re
from pathlib import Path
from pypdf import PdfReader


def extract_pages(path: str) -> list[str]:
    """→ 每页的文本列表（0-based：`pages[0]` 即第 1 页）。

    为什么不复用 `extract()`：`extract()` 把页 join 成一个字符串，**页边界信息就丢了**。
    而「第 3 章在第几页」必须靠页边界定位——分章（T2V-002）的第一块基石就是这个函数。
    """
    p = Path(path)
    if p.suffix.lower() == ".pdf":
        return [(pg.extract_text() or "") for pg in PdfReader(str(p)).pages]
    # MD / 长文没有页概念 → 整篇当一页。**后果**：非 PDF 一律走 outline 的 whole-doc
    # 分支（无法分章）——没有页边界就没有「章→页」映射，硬分章会让每章都切片到整篇。
    return [p.read_text(encoding="utf-8", errors="ignore")]


def extract(path: str) -> str:
    """整篇纯文本。保持原语义不变（外部脚本在用）。"""
    return "\n".join(extract_pages(path))


def lazy_pages(path: str):
    """延迟抽页：返回零参可调用对象，首次调用才真解析（AC-11）。

    抽 348 页要 ~6s，而命中缓存（text.txt）的章根本不需要全文。放在 extractor 里
    是因为它就是「抽页」这件事的懒版本，属于本模块职责，不是编排的事。
    """
    box: dict = {}

    def get() -> list[str]:
        if "v" not in box:
            box["v"] = extract_pages(path)
        return box["v"]

    return get


def resolve_pages(pages):
    """兼容两种传法：已抽好的 `list[str]`，或 `lazy_pages()` 这类零参可调用对象。"""
    return pages() if callable(pages) else pages


def page_slice(pages: list[str], start_page: int, end_page: int) -> str:
    """按 **1-based 闭区间**取页文本。

    越界自动裁剪而不抛异常：PDF 目录里的页码偶尔会比实际页数多 1（书末索引页），
    为这种小瑕疵中断整条出片链路不划算。
    """
    lo = max(1, start_page)
    hi = min(len(pages), end_page)
    if lo > hi:
        return ""
    return "\n".join(pages[lo - 1:hi])


def chapters(text: str, max_n: int = 50) -> list[str]:
    """按空行分段，返回前 max_n 段（用于规则降级取料）。"""
    parts = [s.strip() for s in re.split(r"\n\s*\n", text) if s.strip()]
    return parts[:max_n]


def body(text: str, min_skip: int = 150) -> str:
    """定位正文起点，跳过版权页/献词/目录/序言等噪声区。

    ⚠️ **已废弃（T2V-002）**：这是「猜」正文在哪，不是「读」结构。
    分章链路已改由 `outline.py` 读 PDF 内嵌目录定位，不再需要猜。
    函数保留（不删）：外部脚本与 `RuleFallbackProvider` 的降级取料仍在用——
    本项目回滚条件是「只增不删」（02_requirements §五）。

    启发式：找第一个正式章节标记（第X章 / Part N / Chapter N / 第一部分…），
    从其位置截取；找不到则退路跳过前 1/6。
    """
    pat = re.compile(
        r"(第\s*[一二三四五六七八九十百零\d]+\s*章"
        r"|Part\s+[IVXLCDM\d]+"
        r"|Chapter\s+\d+"
        r"|第一部分|第一编|卷[一二三四]\s)"
    )
    m = pat.search(text)
    if m and m.start() > min_skip:
        return text[m.start():]
    return text[len(text) // 6:]

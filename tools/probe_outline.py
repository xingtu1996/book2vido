"""探测 PDF 书签（outline）结构的一次性小工具。

用法：
  python tools/probe_outline.py [<pdf 路径>]
默认取仓库内样例 samples/books/关键对话.pdf（版权原因不入库，需自备）。
"""
import sys
from pathlib import Path

from pypdf import PdfReader

_HERE = Path(__file__).resolve().parent
p = str(Path(sys.argv[1]) if len(sys.argv) > 1
        else _HERE.parent / "samples" / "books" / "关键对话.pdf")
r = PdfReader(p)
print(f"页数: {len(r.pages)}")
try:
    ol = r.outline
except Exception as e:
    print("outline 读取失败:", e); sys.exit()
print(f"outline 顶层条数: {len(ol) if ol else 0}")

def walk(items, depth=0, n=[0]):
    for it in items:
        if isinstance(it, list):
            walk(it, depth+1, n)
        else:
            try:
                title = getattr(it, "title", str(it))
                page = r.get_destination_page_number(it)
            except Exception as e:
                title, page = f"<解析失败 {e}>", "?"
            n[0] += 1
            if n[0] <= 40:
                print("  " * depth + f"[p{page}] {title}")
    return n[0]

if ol:
    total = walk(ol)
    print(f"\n--- 目录总条数: {total} ---")
else:
    print("\n无内嵌目录（outline 为空）")

# 对照：看正文里有没有「第X章」这类文字标记
txt = "\n".join((pg.extract_text() or "") for pg in r.pages[:20])
import re
hits = re.findall(r"第\s*[一二三四五六七八九十百零\d]+\s*章[^\n]{0,30}", txt)
print(f"\n正文前 20 页的「第X章」命中: {len(hits)} 条")
for h in hits[:8]: print("  ", h.strip()[:50])

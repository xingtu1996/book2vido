# 02 · 文本抽取

## 角色
把输入（PDF / Markdown / 长文）变成纯文本，喂给 LLM。

## 选型
- **pypdf**（本地，免费）：抽取文本型 PDF。无需 OCR。
- OCR 兜底：扫描件用 `pdf2image` + 本地 OCR（Tesseract 中文模型）或云端（仅非敏感草稿）。

## 实测样本
- `book2vido/关键对话.pdf` = 《关键对话：如何高效能沟通》第2版，**348 页文本型**（非聊天记录），pypdf 直抽即可。
- 公众号长文 / Markdown：直接读文本，零抽取成本。

## 接入
```python
from pypdf import PdfReader
text = "\n".join((p.extract_text() or "") for p in PdfReader(path).pages)
```

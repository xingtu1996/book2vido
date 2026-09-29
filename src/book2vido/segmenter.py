"""章节切分：把某一章的页文本切成送给本地 LLM 的片段（≤ max_chars 字）。

为什么这层存在（T2V-002 病根除根）：
  旧代码写死 `extractor.body(text)[:2500]`，348 页的书只喂了开头 2500 字。
  分章之后，一个章可能长达 34 页（远超 2500 字）。如果还按「截头」取样，
  第 3 章只会有开头几页的信息，中间和结尾全丢——分章就白做了。
  所以这里改成**均匀采样首/中/尾**，让一章的片段在预算内代表全章。
"""
from __future__ import annotations

import re

from .models import Chapter, OutlineDoc

# 段间省略分隔符：明确告诉 LLM「此处有跨页省略」，而不是假装是连续全文
_SEP = "\n……\n"

# 句末标点（中英文都收）。逗号/分号/冒号**不算**——它们是句内停顿，不是一句话的结束。
#
# ⚠️ 半角点号 `.` 也**刻意不收**。它在中文文本里大量充当非句末角色：小数点（3.14）、
#    编号（1.）、英文缩写（Mr.）、省略号（...）、URL。收进来会造出虚假的句边界
#    → 句数被高估 → 判据漏拦（该拦的静默放过）。
#    代价是纯英文书会被低估句数（可能误拦）——这是**刻意选的**：误拦会在 CLI 上打出
#    `⊘ 跳过 + 原因`，用户立刻看得见并反馈；漏拦是静默编造，正是本判据要消灭的那类缺陷。
#    （本脚本的测试用例「半角点号不切句」就是钉住这个决定的，别无声改掉。）
_SENT_END = re.compile(r"[。！？!?]+")

# 采样算法版本。**改动 slice_chapter 的取料逻辑时必须 +1**。
# 为什么需要一个版本号：`text.txt` 缓存按 (书字节, 章, max_chars) 键存，
# 不含算法本身——改了算法而版本不变，旧切片会被静默复用，改进等于没做
# （本项目第 4 次遇到「改了不生效」这类缺陷，故前置堵死）。
VERSION = 2


def _chapter_text(pages: list[str], ch: Chapter) -> str:
    # 把 1-based 闭区间页码转成 0-based 切片；越界裁剪到有效范围，不抛异常
    # 为什么自己夹边界而不是交给切片：Python 切片对超大 end 静默返回空，
    # 但我们要的是「尽量多取有效页」，所以显式 min/max 一次。
    start = ch.start_page - 1
    end = ch.end_page
    if start < 0:
        start = 0
    if end > len(pages):
        end = len(pages)
    if start >= end:
        return ""  # 页码完全越界 → 空章，交给上层决定跳过
    return "\n".join(str(p or "") for p in pages[start:end])


def _split_paragraphs(text: str) -> list[str]:
    # 按空行分段；空行 = 连续两个换行之间的纯空白块。
    # 为什么按空行而不是按固定字数切：章内段落是天然的语义边界，
    # 采整段比截断半句更利于 LLM 理解上下文（避免把一句话腰斩）。
    paras: list[str] = []
    buf: list[str] = []
    for line in text.split("\n"):
        if line.strip() == "":
            if buf:
                paras.append("\n".join(buf).strip())
                buf = []
        else:
            buf.append(line)
    if buf:
        paras.append("\n".join(buf).strip())
    return [p for p in paras if p]


def _fill_forward(paras: list[str], lo: int, hi: int, budget: int) -> list[str]:
    # 在 [lo, hi) 里从前往后贪心收集段落，**块拼装后总长不超过 budget**。
    # 为什么把段间 "\n\n" 计入预算：只算段落字符会让拼装结果超出预算
    # （k 段多出 2(k-1) 字符），进而在 _assemble 里被兜底截断——而那一刀是从**尾部**切的，
    # 恰好切掉尾段辛苦保留的「章尾」。预算必须把分隔符算进去，截断才不会发生。
    out: list[str] = []
    total = 0
    for i in range(lo, hi):
        p = paras[i]
        if not out and len(p) > budget:
            # 单段就超限：截断到预算内，保证这一区非空且不撑爆总预算
            out.append(p[:budget])
            break
        if total + len(p) + (2 if out else 0) > budget:
            break
        total += len(p) + (2 if out else 0)
        out.append(p)
    return out


def _fill_backward(paras: list[str], lo: int, hi: int, budget: int) -> list[str]:
    # 在 [lo, hi) 里从后往前贪心收集段落（用于尾段区，确保采到真正的章尾）。
    out: list[str] = []
    total = 0
    for i in range(hi - 1, lo - 1, -1):
        p = paras[i]
        if not out and len(p) > budget:
            out.append(p[:budget])
            break
        if total + len(p) + (2 if out else 0) > budget:
            break
        total += len(p) + (2 if out else 0)
        out.append(p)
    return out


def _assemble(blocks: list[str], max_chars: int) -> str:
    # 把若干文本块用省略分隔符拼起来；段间/段内分隔符也占字数，
    # 最后兜底裁一刀，保证返回长度严格 <= max_chars。
    text = _SEP.join(b for b in blocks if b.strip())
    if len(text) > max_chars:
        text = text[:max_chars]
    return text


def slice_chapter(pages: list[str], ch: Chapter, max_chars: int = 2500) -> str:
    """章节页码范围 → 供 LLM 的文本片段。

    超长时**均匀采样首/中/尾**，而不是 [:max_chars] 截头——
    截头会让 34 页的章只剩下开头几页的信息，分章就白做了。
    """
    raw = _chapter_text(pages, ch)
    if raw.strip() == "":
        return ""  # 空章：页码越界或范围内只有空白，不抛异常
    if len(raw) <= max_chars:
        return raw  # 短章：原样返回，不加任何省略标记

    # 长章：均匀采样首/中/尾三段，各占约 1/3 预算，避免截头丢信息
    paras = _split_paragraphs(raw)
    # 为什么区分两条路径：很多中文 PDF 的 extract_text 不带空行，整章被压成一段。
    # 若按「段落三等分」采样，n=1 时只剩一段被截断 → 实际只采到章首，
    # 章尾照样丢。段落足够多（>=3）才走段落采样；否则退回「按字符位置」采样，
    # 直接从章的开头 / 正中 / 结尾三处取料，保证三段真的覆盖全章。
    if len(paras) >= 3:
        # 三段各占 1/3，但**先扣掉 2 个省略分隔符**：否则 3*budget 会把总长顶过 max_chars，
        # _assemble 的兜底截断就会从尾部切一刀，把尾段保留的章尾切掉（实测踩到）。
        budget = max(1, (max_chars - 2 * len(_SEP)) // 3)
        # 按段落下标三等分：首段区[0,1/3)、中段区[1/3,2/3)、尾段区[2/3,末尾)
        # 为什么各段从「外缘」取料：首取开头、尾取结尾、中取中心——
        # 若都从前往后填，中段与尾段只会采到各自区间的开头，章尾信息仍会丢。
        head = _fill_forward(paras, 0, len(paras) // 3, budget)
        mid_lo, mid_hi = len(paras) // 3, (2 * len(paras)) // 3
        mid = _fill_forward(paras, mid_lo + (mid_hi - mid_lo) // 2, mid_hi, budget)
        tail = _fill_backward(paras, (2 * len(paras)) // 3, len(paras), budget)
        return _assemble(["\n\n".join(r) for r in (head, mid, tail)], max_chars)

    # 字符位置采样：首=开头，中=正中，尾=结尾，各约 1/3 预算。
    # 长章（>2500 字）下这三段必然互斥，不会重叠。（同样先扣分隔符）
    budget = max(1, (max_chars - 2 * len(_SEP)) // 3)
    head = raw[:budget]
    mid = raw[len(raw) // 2 - budget // 2: len(raw) // 2 + budget // 2]
    tail = raw[len(raw) - budget:]
    return _assemble([head, mid, tail], max_chars)


def pick(pages: list[str], doc: OutlineDoc, index: int, max_chars: int = 2500) -> str:
    """按顶层序号取一章并切片。取不到（序号越界/章不存在）返回空串。

    为什么单独封装：上层按 `--chapter N` 调用时只需一个序号，
    不用自己先 doc.by_index 再 slice_chapter，少一层出错面。
    """
    ch = doc.by_index(index)
    if ch is None:
        return ""
    return slice_chapter(pages, ch, max_chars)


# ── 料够不够：出片下限的判据 ────────────────────────────────────────────────
# 存在的理由：上游只有「空文本」的守卫（`pipeline._produce`），挡不住「只有 5 个字」。
# 而「出 N 句」是硬约束，料不够时模型只能同义反复或编造。实测（《关键对话》348 页）：
# 22 字的「附录D」被出了 12 句，内容全是「附录D讲作者团队信息 / 附录D提供作者背景」
# 这类重复，12 张卡同时退化到 2 个图标——本机永远测不出来（没人拿附录去测），
# 只在 `--all` 跑整本书时才踩到。


class InsufficientMaterial(ValueError):
    """料不足以支撑目标句数。

    **是判断，不是故障**：上层应记为「跳过」而不是「失败」——把两者混在一起，
    会让用户以为工具坏了（实际是我们主动没做）。

    为什么把 `reason` 单独留一份：异常消息要**自含章节**（裸 traceback 也能定位），
    而汇总表已经在外层打了「第 N 章「标题」」——只留消息的话汇总行会出现
    「第 22 章「X」：第 22 章「X」可用文本仅…」这种重复。两个消费者要的粒度不同，
    故同时提供（message = 完整可独立读，reason = 裸原因供列表复用）。
    """

    def __init__(self, message: str, reason: str = ""):
        super().__init__(message)
        self.reason = reason or message


def sentence_count(text: str) -> int:
    """按句末标点数「能算作一句」的片段数（纯空白片段不计）。

    刻意只滤空白、不设最小长度阈值：阈值的自然来源是「几个字算一句话」这种
    拍脑袋的魔数（错题库 L-14），而这里不需要它——`参考文献` 只有 5 个字且
    不含任何句末标点，本来就会被算作 1 句，1 < 目标句数，照样拦得住。
    """
    return sum(1 for s in _SENT_END.split(text) if s.strip())


def insufficient_reason(text: str, target: int) -> str | None:
    """这段料够不够支撑 `target` 句口播。够 → `None`；不够 → 一句人话原因。

    判据 = **一句话换一句话**：原文能切出的句子数 ≥ target。

    为什么用句数而不是字数：字数阈值是拍脑袋的数字（L-14）；
    「原句数 < 目标句数」是任何人都能听懂的解释——缺口只能靠重复或编造去填。
    实测该判据在《关键对话》上拦下 5 条（参考文献 + 4 个附录），
    11 个正文章、5 条书前材料、后记全部通过，**零误伤**。

    为什么 target 由外部传入：它就是 `limits.max_sentences`。
    本模块不读配置，依赖保持单向（配置 → 调用方 → 本函数）。
    """
    n = sentence_count(text)
    if n >= target:
        return None
    return (f"可用文本仅 {len(text)} 字 / {n} 句，不足以支撑 {target} 句口播"
            f"（判据：原句数 ≥ 目标句数）")


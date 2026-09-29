"""跨模块数据契约 —— 依赖图的塔尖：所有模块都依赖它，它不 import 任何同包模块。

为什么单独一个文件（T2V-002 决策，依据 specs/2026091518-book2vido-chapter/01_analysis.md §二）：

  ① **契约所有权**：`Scene` 原本定义在 `scriptwriter`，但它是「生成 → 画面 → 配音」三方对齐的契约。
     契约应由依赖图的塔尖持有——谁定义契约，谁就成了解耦前提。
  ② **类型化**：`compositor.compose` 原本收裸 `list[tuple]`，靠**位置约定**对齐；
     调换字段顺序不会报错，只会静默出错片（最贵的一类契约缺陷）。
  ③ **可序列化**：`script.json` / `outline.json` 是「人能微调」的口子，需要稳定 schema。

🔒 **铁律**：本文件不得 import 任何 `book2vido` 内部模块（AC-13，可用 `ast` 断言）。
   只允许标准库。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime


def now_stamp() -> str:
    """统一时间戳格式（分钟精度）。集中一处，避免各模块各写一种格式。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M")


@dataclass(frozen=True)
class Chapter:
    """一个章节的页码范围。**页码一律 1-based，两端闭区间**。

    `end_page` 的推导约定：顶层章 = 下一章 `start_page - 1`；末章 = 全书总页数。
    这样 `slice_chapter` 只需按 [start_page-1:end_page] 切片即可，不需要再算相邻关系。
    """

    index: int          # 1-based 顺序号，与 PDF outline 中出现顺序一致
    title: str
    start_page: int     # 1-based，含
    end_page: int       # 1-based，含
    depth: int = 0      # 0 = 顶层章，1 = 小节
    source: str = "outline"   # outline | regex | whole —— 标注这一章是谁发现的

    @property
    def pages(self) -> int:
        """覆盖页数（至少 0，防页码错乱时出现负数）。"""
        return max(0, self.end_page - self.start_page + 1)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Chapter":
        return cls(index=int(d["index"]), title=str(d["title"]),
                   start_page=int(d["start_page"]), end_page=int(d["end_page"]),
                   depth=int(d.get("depth", 0)), source=str(d.get("source", "outline")))


@dataclass
class OutlineDoc:
    """一本书的目录树。

    `origin` 记录这份目录是**怎么来的**，供上层决定可信度与是否提示用户：
      - `pdf-outline`：PDF 内嵌书签，零成本零幻觉（首选）
      - `regex`      ：正文里正则匹配「第X章」，次选
      - `whole-doc`  ：两者都失败，整本当一章（保底，不编造）
    """

    source_path: str
    total_pages: int
    origin: str = "whole-doc"
    chapters: list[Chapter] = field(default_factory=list)

    def top(self) -> list[Chapter]:
        """仅顶层章（`depth == 0`）。

        `--chapter N` 的 N 以**本列表**为索引基准，而不是 `chapters` 全量——
        否则用户看到 93 条会不知道 N 该填几。两级目录的二级只用于 `list` 展示。
        """
        return [c for c in self.chapters if c.depth == 0]

    def by_index(self, index: int) -> Chapter | None:
        """按顶层序号取章；不存在返回 None（由 CLI 决定如何报错）。"""
        for c in self.top():
            if c.index == index:
                return c
        return None

    def to_json(self) -> str:
        # ensure_ascii=False：中文标题要人可读（这是「人工可改」的前提）
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, text: str) -> "OutlineDoc":
        d = json.loads(text)
        return cls(source_path=str(d["source_path"]),
                   total_pages=int(d["total_pages"]),
                   origin=str(d.get("origin", "whole-doc")),
                   chapters=[Chapter.from_dict(c) for c in d.get("chapters", [])])


@dataclass
class Scene:
    """一句口播 + 它的画面标签。

    字段语义（与 `concepts.py` 的受控清单配合）：
      - `text`    ：口播正文
      - `keyword` ：画面大标题，LLM 自由发挥，有信息量
      - `concept` ：图标语义标签，**须落在 `concepts.CONCEPTS` 受控清单内**；
                    为空时 `visualizer` 自动退回按 `keyword` 解析。
    自由词命中率太低（12 张卡会散列撞车），故把来源分成两个字段——详见 `concepts.py`。
    """

    text: str
    keyword: str = ""
    concept: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Scene":
        return cls(text=str(d.get("text", "")), keyword=str(d.get("keyword", "")),
                   concept=str(d.get("concept", "")))


@dataclass
class ScriptDoc:
    """一章的分镜产物 —— **最贵的东西**（要跑 LLM），必须能落盘、能人工改、能回读。

    人工微调闭环：改 `script.json` → 哈希变化 → 缓存只重跑下游（画面/配音/合成），
    **不重跑 LLM**，省 ~36s。见 specs/.../03_design.md §3.3。

    `prompt_version` / `prompt_hash`（T2V-007）回答一个此前无处可查的问题：
    **这版分镜是哪版提示词产出的？**
    换模型、调提示词之后要对比产出时，没有这两个字段就只能靠记忆和文件时间戳。
    两者都是"记录用"的：**缓存失效不靠它们**（靠缓存键里的提示词指纹），
    所以人可以自由地改提示词而不必记得升版本号。
    """

    chapter_index: int
    title: str = ""
    scenes: list[Scene] = field(default_factory=list)
    model: str = ""
    think: bool = False
    created: str = ""
    prompt_version: str = ""   # 提示词资产的 version 字段（人读，如 "1"）
    prompt_hash: str = ""      # 提示词模板正文的指纹（稳定；用于跨产物对比）

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, text: str) -> "ScriptDoc":
        d = json.loads(text)
        return cls(chapter_index=int(d.get("chapter_index", 0)),
                   title=str(d.get("title", "")),
                   scenes=[Scene.from_dict(s) for s in d.get("scenes", [])],
                   model=str(d.get("model", "")),
                   think=bool(d.get("think", False)),
                   created=str(d.get("created", "")),
                   # 缺字段的老 script.json 照样能读（都给了默认值）——「只增不删」
                   prompt_version=str(d.get("prompt_version", "")),
                   prompt_hash=str(d.get("prompt_hash", "")))


@dataclass(frozen=True)
class MediaClip:
    """一张卡 + 一条配音 + 时长 = 一个视频片段（compositor 的最小输入单元）。

    取代原来的 `(png, audio, duration)` 三元组：字段有名字，调换顺序会报错而不是出错片。
    """

    index: int
    image: str        # PNG 路径（建议绝对路径，见 compositor 的 concat 坑）
    audio: str        # 音频路径（mp3/aiff 皆可）
    duration: float

    @classmethod
    def from_any(cls, item) -> "MediaClip":
        """向后兼容：接受 MediaClip / dict / (image, audio, duration) 三元组。

        保留这条通道是为了不破坏外部脚本与旧调用点——
        「只增不删」是本 spec 的回滚条件（02_requirements §五）。
        """
        if isinstance(item, cls):
            return item
        if isinstance(item, dict):
            return cls(index=int(item.get("index", 0)), image=str(item["image"]),
                       audio=str(item["audio"]), duration=float(item["duration"]))
        image, audio, duration = item[0], item[1], item[2]
        return cls(index=int(item[3]) if len(item) > 3 else 0,
                   image=str(image), audio=str(audio), duration=float(duration))

"""提示词资产加载器：外部 `.md` 文件 → 可送模型的 prompt 文本。

为什么单独成模块（T2V-007）：

  ① **提示词是资产，不是代码。** 本链路只有一个环节用模型（`CONSTITUTION.md` 铁律六），
     而它的行为 100% 由这段文本决定。内联在 `scriptwriter` 的字符串拼接里意味着：
     想改提示词就得改 Python，而且**没有地方写「这条约束为什么这么写」**。
  ② **改提示词必须让缓存失效。** `script_key` 原本只含 model/think/句数/章节文本，
     漏了提示词 —— 于是改提示词会静默命中旧分镜，表现为"改了像没改"（错题库 L-13 家族）。
     本模块提供**指纹**，由调用方拼进缓存键：改一个字就自动失效，不依赖谁记得升 version。
  ③ **注释与模板同文件。** 约束的解释就写在约束旁边（`<!-- -->`），加载时整块剥掉，
     不占 token。文件头/文末的人读区在标记之外，根本不参与渲染。

依赖：标准库 + `paths`（后者同样只依赖标准库）。
  包内依赖只有这一条，且指向一个 stdlib-only 的叶子模块 —— 不构成环，也不破分层。
  （收敛项目根定位后不再自己写 `parents[2]`，见 `paths.py` docstring 与 doc/17 §S-1。）

文件格式（唯一实例见 `prompts/scriptwriter.md`）：

    ---                      ← frontmatter（人读元数据，不进 prompt）
    id / version / applies_to / updated / placeholders
    ---
    <!-- 文件头说明：怎么用 / 怎么改 / 现在什么模型 -->
    <!-- @prompt:begin -->
    提示词正文，可夹 <!-- 就近注释 -->
    <!-- @prompt:end -->
    ## 文末人读区（模型适配记录 / 影响面 / 验证 SOP）

剥注释规则（**两条都要**，否则注释会被当提示词送进模型、白烧 token 并污染行为）：
  · 注块**独占一行**（该行去掉注块后只剩空白）→ 整行连同换行一起删；
  · 注块在**行内** → 只删注块本身，保留该行其余内容。
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from .paths import project_root

BEGIN = "<!-- @prompt:begin -->"
END = "<!-- @prompt:end -->"

# 标记一律按**整行精确匹配**，不用子串匹配。
# 实测教训（T2V-007 第一跑就踩）：文件头说明里写了「`<!-- @prompt:begin -->` 与 …」，
# 子串匹配把**注释里提到的那一处**当成了真标记，于是正文只取到两个反引号之间的 5 个字符。
# 这类"匹配到不该匹配的东西"不报错、只静默取错内容 —— 与错题库里那条同源。
# 整行匹配后，正文随便提到标记都不会歧义。
_BEGIN_LINE = re.compile(r"(?m)^[ \t]*<!--[ \t]*@prompt:begin[ \t]*-->[ \t]*$")
_END_LINE = re.compile(r"(?m)^[ \t]*<!--[ \t]*@prompt:end[ \t]*-->[ \t]*$")

_SENTINEL = "\x00"                                  # 注释占位（正文里不会出现 \x00）
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_WHOLE_LINE = re.compile(r"(?m)^[ \t]*\x00[ \t]*\n")
_TAIL_LINE = re.compile(r"(?m)^[ \t]*\x00[ \t]*$")
_LEFT_OVER = re.compile(r"\{\{(\w+)\}\}")

# 资产默认目录：<项目根>/prompts。项目根来自 paths（唯一来源）；
# 在 .app 里即 Contents/Resources，故 config.yaml 与 prompts/ 必须同级
# —— 见 packaging/build_app.sh 的布局注释。
DEFAULT_DIR = project_root() / "prompts"


class PromptError(ValueError):
    """提示词资产有问题。

    **显式失败优于静默降级**：若悄悄退回一份内置文本，用户会以为"我改的生效了"，
    而真相是他改的那份根本没被读到 —— 这类"静默走错分支"是本项目最忌讳的缺陷。
    """


@dataclass(frozen=True)
class Prompt:
    """一份提示词资产（已剥注释、未渲染）。"""

    id: str
    version: str
    applies_to: str
    updated: str
    body: str          # 模板正文，含 {{占位符}}；不含任何注释
    source: str = ""   # 实际读到的路径（报错与追溯用）

    @property
    def body_hash(self) -> str:
        """模板本身的指纹 —— **稳定，不随章节变**，供 `script.json` 做人工追溯。

        与 `fingerprint()` 的分工：这个是"这版分镜是哪版提示词出的"，
        那个是"这次输入该不该复用缓存"。
        """
        return hashlib.sha256(self.body.encode()).hexdigest()[:12]

    def render(self, **kw) -> str:
        """替换 `{{占位符}}`。**残留未替换的占位符直接报错**，不静默送脏文本给模型。"""
        s = self.body
        for k, v in kw.items():
            s = s.replace("{{" + k + "}}", str(v))
        left = sorted(set(_LEFT_OVER.findall(s)))
        if left:
            raise PromptError(
                f"提示词「{self.id}」有未替换的占位符：{left}；"
                f"实际传入：{sorted(kw)}（定义见 {self.source}）")
        return s

    def fingerprint(self, **kw) -> str:
        """缓存键用的指纹：**模板 + 注入项，但不含 chunk**。

        为什么必须不含 chunk：`pipeline` 要**先算键、再决定是否调模型**，
        而 chunk 是那一步才有的；章文本本身已在 `script_key` 里，再算一次是冗余。

        为什么用指纹而不是 version 号：版本号靠人记得升，**迟早会忘**。
        内容哈希是自动的 —— 改注释不影响（注释已被剥掉），改正文一个字就变。
        """
        parts = [self.body] + [f"{k}={v}" for k, v in sorted(kw.items())]
        return hashlib.sha256("\x00".join(parts).encode()).hexdigest()[:12]


def hash_text(text: str) -> str:
    """任意文本的短指纹（12 位十六进制，够用且好读）。"""
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def strip_comments(text: str) -> str:
    """剥掉所有 `<!-- -->` 注块。规则见模块 docstring（独占行 / 行内两种）。"""
    s = _COMMENT.sub(_SENTINEL, text)
    s = _WHOLE_LINE.sub("", s)      # 独占一行的注块：连换行一起删
    s = _TAIL_LINE.sub("", s)       # 文件末尾无尾换行的那行
    return s.replace(_SENTINEL, "")  # 行内注块：只删块本身


def _parse_front(text: str, source: str) -> tuple[dict, str]:
    if not text.lstrip().startswith("---"):
        raise PromptError(f"{source} 缺少 frontmatter（应以 `---` 开头）")
    _, fm, rest = text.split("---", 2)
    meta: dict[str, str] = {}
    for line in fm.strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    for need in ("id", "version"):
        if not meta.get(need):
            raise PromptError(f"{source} 的 frontmatter 缺字段 `{need}`")
    return meta, rest


def parse(text: str, source: str = "(内存)") -> Prompt:
    """把一份提示词文件解析成 `Prompt`。标记缺失即报错，不猜。"""
    meta, rest = _parse_front(text, source)
    mb, me = _BEGIN_LINE.search(rest), _END_LINE.search(rest)
    if not mb or not me:
        raise PromptError(
            f"{source} 缺少正文标记：需要**独占一行**的 `{BEGIN}` 与 `{END}` 各一处"
            f"（只找到 begin={bool(mb)} / end={bool(me)}）")
    if me.start() < mb.end():
        raise PromptError(f"{source} 的 end 标记出现在 begin 之前")
    body = strip_comments(rest[mb.end():me.start()]).strip("\n")
    if "<!--" in body:
        # 说明剥注释有遗漏 —— 与其把注释送进模型烧 token，不如当场炸
        raise PromptError(f"{source} 剥离注释后仍残留 `<!--`，请检查注释是否成块闭合")
    if not body.strip():
        raise PromptError(f"{source} 的正文为空")
    return Prompt(id=meta["id"], version=meta["version"],
                  applies_to=meta.get("applies_to", ""), updated=meta.get("updated", ""),
                  body=body, source=source)


def load(name: str = "scriptwriter", path: str | None = None) -> Prompt:
    """读一份提示词。`path` 给了就用它（用户在 config 里指到别处），否则用默认目录。"""
    p = Path(path) if path else DEFAULT_DIR / f"{name}.md"
    if not p.is_file():
        raise PromptError(
            f"找不到提示词文件：{p}\n"
            f"  · 默认位置 {DEFAULT_DIR}/<name>.md（与 config.yaml 同级）\n"
            f"  · 或在 config.yaml 的 `llm.prompt_file` 里指定绝对路径\n"
            f"  · 从 git 恢复：git checkout -- prompts/")
    return parse(p.read_text(encoding="utf-8"), source=str(p))

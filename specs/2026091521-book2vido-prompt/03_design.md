# 03 · 设计（接口与契约冻结）

## 一、目录与文件布局

```
<项目根>/                          ← 也是 .app 的 Contents/Resources/
├── config.yaml                    ┐ 两个"人可改的资产"，同级、
├── prompts/                       ┘ 同一套定位法（parents[2] 回溯）
│   └── scriptwriter.md            ← ★ 提示词资产（正文 + 就近注释 + 人读区）
└── src/book2vido/
    ├── promptlib.py               ← 加载器（本 spec 新增，172 行）
    └── scriptwriter.py            ← 只管「加载 → 渲染 → 调用 → 解析」
```

**为什么 `prompts/` 与 `config.yaml` 同级**：两者都是"人能改的东西"，且都被同一行
`Path(__file__).resolve().parents[2]` 定位（项目根 = `.app` 里的 `Contents/Resources/`）。
**已实测**：模拟 `.app` 布局后加载成功，缺文件时报错含修复指引。

## 二、契约冻结（本 spec 唯一冻结点）

### 2.1 `promptlib` 模块接口

```python
BEGIN = "<!-- @prompt:begin -->"
END   = "<!-- @prompt:end -->"
DEFAULT_DIR = <项目根>/prompts

class PromptError(ValueError): ...
    # 一切"资产有问题"的统一异常。**显式失败优于静默降级**

@dataclass(frozen=True)
class Prompt:
    id: str; version: str; applies_to: str; updated: str
    body: str            # 已剥注释的模板（含 {{占位符}}）
    source: str = ""     # 实际读到的路径（报错/追溯用）

    @property
    def body_hash(self) -> str: ...          # 模板指纹（稳定，写进 script.json）
    def render(self, **kw) -> str: ...       # 替换占位符；有残留 → PromptError
    def fingerprint(self, **kw) -> str: ...  # 模板+注入项（**不含 chunk**），进缓存键

def hash_text(text: str) -> str: ...         # 通用短指纹（12 位）
def strip_comments(text: str) -> str: ...    # 两条规则：独占行整行删 / 行内只删块
def parse(text: str, source: str = "(内存)") -> Prompt: ...
def load(name: str = "scriptwriter", path: str | None = None) -> Prompt: ...
```

### 2.2 模块间契约变更

```python
# scriptwriter.LLMProvider（基类新增两个属性，子类按需覆盖）
prompt: Prompt | None = None        # rule 降级为 None
prompt_fingerprint: str = ""        # rule 降级为 ""

# OllamaProvider.__init__ 新增（都是可选，向后兼容）
prompt_file: str | None = None, prompt_name: str = "scriptwriter"

# cache.Cache.script_key 新增可选参数
script_key(self, i, chapter_text, cfg, prompt_fp: str = "") -> str

# models.ScriptDoc 新增两个字段（带默认值 → 老 JSON 可读）
prompt_version: str = ""   # 人读：提示词资产的 version
prompt_hash: str = ""      # 人读：模板 body_hash
```

> **兼容性承诺（"只增不删"）**：所有新参数都有默认值；不传即与升级前行为一致。
> 唯一的行为变化是 **`prompt_fp` 非空时键值不同**，见 §四。

## 三、提示词文件格式（唯一实例：`prompts/scriptwriter.md`）

```markdown
---
id: scriptwriter          ← 必填（缺 → PromptError）
version: 1                ← 必填（人读的追溯标签，**不是**失效开关）
applies_to: qwen3:8b      ← 可选：实测过的模型
updated: 2026-09-15       ← 可选
placeholders: max_n, concept_list, chunk   ← 人读清单（代码靠正则检测残留，不依赖它）
---

<!-- 文件头说明区（不进 prompt）：怎么读 / 怎么改 / 现在什么模型 -->

<!-- @prompt:begin -->        ← 整行精确匹配
提示词正文
<!-- 就近注释（剥掉后整行消失，不改变正文换行结构） -->
{{chunk}}
<!-- @prompt:end -->

## 模型适配记录（人读区，不进 prompt）
## 改动影响面
## 验证
```

### 剥注释算法（两条规则，缺一不可）

| 情形 | 处理 | 为什么 |
|---|---|---|
| 注块**独占一行**（去掉后该行只剩空白） | **整行连同换行一起删** | 保证正文换行结构与搬出前**逐字节一致**；否则 golden 比对必然失败 |
| 注块**在行内** | 只删块本身，保留该行其余 | 允许 `  keyword：xxx <!-- 说明 -->` 这种贴行注释 |

实现（`strip_comments`）：注块 → 哨兵 `\x00` → `(?m)^[ \t]*\x00[ \t]*\n` 删整行
（末尾无换行的那行用 `$` 版本兜一次）→ 剩余哨兵直接删（行内情形）。

### 标记匹配必须**整行**

`^[ \t]*<!--[ \t]*@prompt:begin[ \t]*-->[ \t]*$`（`re.M`）。

**不用子串匹配**：实测踩过——文件头说明里写了标记字面量，子串匹配把它当成真标记，
正文只取到 5 个字符（`01_analysis` §七 F-A）。整行匹配后，正文里随便提到标记都不歧义。

## 四、缓存键（行为变更点）

```python
# 改前
raw = f"{book_hash}|{model}|{think}|{max_sentences}|{sha256(chapter_text)}"
# 改后（末段为新增）
raw = f"{book_hash}|{model}|{think}|{max_sentences}|{sha256(chapter_text)}|{prompt_fp}"
```

**后果：既有缓存全部失效一次**（旧键与新键任何情况都不相等）。这是**有意**的：
历史分镜产自"说不清是哪版提示词"的状态，其来源不可信；重跑一次是正确而非浪费。

**为什么指纹不含 `chunk`**：`pipeline` 必须**先算键、再决定是否调模型**，那时章节文本还没有。
章节文本本身已在键里，重复无益。

## 五、数据流

```
config.yaml(llm.prompt_file) ─┐
prompts/scriptwriter.md ──────┴→ promptlib.load() ──→ Prompt
                                    │
                                    ├─ fingerprint(concept_list) ──→ OllamaProvider.prompt_fingerprint
                                    │                                      │
                                    │                                      ▼
                                    │             pipeline: skey = cache.script_key(..., prompt_fp)
                                    │                                      │
                                    │                            ┌─────────┴─────────┐
                                    │                         命中│                   │未命中
                                    │                            ▼                   ▼
                                    │                    读 script.json      render(chunk=章文本)
                                    │                                            │
                                    │                                            ▼
                                    │                                     POST /api/generate
                                    │                                            │
                                    └─ body_hash ──→ ScriptDoc.prompt_version / prompt_hash ←─┘
                                                          │
                                                          ▼
                                                    cache/.../script.json（可追溯 + 人工可改）
```

## 六、关键设计决策（含被否决项）

| 决策 | 选它 | 否决的替代 | 理由 |
|---|---|---|---|
| 资产位置 | 项目根 `prompts/` | 包内 / config 内联 | 与 config.yaml 同定位法；`.app` 可回溯（已实测）；用户可见可改 |
| 失效开关 | **内容哈希** | `version` 号 | 版本号靠人记得升，**迟早会忘** → 回到"改了像没改" |
| 版本号 | 保留（人读） | 删掉 | `script.json` 要能人读回答"哪版提示词" |
| 指纹分层 | `fingerprint`（进键）/ `body_hash`（进产物） | 一个哈希通吃 | 进键的必须能**先于 chunk** 算出；进产物的必须**稳定可比** |
| 加载失败 | `PromptError` | 退回内置文本 | 静默降级 = 让人以为"我改的生效了"，本项目头号缺陷类型 |
| 清单归属 | 留在 `icons.py`（prompt 只放 `{{concept_list}}` 占位） | 搬进 `prompts/` | 清单是"词→图标名"映射；搬走会让 icons 反向依赖 prompts |
| 模板引擎 | 无（自带 `str.replace` + 残留检测） | Jinja2 | 3 个占位符不值得引依赖；且模板引擎会诱惑人把逻辑塞进提示词 |
| 打包缺失 | 构建 `die` | 只 warn | 与 ffmpeg 同理：静默降级 = 把失败从构建期推迟到用户期 |

## 七、级联影响（调用链 3 跳）

| 跳 | 路径 | 影响 | 已验 |
|---|---|---|---|
| 1 | `providers.build` → `OllamaProvider.__init__` | 多传 `prompt_file`（默认 None） | ✅ `.app` 布局模拟 |
| 2 | `pipeline._produce` → `cache.script_key` / `ScriptDoc` | 键多一段；产物多两字段 | ✅ 四跑对照 + 老 JSON 兼容 |
| 3 | `__main__._run_cmd` → `pipeline.run_book` → `_produce` | CLI 侧**零改动**（配置经 `config.load` 已带 `prompt_file`） | ✅ 端到端跑通 |

**不受影响**：`RuleFallbackProvider`（不读提示词）、`pipeline.run()`（`enabled=False` 不参与键）、
`icons.resolve()`（清单未动）、`visualizer` / `narrator` / `compositor`（与提示词无关）。

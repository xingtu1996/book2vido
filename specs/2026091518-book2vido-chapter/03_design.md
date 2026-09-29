# 03 · 详细设计：目录索引与按需生成

> Ticket: T2V-002 | 日期: 2026-09-15 18:51 | 状态: ✅
> **本文件的 §三 契约已冻结** —— Phase 1/2/2b/3 四个并行单元据此编码，任何改动须先回改本文件（铁律 3）。

> 📜 **Check**：设计遵守 [laws.md](./laws.md) 的架构/分层约束——依赖单向无环、每模块 <200 行、契约集中一处。
> 并行门禁（laws §三）：契约先冻结 → 文件冲突交集 = ∅ → 共享文件串行。

## 一、架构决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 同步/异步 | **同步 CLI**，只在 TTS 环节用线程池 | 实测 Ollama 服务端串行（探针 2），异步化无收益；TTS 是纯网络 IO 等待（探针 4，13.1x） |
| 并发模型 | `concurrent.futures.ThreadPoolExecutor`（**标准库**） | 引 Celery/Prefect/Ray 是负收益（宪法铁律三：集百家之长 ≠ 引重栈） |
| 缓存策略 | **文件系统**（内容哈希分目录 + JSON） | 无 DB；文件系统即可满足三层命中语义，且中间产物天然可读可改 |
| 降级/兜底 | 三级降级链，**每级都有明确 origin 标注** | ①目录：outline → 正则 → 整本 ②TTS：edge 并发 → 降并发 → say ③图标：缓存 → 网络 → 无图标版式 |
| 契约归属 | 新建 `models.py` 作为**依赖图塔尖** | 见 `01_analysis` §二更正：病根是契约所有权错位 + 裸 tuple 契约 |
| 热加载 | **不做** | 批处理 CLI 无常驻进程，无可热替换对象；「边点播边生成」由 `--chapter` + 缓存命中承接 |
| 关注点分离 | 新建 `providers.py`（造 provider） | AC-16 暴露的结构问题：pipeline 同时干"造对象"和"编排流程"，文件必然超行数 |
| 命中路径零冗余 | 大纲读缓存 + 章文本落 `text.txt` + 抽页**延迟执行** | 「全命中」不能还去解析 348 页：实测冗余 11.9s（`extract_pages` 5.9s + `outline.build` 6.0s），AC-10①/AC-11 就是被它拖垮的 |

## 二、影响面确认

```
改动入口: pipeline.run()  （签名保持不变）
  ├── 直接调用者:  __main__._run() L15   ·   __main__._batch() L30
  ├── 级联影响 3 跳: CLI run/batch → pipeline → {extractor, scriptwriter, visualizer, narrator, compositor}
  └── 跨模块消费者:  packaging/launcher.sh（拖 PDF = run 整本，默认行为不得变）
                    tools/probe_perf.py:37（import Scene → 须保持可导入）
```

| 波及点 | 类型 | 处置 |
|-------|------|------|
| `pipeline.run()` | 入口函数 | **保留原签名与语义**，内部改为 `run_chapter`/`run_book` 的封装 |
| `compositor.compose()` | 接口 | 改收 `list[MediaClip]`，`MediaClip.from_any` 兼容旧三元组 |
| `extractor.body()` | 被调函数 | **不删**，加 deprecated 注释；删除 `scriptwriter` 内调用点 |
| `extractor.chapters()` | 被调函数 | **不删**（`RuleFallbackProvider` 用于降级取料，语义与 PDF 章节无关） |
| `scriptwriter.Scene` | 导入路径 | 改为 `from .models import Scene` 并 **re-export**，`tools/probe_perf.py` 不破 |
| `providers.py` | 新模块 | 承载 `Stage` + `build(cfg, think)`；pipeline 只 `providers.build(...)`，不再自己 new provider |
| `extractor.lazy_pages/resolve_pages` | 新增函数 | 抽页的懒版本 + 传参兼容（list 或零参可调用）——属 extractor 职责，不塞进 pipeline |
| `outline.build()` | 语义收紧 | 非 PDF **一律落 `whole-doc`**：无页边界 → 无「章→页」映射，硬分章会让每章切片到整篇 |
| `pipeline.run_chapter()` | 签名 | `pages` 参数放宽为「list 或 `extractor.lazy_pages()`」；新增 `text.txt` 读写 |
| `config.yaml` | 配置 | 新增 `cache` / `concurrency` 段，`config.py` 给默认值 |
| `packaging/launcher.sh` | 分发 | 不改；`.app` 需重建以带上 5 个新模块 |

## 三、接口设计（契约冻结）

### 3.0 `models.py` — 数据契约（**塔尖：不 import 任何同包模块**）

```python
@dataclass(frozen=True)
class Chapter:
    index: int            # 1-based 顺序号（与 PDF outline 出现顺序一致）
    title: str
    start_page: int       # 1-based，含
    end_page: int         # 1-based，含（= 下一章 start_page - 1；末章 = 总页数）
    depth: int = 0        # 0 = 顶层章，1 = 小节
    source: str = "outline"   # outline | regex | whole
    @property
    def pages(self) -> int

@dataclass
class OutlineDoc:
    source_path: str
    total_pages: int
    origin: str                          # pdf-outline | regex | whole-doc
    chapters: list[Chapter] = field(default_factory=list)
    def top(self) -> list[Chapter]       # 仅 depth==0，供 list 打印与 --chapter 索引
    def by_index(self, i: int) -> Chapter | None
    def to_json(self) -> str
    @classmethod
    def from_json(cls, text: str) -> "OutlineDoc"

@dataclass
class Scene:
    text: str
    keyword: str = ""     # 画面大标题，LLM 自由发挥
    concept: str = ""     # 图标语义标签，须落在 icons.CONCEPTS 内

@dataclass
class ScriptDoc:
    chapter_index: int
    title: str
    scenes: list[Scene] = field(default_factory=list)
    model: str = ""
    think: bool = False
    created: str = ""     # ISO 分钟精度
    def to_json(self) -> str
    @classmethod
    def from_json(cls, text: str) -> "ScriptDoc"

@dataclass(frozen=True)
class MediaClip:
    index: int
    image: str            # PNG 绝对路径
    audio: str            # MP3 绝对路径
    duration: float
    @classmethod
    def from_any(cls, item) -> "MediaClip"   # 兼容 (image, audio, duration) 三元组
```

> `Scene` 字段顺序与现值一致（`text, keyword, concept`），`keyword` 由必填改带默认值 → 旧调用 `Scene(s, kw)` 不受影响。
> JSON 字段名 = dataclass 字段名，**不做缩写**（AI 与人共读，显式优于紧凑）。

### 3.1 `outline.py`（Unit A）

```python
def build(path: str) -> OutlineDoc
    """文件 → 章节树。三层兜底：PDF 内嵌 outline → 页首正则 → 整本当一章。"""
def load(path: str) -> OutlineDoc          # 读 <cache>/outline.json，缺失时抛 FileNotFoundError
def save(doc: OutlineDoc, path: str) -> str
def render_tree(doc: OutlineDoc) -> str    # 供 CLI list 打印的纯文本树
```

> **兜底链只对 PDF 完整成立**：分章需要「页边界 + 页级标记」两个要素，只有 PDF 具备。
> 非 PDF（MD/长文）被 `extract_pages` 整篇当一页 → 正则最多给出"所有章都在第 1 页"
> → `_to_chapters` 推出的范围全是 `p1-p1` → **切片会把整篇重复给每一章，比粒度粗更糟**。
> 故非 PDF 一律落 `whole-doc`：没有页结构就如实不假装有。
> （曾出现两种偏差：①正则段被误关进 `if .pdf` 之外、注释却称"对所有格式生效"；
>   ②`extractor.extract_pages` 文档称"MD 分章走正则/整本分支"——两者都已在实现中改正。）

测试场景：
- 348 页《关键对话》（有内嵌 outline） → `origin="pdf-outline"`，`len(chapters)==93`，
  **`top()==22`**（小节 71）[端到端]
  > 注意：pypdf 原始 outline 有 **35 个元素**（22 Destination + 13 嵌套 list），
  > 这是**未解析**的计数，不等于顶层章数。曾把 35 误当章数写进 AC，已更正。
- 无 outline 的 PDF → `origin="regex"`，章节页码单调不减 [TDD]
- 纯文本 MD/TXT → `origin="whole-doc"`，`len(chapters)==1`，`end_page` 收敛不越界 [TDD]
- outline 含嵌套 list（二级小节） → `depth` 正确为 1，且不污染顶层索引 [TDD]
- 目录页混在正文里（页码在页首行尾，形如「第 10 章 …143」）→ **必须跳过该页**，
  否则「第 10 章」的起始页会被取成目录页页码 [TDD]

### 3.2 `segmenter.py`（Unit B）

```python
VERSION = 2                                # 改 slice_chapter 取料逻辑必须 +1
def slice_chapter(pages: list[str], ch: Chapter, max_chars: int = 2500) -> str
    """章节页码范围 → 供 LLM 的文本片段。

    超长时**均匀采样首/中/尾**，而不是 [:max_chars] 截头——
    截头会让 34 页的章只剩下开头几页的信息，分章就白做了。
    """
def pick(pages: list[str], doc: OutlineDoc, index: int, max_chars: int = 2500) -> str
```

> **预算必须预留分隔符**（实施期修，见 `verification-report.md` §四-2）：
> 三段各 `max_chars//3` = 833，共 2499 字，加 2 个省略分隔符（`"\n……\n"`，各 4 字）= 2507 > 2500
> → `_assemble` 的兜底 `text[:max_chars]` **从尾部切**，恰好切掉尾段辛苦保留的「章尾」。
> 修法：`budget = max(1, (max_chars - 2 * len(_SEP)) // 3)`，且
> `_fill_forward/_fill_backward` 把段间 `"\n\n"` 一并计入预算 → 块拼装后**严格不超预算**，
> 兜底截断永不触发。**实测：修前尾段末 12 字命中 = False；修后全 22 章通过。**
>
> **`VERSION` 存在的唯一理由**（实施期加）：`text.txt` 按 `(书字节, 章, max_chars)` 键存，
> 不含算法本身 → 改了算法而版本不变，旧切片被静默复用，改进等于没做。它进 `text_key`。

测试场景：
- 短章（总量 ≤ max_chars） → 原样返回，无省略标记 [TDD]
- 长章（34 页，远超 max_chars） → 长度 ≤ max_chars，且**首 / 正中 / 末 12 字**三段均被代表 [TDD]
- 页码越界（章超出 pages 长度） → 裁剪到有效范围，不抛异常 [TDD]
- 空章（页码范围无文本） → 返回空串，由上层决定跳过 [TDD]
- `VERSION` 变化 → `text.txt` 判定过期并重算（不静默复用旧切片）[TDD]

### 3.3 `cache.py`（Unit C）

```python
class Cache:
    def __init__(self, input_path: str, cfg: dict, root: str | None = None, enabled: bool = True)
    @property
    def dir(self) -> Path                      # <root>/<book_hash>
    def chapter_dir(self, i: int) -> Path      # <dir>/ch<NN>（NN 两位左补零）
    def script_key(self, i: int, chapter_text: str, cfg: dict) -> str
    def video_key(self, i: int, script_fp: str, cfg: dict) -> str   # script_fp = sha256(ScriptDoc.to_json())
    def hit_video(self, i: int, video_key: str) -> Path | None
    def hit_script(self, i: int, script_key: str) -> ScriptDoc | None
    def put_script(self, i: int, doc: ScriptDoc, script_key: str) -> Path
    def put_video(self, i: int, src: Path, video_key: str) -> Path
```

**键分层（三层命中语义的实现基础）**

| 键 | 输入 | 失效场景 |
|---|---|---|
| `book_hash` | 文件字节 sha256[:16] | 换书 |
| `script_key` | book_hash + model + think + max_sentences + **章节输入文本** | 换模型/改思考/换素材 |
| `video_key` | **sha256(分镜规范化 JSON)** + voice + accent + w + h + icon_size | 换配色/音色/**手改分镜**（均不动 LLM） |

> ⚠️ **`video_key` 挂「分镜内容指纹」而非 `script_key`**（实现期追调用流发现的规格缺陷，已 Reverse Sync）：
> `script_key` 由**输入文本**推导，手改 `script.json` 不改它 → 若 `video_key` 也挂 `script_key`，
> `hit_script` 会正确返回改后的分镜，但 `hit_video` 会命中**旧分镜渲染出的成片** → 改动被静默丢弃。
> 挂分镜指纹后：改一句 → 指纹变 → 只重渲染下游，LLM 仍不跑。

> 元数据落 `<chapter_dir>/.keys.json`（存当前 script_key / video_key）。
> 命中判定 = 产物文件存在 **且** `.keys.json` 中的键一致。
> 手工改 `script.json` → **`script_key` 不变**（它只由输入文本推导）→ `hit_script` 仍命中、
> 改动被保留 → 但 `video_key` 变 → **只重跑下游**（画面/配音/合成），LLM 不跑。
> 这个"命中"是刻意的：否则手工润色过的分镜会被重跑 LLM 覆盖掉。

**除键之外的两个缓存面（AC-10①/AC-11 的性能前提）**

| 缓存文件 | 位置 | 作用 | 为什么安全 |
|---|---|---|---|
| `outline.json` | `<dir>/outline.json` | `run_book` 优先 `load()`，省 ~6s 全书解析 | 它是**人工可改口子**：读缓存才让手改真正生效（此前每次重建 → 落盘文件白存） |
| `text.txt` | `<chapter_dir>/text.txt` | 章切片结果落盘，命中时跳过 348 页抽取（~6s） | 内容只由 (书字节, 章, max_chars, **`segmenter.VERSION`**) 决定；缓存目录已按书字节分键 → 永不与当前 PDF 漂移 |

> `text_key` = `f"seg{segmenter.VERSION}|chars{max_chars}"`，由 **pipeline 拼好传给 cache**
> （`Cache.text_ok/put_text`），cache 不 import segmenter → 依赖保持单向。
> 带算法版本的理由见 §3.2 的 `VERSION` 说明。
>
> 加上 `extractor.lazy_pages()`（抽页延迟到真正需要时），命中路径的冗余从 11.9s 降到 ~0。
> 实测：全命中 **0.502s**（旧实现 19.9s）；手改分镜后只重渲染 **13.0s**。

测试场景：
- 全新输入 → 三层全未命中，`hit_*` 返回 None [TDD]
- 同输入跑两次 → 第二次 `hit_video` 命中，返回既有 mp4，墙钟 ≤2s [端到端]
- `script.json` 手工改一句 → `hit_script` **仍命中**（键未变），改动被保留 [TDD]
- 只改配色 config → `video_key` 变、`script_key` 不变 → **script 仍命中** [TDD]
- 手工改 `outline.json` 的章标题 → 重跑后 `list` 显示改后的标题（证明读缓存生效）[TDD]
- 手工改 `text.txt` → `script_key` 变 → 重跑模型（语义正确：换了素材）[TDD]
- `enabled=False` → 所有 `hit_*` 返回 None 且不写盘、不读 `outline.json`/`text.txt` [TDD]

### 3.4 `narrator.py` 增 `speak_many`（Unit D）

```python
class TTSProvider:
    def speak(self, text: str, out_path: str) -> float: ...
    def speak_many(self, items: list[tuple[int, str, str]], max_workers: int = 12,
                   on_progress: Callable[[int, int], None] | None = None) -> dict[int, float]
        """items = [(index, text, out_path)] → {index: duration}。

        并发是 TTS 自己的事（不该由 pipeline 拼线程池）。
        带重试与自适应降并发：失败率 > 50% → 减半重跑失败项；仍失败 → 串行；仍失败 → 抛错。
        绝不静默产出 0 字节音频（HANDOFF §5.7 的教训）。
        """
```

测试场景：
- 12 句正常 → 全成功，耗时 ≤5s（基线 28.9s） [端到端]
- 注入 1 个必失败文本 → 重试后成功，结果集完整 [TDD]
- 注入 >50% 必失败 → 自动降并发，日志可见；最终抛错而非静默 [TDD]
- `on_progress` 回调按**完成数**递增调用（不是尝试数——曾写成尝试数导致 15/12 越界）[TDD]

### 3.5 `providers.py`（新模块）+ `pipeline.py`

```python
# providers.py —— 只负责"造对象"，不负责"排顺序"
@dataclass
class Stage:
    cfg: dict
    llm: object
    tts: object
    viz: object

def build(cfg: dict, think: bool | None = None) -> Stage
    """think=None 取配置值，传 bool 则覆盖。provider 无状态 → 构造一次跨章复用。"""

# pipeline.py —— 只负责"先谁后谁" + 缓存判断 + 进度打印
def run(input_path, out_path, config_path=None, think=None) -> dict      # T2V-001 兼容入口（签名不变）
def run_book(input_path, out_root, cfg, indices=None, single_file=False,
             no_cache=False, think=None) -> dict
def run_chapter(pages, doc, ch, cfg, out_path, c, stage, no_cache=False) -> dict
```

> **为什么拆出 `providers.py`**：AC-16（每模块 ≤200 行）是症状，病根是 pipeline 同时承担
> 「造 provider」和「编排流程」两件事。拆开后 pipeline 192 行、providers 35 行，各司其职。
>
> **`run_chapter(pages=...)` 的两态**：可以传已抽好的 `list[str]`，也可传
> `extractor.lazy_pages(path)` 返回的零参可调用对象——命中 `text.txt` 时**根本不触发抽页**。
> 由 `extractor.resolve_pages()` 统一解包，调用方不必关心。

测试场景：
- `providers.build(cfg, None)` → `llm/tts/viz` 三个字段均非 None，且 `stage.cfg is cfg` [TDD]
- `providers.build(cfg, False)` → `cfg["llm"]["think"]` 被覆盖为 False [TDD]
- `run_chapter` 传 `lazy_pages()` + `text.txt` 已存在 → 全程未调用 `extract_pages`（打桩断言）[TDD]
- `run()` 不带任何新参数 → 产物合法、句数与 T2V-001 一致 [端到端]

## 四、数据流

```
input.pdf
   │
   ├─ extractor.extract_pages() ──→ list[str]（页文本，保留页边界）
   │                                      │
   │                                outline.build()  ──→ OutlineDoc ──→ outline.json
   │                                      │
   │                      ┌───────────────┴───────────────┐
   │                      │  for each 选定章 ch            │
   │                      ▼                               │
   │        segmenter.slice_chapter(pages, ch)             │
   │                      │                                │
   │              cache.hit_script(ch)? ──命中──→ ScriptDoc（跳过 LLM，省 ~36s）
   │                      │未命中                          │
   │              scriptwriter.script(text, max_n) → ScriptDoc
   │                      │                                │
   │              cache.put_script() ──→ script.json（人工可改）
   │                      │                                │
   │         ┌────────────┴────────────┐                   │
   │         ▼                         ▼                   │
   │  visualizer.card()×N        narrator.speak_many()×N   │
   │         └────────────┬────────────┘                   │
   │                      ▼                                │
   │              compositor.compose(list[MediaClip])       │
   │                      ▼                                │
   │                 ch<NN>.mp4 ──→ cache.put_video()      │
   └───────────────────────────────────────────────────────┘
```

## 五、数据/结构变更

```text
新增目录：<cache_dir>/<book_hash>/ch<NN>/
新增文件：outline.json · script.json · .keys.json
新增 config 段（config.yaml，均有默认值，老配置可跑）：
  cache:       { enabled: true, dir: null }        # dir=null → <project>/cache
  concurrency: { tts_workers: 12, tts_retry: 2 }
```

> ⚠️ 本项目无 DB/表结构变更。cache 目录为**可选产物**，删除即回到「无缓存」行为（回滚条件）。

## 六、关键代码模板

```python
# pipeline.py —— 编排只做编排，不实现任何环节
def run_chapter(pages, doc, ch, cfg, out_path, c: Cache, no_cache: bool) -> dict:
    text = segmenter.slice_chapter(pages, ch, cfg["limits"]["max_chars"])
    skey = c.script_key(ch.index, text, cfg)

    doc_script = None if no_cache else c.hit_script(ch.index, skey)
    if doc_script is None:
        print(f"  [{ch.index}] 分镜生成中…（{len(text)} 字，跳过缓存）")
        doc_script = llm.script(text, cfg["limits"]["max_sentences"])
        if not no_cache:
            c.put_script(ch.index, doc_script, skey)

    work = c.chapter_dir(ch.index)
    for i, s in enumerate(doc_script.scenes):
        viz.card(s, i + 1, work)
    durs = tts.speak_many([(i + 1, s.text, str(work / f"voice_{i + 1}.mp3"))
                           for i, s in enumerate(doc_script.scenes)],
                          max_workers=cfg["concurrency"]["tts_workers"])
    clips = [MediaClip(i + 1, str(work / f"card_{i+1:03d}.png"),
                       str(work / f"voice_{i+1}.mp3"), durs[i + 1])
             for i in range(len(doc_script.scenes))]
    compositor.compose(clips, str(out_path), str(work))
    return {...}

def run(input_path, out_path, config_path=None, think=None) -> dict:
    """T2V-001 兼容入口：不传章参数 = 取全文当一章（与今天等价）。"""
```

```python
# cache.py —— 三层命中靠「分键」而不是「猜」
def script_key(self, i, chapter_text, cfg) -> str:
    # 只含影响「分镜内容」的因子：改配色不该让最贵的 LLM 产物失效
    raw = f"{self.book_hash}|{cfg['llm']['model']}|{cfg['llm']['think']}|" \
          f"{cfg['limits']['max_sentences']}|{hashlib.sha256(chapter_text.encode()).hexdigest()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
```

```python
# outline.py —— 结构优先，正则兜底，绝不编造
def build(path: str) -> OutlineDoc:
    reader = PdfReader(path)
    doc = _from_pdf_outline(reader)          # 首选：零成本、零幻觉
    if not doc.chapters:
        doc = _from_regex(_all_text(reader), len(reader.pages))
    if not doc.chapters:
        doc = _whole(len(reader.pages))
    return doc
```

## 七、扩展

| 节 | 适用场景 | 本 spec 结论 |
|----|---------|------|
| 安全条件验证方案 | 涉及计费/库存/权限 | N/A（无计费/库存/权限）；但 cache/输出为写操作 → 05_validator §四 仍全跑 |
| 性能预算 | 循环内外部调用/大数据量 | **适用**：首跑 ≤48s、重跑 ≤15s、TTS ≤5s（见 02 §四） |
| 兼容性矩阵 | 对外 DTO/消息体变更 | **适用**：`compose()` 收类型变更 + `run()` 签名不变 → 05_validator TC-10/TC-11 覆盖 |
| 回滚方案 | 涉及结构变更 | **适用**：`.backups/2026091518-*/` 覆盖回 `src/`；cache 目录可直接删 |
| 灰度策略 | 核心链路改动 | N/A（单机 CLI，无灰度对象） |

## 八、文档回写清单

| # | 文档 | 需要更新？ | 变更内容 |
|---|------|:--------:|---------|
| 1 | `laws.md` / 项目宪法 | 否 | 无新增护栏；宪法五条未被触碰 |
| 2 | **`doc/10-目录索引与按需生成.md`** | **是** ⚠️ | 按铁律 3 更正 §4.1「反向依赖」为「契约所有权错位」；§七 实施顺序标注已完成阶段 |
| 3 | `doc/01-llm-local.md` | 是 | 补「章节切分后送模型文本 ≤2500 字」的取料口径 |
| 4 | `HANDOFF.md` | 是 | 更新状态快照（新增 4 模块）、CLI 新命令、缓存目录说明 |
| 5 | `README.md` | 是 | 快速开始补 `outline`/`list`/`--chapter` 用法 |
| 6 | `AGENTS.md` | 是 | 模块地图更新（依赖塔尖 = models.py） |
| 7 | `specs/README.md` | 是 | 本 spec 索引行 + 状态 |
| 8 | `config.yaml` | 是 | 新增 `cache` / `concurrency` 段（带默认值） |
| 9 | `CHANGELOG.md`（仓库根 `../CHANGELOG.md`） | 是 | 本次变更条目 |
| 10 | 项目记忆区 + skill | 是 | `ollama-local-ops` / `zero-cost-visuals-iconify` 按需补；`xingtu/.workbuddy/memory/2026-09-15.md` 记日志 |

# 02 · 需求规格：目录索引与按需生成

> Ticket: T2V-002 | 日期: 2026-09-15 18:51 | 状态: ✅

> 📜 **Check**：本需求不违反 [laws.md](./laws.md) 与项目宪法。特别对照：铁律一（零公司资源）——本 spec 不新增任何外部服务，
> TTS 并发仍走 edge-tts（免费匿名）+ say（完全本地）；铁律四（MVP 优先）——P5 网页点播已明确移出范围。

## 一、用户故事

- 作为**行途（内容生产者）**，我希望输入一本书就能看到它的目录，并**指定第几章**出片，以便长书不再只能出「开头一小段」。
- 作为**迭代中的作者**，我希望改一句文案后重跑只要十几秒，以便快速试错封面配色与措辞。
- 作为**接手的 AI/同事**，我希望每个模块只做一件事、契约集中在一处，以便改一个文件不牵动全身。

## 二、验收标准（16 条，其中 P0 8 条）

| # | 验收标准 | 验证方式 | 优先级 |
|---|---------|:-------:|:-----:|
| AC-1 | `run outline <pdf>` 产出 `outline.json`；本样本章节条数 = PDF 内嵌 outline 条数（93），且带页码 | 命令 + JSON 断言 | P0 |
| AC-2 | `list <pdf>` 打印两级章节树，**顶层章 22 条**（小节 71 条，合计 93），每行含页码与标题 | 命令 | P0 |
| AC-3 | 无内嵌 outline 的 **PDF** → 正则「第X章」兜底，`origin="regex"`；两者皆失败 → `origin="whole-doc"` 且 `chapters` 长度 = 1。**非 PDF（MD/长文）一律 `whole-doc`**：无页边界即无「章→页」映射，硬分章会让每章切片到整篇 | 单元 | P0 |
| AC-4 | `run --chapter 3` 只出第 3 章；送 LLM 的文本**全部落在第 3 章页码范围内**，无相邻章正文混入 | 命令 + 产物核对 | P0 |
| AC-5 | `run --chapters 1,3,5` 产出 3 个 mp4；章号越界时**明确报错**，不静默跳过 | 命令 | P1 |
| AC-6 | `--all` 章级串行出全部顶层章；单章失败不阻塞其余章，末尾汇总失败清单并以非 0 退出码标识 | 命令 | P1 |
| AC-7 | 超长章（34 页 > 2500 字）切分**均匀采样首/中/尾**而非只取开头；返回长度 ≤ `max_chars` | 单元 | P0 |
| AC-8 | TTS 12 句并发耗时 ≤ 5s 且成功 12/12（基线：串行 28.9s，10/12） | 命令 + 计时 | P0 |
| AC-9 | 单句 TTS 失败自动重试 ≤ 2 次；失败率 > 50% **自动降并发**重跑失败项；最终失败抛错并回退 `say`，不静默产出空音频 | 单元 | P0 |
| AC-10 | 缓存三层语义：①全命中 → **≤2s** 返回既有 mp4 ②`script.json` 命中 → 跳过 LLM（省 ≥30s）③`script.json` 被手改 → **只重跑下游、不动 LLM**。前提：命中路径**不得**重复解析全书（大纲读 `outline.json`、章文本读 `text.txt`、抽页延迟执行） | 命令 + 计时 | P0 |
| AC-11 | 改一句文案后重跑 ≤ 15s。两个口子语义不同，需分别成立：①改 `script.json`（分镜）→ 只重渲染 ≈9s，**不跑 LLM** ②改 `text.txt`（素材）→ `script_key` 变 → 重跑 LLM（此时 ≤15s 不适用，属换素材） | 命令 + 计时 | P1 |
| AC-12 | 跨模块传参一律 `models.py` dataclass；`compose()` 收 `list[MediaClip]` 且**兼容**旧三元组 | 单元 | P1 |
| AC-13 | `models.py` 不 import 任何同包模块（依赖图塔尖，可用 `ast` 断言） | 单元 | P1 |
| AC-14 | `run --input --out`（**不带任何新参数**）行为与 T2V-001 完全一致（同等句数、同等产物合法性） | 单元 + 端到端 | P0 |
| AC-15 | 全程零公司 key；成本日志仍打印 ≈¥0；`--no-tts-net` 切 `say` 后**离线可出片** | 命令 + 代码审计 | P0 |
| AC-16 | 除 `icons.py`（纯映射表，豁免）外，每个模块 ≤ 200 行（新增模块 `providers.py` 同样计入） | 命令（`wc -l`） | P2 |

> 验证方式：命令 = CLI 可跑 | 单元 = 单测/断言脚本 | 端到端 = 真出 mp4 并 ffprobe 校验。

## 三、影响范围

| 模块/文件 | 变更类型 | 说明 |
|------|---------|------|
| `src/book2vido/models.py` | **新增** | 数据契约（Chapter/OutlineDoc/Scene/ScriptDoc/MediaClip） |
| `src/book2vido/outline.py` | **新增** | PDF/MD → 章节树，三层兜底 |
| `src/book2vido/segmenter.py` | **新增** | 章节 → LLM 文本片段（均匀采样） |
| `src/book2vido/cache.py` | **新增** | 三层缓存（成片/分镜/无） |
| `src/book2vido/extractor.py` | 修改 | 新增 `extract_pages`/`page_slice`；`body()` 标 deprecated 但**保留** |
| `src/book2vido/narrator.py` | 修改 | 新增 `TTSProvider.speak_many`（重试 + 降并发） |
| `src/book2vido/scriptwriter.py` | 修改 | `Scene` 改为从 `models` 导入（保留 re-export 兼容）；接受外部传入文本 |
| `src/book2vido/pipeline.py` | 修改 | 拆 `run_chapter`/`run_book`；保留 `run()` 原签名；命中路径改为读缓存 + 延迟抽页 |
| `src/book2vido/providers.py` | **新增** | 环境装配：`Stage` + `build(cfg, think)`（从 pipeline 拆出，见 `03_design` §3.5） |
| `src/book2vido/__main__.py` | 修改 | 新增 `outline`/`list` 子命令与 `run` 的可选参数 |
| `config.yaml` / `config.py` | 修改 | 新增 `cache` / `concurrency` 段（带默认值，老配置可跑） |
| `packaging/launcher.sh` | 不改 | 默认行为必须与今天一致（AC-14 覆盖） |
| `doc/10-目录索引与按需生成.md` | 修改 | 按铁律 3 更正「反向依赖」判断（见 `01_analysis` §二） |

## 四、非功能需求

- **性能**：首跑整章 ≤ 48s（基线 ~75s）；**全命中重跑 ≤ 2s**（实测 0.322s）；
  **改分镜重渲染 ≤ 15s**（实测 ≈9s）；TTS 12 句 ≤ 5s。
  > 命中路径**不得重复解析全书**——`outline.build` 6.0s + `extract_pages` 5.9s 是白干，
  > 实测曾因此让"全命中"变成 19.9s。修法见 `03_design` §3.3 的两个缓存面 + §3.5 的延迟抽页。
- **兼容性**：`pipeline.run(input_path, out_path, config_path, think)` **签名与语义不变**；`compose()` 兼容旧三元组；
  `extractor.body()`/`chapters()` 不删（外部脚本与 `RuleFallbackProvider` 在用）。
- **幂等性**：同 cache key 覆盖写不产生重复产物；`cache/<book_hash>/ch<NN>/` 章间目录隔离，并发不同章无写冲突。
- **可观测性**（军规 progress_visibility）：每章打印 `[i/N] 章名`，每步打印进展；失败打印原因不静默；`--all` 末尾汇总。
- **上下文约束**：送本地模型的文本 ≤ 2500 字（4K ctx 硬约束，`doc/01-llm-local.md`）。
- **成本**：仍为 ≈¥0（仅电费），成本日志格式不变。

## 五、安全条件（必填）

> 本项目无计费/库存/权限；但存在**写操作**（cache 目录 + 输出 mp4），故三条件硬性必填。

| 条件 | 说明 | 具体措施 |
|------|------|---------|
| **退出条件** | 什么时候停止？ | ①`--no-cache` 整体关缓存 ②TTS 并发失败率 > 50% → 降并发 → 再失败 → 退串行 → 仍失败则抛错（**有上限，不无限重试**）③`--all` 单章失败记录后继续（不阻塞） |
| **幂等条件** | 重复执行不产生副作用 | cache key = 文件内容哈希 + 相关 config；同 key **覆盖写**；章间目录隔离；重跑同一章产出一致（不追加、不重复） |
| **回滚条件** | 失败后如何恢复 | 仅新增模块 + 改调用点，**不删任何公开函数**；回滚 = 用 `.backups/2026091518-*/` 覆盖回 `src/`；新参数全部可选 → 不传即旧行为 |

## 六、扩展

### 6.1 CLI 契约（本次唯一对外接口变更）

```yaml
# 新增子命令
book2vido outline <input>            # 建索引 → <cache>/outline.json
book2vido list    <input>            # 打印章节树

# run 新增可选参数（全部可选，不传 = T2V-001 行为）
book2vido run --input <path> --out <path>
  [--chapter N]                      # 只出第 N 章（1-based 顶层章）
  [--chapters 1,3,5]                 # 多章
  [--all]                            # 全部顶层章（--out 视为目录）
  [--jobs N]                         # TTS 并发度，默认 12；仅影响 TTS，不影响 LLM
  [--no-cache]                       # 关闭缓存
  [--cache-dir <dir>]                # 缓存根目录，默认 <project>/cache
  [--fast]                           # 既有：关闭思考模式
```

### 6.3 数据模型（新增落盘结构，非 DB）

```
<cache_dir>/<book_hash>/              # book_hash = sha256(文件字节)[:16]
  outline.json                        # OutlineDoc ← 人工可改（改完重跑生效）
  ch01/
    text.txt                          # 章切片结果 ← 省 348 页抽取；改了=换素材
    script.json                       # ScriptDoc ← 最贵产物，人工可改
    .keys.json                        # 当前 script_key / video_key
    card_001.png ...                  # 画面
    voice_001.mp3 ...                 # 配音
    ch01.mp4                          # 成片
  ch02/ ...
```

**键分层（关键设计）**：三类产物失效条件不同，必须分开算键，否则「改配色」会白扔最贵的 LLM 产物。

| 键 | 输入 | 失效场景 |
|---|---|---|
| `book_hash` | 文件字节 | 换书 |
| `script_key` | `book_hash` + model + think + max_sentences + **章节输入文本** | 换模型/改思考/改素材 |
| `video_key` | **sha256(分镜规范化 JSON)** + voice + accent + w + h + icon_size | 换配色/音色/**手改分镜**（均不动 LLM） |

> ⚠️ `video_key` 挂**分镜内容指纹**而非 `script_key`——理由见 `03_design` §3.3 的说明（实现期发现的规格缺陷，已 Reverse Sync）。


# HANDOFF · book2vido 会话交接

> **交接给**：接续本项目的下一个 AI 模型 / 开发者
> **生成**：2026-09-15 · 小研（WorkBuddy，specs 驱动开发）
> **更新**：2026-09-15 20:05（T2V-003 收口 + 私有仓推送）
> **一句话状态**：T2V-001（整本一条片）+ **T2V-002（目录索引 + 按章生成 + 三层缓存）** +
> **T2V-003（错题库 / KB / 构建门禁 / 非技术用户 UX / 私有仓）已落地并验通**；
> 远端 **`github.com/xingtu1996/book2vido`（PRIVATE）** 已推送，commit `3986c88`。

---

## 0 · 30 秒上手

| 问题 | 答案 |
|---|---|
| 这是什么 | 把书 / 长文 → 「能看完」短视频的**零成本**本地流水线 |
| 项目在哪 | `<仓库根>/` |
| 驱动方式 | **specs 驱动**：当前活跃 `specs/2026091518-book2vido-chapter/`（T2V-002）；历史 `specs/20260915-book2vido-mvp/`（T2V-001） |
| 现在到哪 | ✅ MVP 跑通 → ✅ **按章点播 + 三层缓存跑通**（全命中 0.322s）→ ✅ **已推私有仓 `xingtu1996/book2vido`**（等 boss 看 diff 后定协议/是否公开，见 §3 待办与 `doc/12`） |
| 最大红线 | **禁用任何公司 API key**（见 §1） |

---

## 1 · 合规红线（换任何模型都必须守，最高优先级）

- **铁律一 · 零公司资源**：本项目**不得调用任何公司订阅的 LLM / API key**（含 CodeMax、DeepSeek 公司身份、一切公司 key）。公司资源与行途（个人 IP）内容生产**物理隔离**。
- **只允许**：本地模型（Ollama）+ 免费匿名服务（edge-tts）+ 完全本地（macOS `say` / FFmpeg）。
- **铁律七 · 克制**：**根本底牌 = 极致性能压缩 + ¥0**。引入任何外部资产（"宝藏风格包"类）
  先过三道闸（费用 / 体积 / 替换），**任一为否即不接**。最省的依赖是不引入的那个依赖。
- **铁律八 · 工程的取舍顺序**：**可读性第一，性能例外**。确有效率影响时性能优先，
  但"有效率影响"必须能回答**慢在哪 / 慢多少 / 谁测的**，并就地注释说明原因。
- **铁律九 · 思想的搬运工**：**免费 · 不出本机 · 断网跑得完**。
  ① 只换载体不造思想（智能只用在"怎么呈现"，不用在"说什么"）；
  ② 用户内容**全程不出本机**；③ 断网必须跑得完 ——
  判据是 `python tests/verify_offline.py --tts say`（socket 层拦全部外网），**外网请求须为 0 且出片**。
  ⚠️ **默认 `tts.provider=edge` 需网**：断网能自动回退 `say`，但实测**多花 27.7s**（71.0s vs 43.3s）——
  离线 / 隐私场景应**主动**用 `say`，不要指望自动降级。
- 完整铁律见 [`CONSTITUTION.md`](CONSTITUTION.md) —— **以该文件为准，此处不硬编码条数**
  （硬编码计数是必然漂移项，见 `doc/lessons` 计数漂移条目）。
  **违反＝作废，代码再漂亮也没用。**

---

## 2 · 项目定位与设计哲学

> 身边人抱怨「字太多看不下去」——本质是**高密度文本 → 低门槛连续视觉叙事**的降维需求。

一条纯本地的 MVP 闭环：`pypdf 抽取 → Ollama 精炼口播稿 → Pillow 信息卡 → edge-tts 配音 → FFmpeg 合成`。

设计哲学（**完整清单以 [`README.md`](README.md) §设计哲学 为准，此处不复制条数——它已漂移过一次**）：
**集百家之长**（不造轮子，复用 Ollama/pypdf/edge-tts/FFmpeg）· **MVP 优先** · **极致省资源**
（不烧文生图/文生视频 API，质量目标＝「能知道内容就好」）· **零公司资源** · **克制** · **可读性第一，性能例外**。

---

## 3 · 当前状态快照（截至 2026-09-15 23:55）

> **计数口径（本节尤其适用）**：模块数与行数一律**以 `wc -l src/book2vido/*.py` 为准**，
> 依赖方向用 `python tests/verify_deps.py` 一键核。本节出现的模块数是**写入当时**的快照，
> **不作为当前值**——硬编码计数已在 2026-09-15 一天内漂移三次（见 `doc/lessons` L-14/L-18）。

### 🆕 T2V-002 · 目录索引与按需生成（2026-09-15 19:00 落地）

**从「整本拍平成一条片」升级为「读目录 → 按章点播 → 每章一条片，重跑不重算」。**

新增 5 个模块（`models` / `outline` / `segmenter` / `cache` / `providers`）。
（**当前模块数不在本文写死**，以 `wc -l src/book2vido/*.py` 为准 —— 见本节开头口径。）

| 能力 | 命令 | 实测 |
|---|---|---|
| 读目录树 | `list <pdf>`（**位置参数**） | 348 页 → **顶层 22 章** + 小节 71 = 93 条，带页码 |
| 建索引落盘 | `outline <pdf>` | `cache/<hash>/outline.json`（人工可改，改完重跑生效） |
| 只出第 N 章 | `run --input X --out Y --chapter 8` | 第 3 章 12 句 / 39.7s / 735KB |
| 多章 / 全部 | `--chapters 1,3,5` / `--all` | 章级串行、章内 TTS 并发 |
| 关缓存 | `--no-cache` | 退回旧语义，不读不写 cache |
| 全命中重跑 | 同上再跑一次 | **0.322s**（旧实现 19.9s） |
| 改分镜重渲染 | 手改 `script.json` 再跑 | **≈8.5s**，**不跑 LLM** |

**缓存三层（分键是核心）**
```
cache/<book_hash>/                  book_hash = sha256(文件字节)[:16]
  outline.json                      大纲（人工可改）
  ch08/
    text.txt                        章切片（省 348 页抽取；改了=换素材→重跑模型）
    script.json                     分镜 ← 最贵产物，人工可改
    .keys.json                      当前 script_key / video_key
    card_*.png · voice_*.mp3 · ch08.mp4
```
- `script_key` = book_hash + model + think + 句数 + **章节输入文本**（改配色**不动**它）
- `video_key` = **sha256(分镜规范化 JSON)** + 音色/配色/尺寸（手改分镜只重渲染下游；
  取规范化 JSON 而非原始字节 → 只动缩进/空白不废成片）

**实施期修掉的 5 个"看不见的"缺陷**（详见 `specs/2026091518-book2vido-chapter/01_analysis.md` §七
+ `verification-report.md` §四）
1. `video_key` 原挂 `script_key` → 手改分镜**被静默丢弃**（命中旧分镜的成片）
2. 命中路径每次白解析全书 **11.9s**（`extract_pages` 5.9 + `outline.build` 6.0）
3. `outline.json` 的"人工可改口子"是**假的**（每次重建，落盘白存）
4. **长章切片尾部被截**：三段预算没扣省略分隔符 → 兜底 `text[:2500]` 从**尾部**切，
   恰好切掉尾段存在的意义（章尾）。另 `text.txt` 缓存键**不含采样算法** → 修了也不生效。
   已加 `segmenter.VERSION`（**改取料逻辑必须 +1**）
5. `--chapter 0` **静默走整本出片**（`bool(0)` 被判成"没给参数"，退出码 0、无任何提示）

> 🔑 **模式**：以上 5 个里有 4 个同属**"键/缓存/落盘文件"这类看不见的契约**——
> **不报错、只静默走错分支或静默不生效**。本项目累计已 6 次踩这类（含跨项目的术语改一处、
> 信息图 HTML 改了 PNG 没重渲染）。**动"缓存键 / 派生文件 / 落盘中间产物"时，先问：
> 用户改了 X 之后，键变了吗？产物会重算吗？**

**已知限制**：非 PDF（MD/长文）**无法分章**，一律 `whole-doc`。
原因：无页边界 → 无「章→页」映射，硬分章会让每章都切片到整篇，比粒度粗更糟。

**验收**：AC **16/16 通过**（`specs/2026091518-book2vido-chapter/verification-report.md`）。
⚠️ 该报告是**主线自查**，非独立第三方验收（原定独立单元 18m27s 无产出被终止）。

> 变更摘要另见 `CHANGELOG.md`。

### ✅ 已成（T2V-001）
- **代码全落地**：`src/book2vido/` **15 个模块**真跑通。
- **运行方式已修好**：`pip install -e .` 后，**在项目根目录**即可 `python -m book2vido run`。
- **画面层可用**：Iconify 离线图标（缓存 **118 个**）+ 主视觉面板 + **受控概念清单**，
  实测 **12/12 语义命中、零重复图标**。
  - ⚠️ 此前被记为「12/12 语义命中」的是**有图标率**，不是语义命中率。
    boss 出片后实图核对：首版 12 张卡只有 **6 个不同图形**（拼图撞 3 次、菱形 2 次），语义相符不到 1/3。
  - 根因＝「让 LLM 自由出词、再事后翻译成图标」的架构错位；修法是把**受控词表前置进 LLM 输出约束**。
  - 完整病灶/药方/验证见 `doc/08-画面资产策略.md` §六。
- **一键安装已跑通**：`bash packaging/build_app.sh` → `dist/Book2Vido.app`（**131 MB**，2026-09-15 实测）。
  拖 PDF 到图标即出片，**全程走随包运行时，用户不需装 Python / Ollama / 任何依赖**。
  ⚠️ T2V-002 后需重建（多 5 个模块；`build_app.sh` 整体拷目录，无需改脚本）；**体积随随包运行时变动，引用前先实测**。
- **不再钉死本机**：新增 `binpaths.py`，清掉 4 处硬编码（ffmpeg / ffprobe / rsvg / DYLD_LIBRARY_PATH）。
- **样片**（2026-09-15 `ffprobe` 实测；**KB 一律按 `字节/1024`**，此前表格混用过 `/1000`，读数会差 2–3%）
  ｜ 面向访客的成品展示见 [`demo/README.md`](demo/README.md)：

| 文件 | 状态 | 时长 / 体积 | 备注 |
|---|---|---|---|
| `samples/关键对话_v2.mp4` | ✅ 画面层修复后 | 23.3 s / 543 KB | 12/12 图标语义命中、零重复；生成耗时 91.4 s |
| `samples/关键对话_拖拽版.mp4` | ✅ **.app 出片** | 23.1 s / 518 KB | **打包验收**（boss 亲测拖拽） |
| `samples/t2v_ch03.mp4` | ✅ **按章生成** | 36.7 s / 670 KB | 书内**第 3 章**（p068-p092）——对应 CLI **目录序号 8** |
| `samples/chapters/第1章_何谓关键对话.mp4` | ✅ 批量 | 33.3 s / 613 KB | `--chapters 6,7` 同一次命令产出 |
| `samples/chapters/第2章_掌握关键对话.mp4` | ✅ 批量 | 35.7 s / 638 KB | 同上 |
| `samples/g/ch01·ch03·ch05.mp4` | ✅ `--fast` 快筛 | 29.3 / 34.0 / 38.9 s | 目录第 1/3/5 条 = 赞誉 / 第1版序 / 前言（**非正文章节**） |
| `samples/省Token实战包装.mp4` | ✅ 泛化（自有素材） | 39.0 s / 706 KB | 输入不是书，是一篇干货笔记 |
| `samples/关键对话_ollama.mp4` | ⚠️ **画面空白** | 27.7 s / 359 KB | 画面层修复**前**产物：整帧只有序号 + 水印，标题/图标/说明全空（中部墨量 0.0000–0.0002，正常片 0.05–0.07）。**不宜作 demo** |
| `samples/关键对话_sample.mp4` | ⚠️ **画面稀疏** | 360.1 s / 5.4 MB | rule 降级路径早期产物，墨量 0.004–0.010；保留作历史证据 |
| ~~`samples/人话翻译术.mp4`~~ | ❌ **文件已不在** | — | 原记录为「run2 卡死，见 §5.8」；现仅剩 `samples/.work_人话翻译术/` 目录 |

### ⏳ 待办 / 未决
- 🔴 **公开前阻塞（2026-09-16 新增，务必先读）**：项目已由 `text2vido` **更名为 `book2vido`**（全库），
  当前阻塞项：
  1. ✅ ~~远端仓名仍是 `text2vido`~~ → **2026-09-16 已完成**：远端已改名为
     `xingtu1996/book2vido`（仍私有），`origin` 已指向新地址。
  2. **git 历史里含绝对路径 `/Users/<用户名>/…`**（`git log -p | grep -c` 实测 42 处）。
     ⚠️ **清工作区 ≠ 可公开** —— 真要 `--public` 必须先**历史重写**（`git filter-repo`，或压成单条初始提交）。
     另 `specs/` 有 3 个**验证记录**含该路径且**刻意未改**（改写＝篡改证据），见 `specs/README.md` 红框。
  `CodeMax` 字面提及亦未清。
- **ffmpeg 未内置**（打包唯一硬缺口）：homebrew 版绑 **18 个 dylib**，不可分发。
  需注入 static build：`BOOK2VIDO_FFMPEG_SRC=/path/ffmpeg bash packaging/build_app.sh`
- **目录感知分片未做**：当前是「整篇抽 12 句」，对长书信息损失大 —— 下一轮最高价值项。
- **N 选 1 校验未做**：单次生成方差大（同任务测出 3 种体裁/3 种耗时）。
- **run2 卡死未定位**（§5.8）。
- ~~**git 未 init**；远程 `xingtu1996/book2vido` 未创建~~ → ✅ **2026-09-15 已完成私有推送**，见 §3.1。
- 协议 / 是否公开：**等 boss 看 diff 后拍板**（`doc/12` §05）。
- 开源仓收尾：README 打磨、示例素材、CI（可选）——**以"是否公开"为前提**。

> **2026-09-16 更名影响（接续者注意）**：`import` 名、`Book2Vido.app`/`.dmg`、
> `BOOK2VIDO_*` 环境变量、输出目录 `~/Movies/Book2Vido`、日志目录 `~/Library/Logs/Book2Vido`
> 全部已随更名变更。**缓存无需清**（键是内容指纹，非包名）。完整变更表见 `CHANGELOG.md` 文首。

---

## 3.1 · 远端仓库（2026-09-15 私有推送）

| 项 | 值 |
|---|---|
| 地址 | `github.com/xingtu1996/book2vido`（**PRIVATE**） |
| 分支 | `main`（已 `-u` 绑定 `origin/main`） |
| 协议 | SSH（`~/.ssh/config` 已把 `github.com` 指向 `ssh.github.com:443`，密钥 `~/.ssh/github_xingtu`） |
| 提交身份 | `行途 XingTu <274853659+xingtu1996@users.noreply.github.com>`（**仓库级 local，未动全局**） |
| 首提交 | `3986c88` 初始提交（213 文件入库） |

⚠️ **推送环境坑（换机必读）**：沙箱内 `github.com:443` 被网络策略拦截——`api.github.com` 放行
（所以 `gh api` / `gh repo create` 正常），但 git 的 SSH / HTTPS 通道全断
（报 `502 CONNECT tunnel failed` 或 `ssh_dispatch_run_fatal ... timed out`）。
**所以 `git push` 必须跳出沙箱执行**（WorkBuddy 会弹授权）。推送成功后别只看返回码，
要用 `gh api` 复验**作者身份**与**目录树**。
- 发布/宣发未启动（引擎开源 + 内容分发的联动）。

---

## 4 · 环境与运行

| 项 | 值 |
|---|---|
| Python | `$HOME/.workbuddy/binaries/python/envs/default/bin/python`（已装 pypdf/Pillow/edge-tts/pyyaml，并 `pip install -e .`） |
| Ollama | `qwen3:8b`（**正确标签是 8b，`qwen3:7b` 不存在**）；服务 `http://localhost:11434` |
| ffmpeg / ffprobe | `/opt/homebrew/bin/ffmpeg`（**Bash 默认 PATH 可能不含，一律用绝对路径**） |
| 配置 | `config.yaml`（`llm.provider: ollama`/`rule`，`tts.provider: edge`/`say`） |

```bash
cd <仓库根>
PY=$HOME/.workbuddy/binaries/python/envs/default/bin/python
rm -rf src/book2vido/__pycache__          # ← 改代码后必做（见坑 #4）
$PY -m book2vido run   --input "<文件.md|pdf>" --out samples/xxx.mp4
$PY -m book2vido batch --batch "<目录>"        --out samples
$PY -m book2vido run --input x.md --out y.mp4 --fast    # 关思考，快约 2 倍（质量下降）

# 性能基准（6 用例，测 TTFT / 预填充 / 解码 t/s / 内存）
$PY tools/bench_ollama.py

# 零安装网页台（流式对话 + 实时性能面板 + 卸载模型释放内存）
bash tools/start_webui.sh        # 打开 http://localhost:8123/ollama_webui.html
```

**资源现状**：`/Users` 余 41 Gi（91% 占用，高位）；Ollama `llama-server` 常驻 **5.9 GB**（M1 Pro 16 GB，实测 100% GPU；跑时别同时开重应用），冷启动加载 5.2 GB 耗时 **4.91s**。单条样片仅 0.3–6 MB，磁盘**不是**瓶颈。

**性能基线（2026-09-15 实测，勿凭感觉）**：解码 **14–17 tok/s**（硬上限，与输入长度无关）；
预填充最高 **1332 tok/s**（2500 字正文约 2s）；首字延迟关思考 0.12–0.79s、**开思考 27–67s**。

---

## 5 · 已知坑清单（必读）

| # | 症状 | 根因 | 修复状态 |
|---|---|---|---|
| 1 | 一直走 rule，没调 Ollama | `pipeline.run` 未传 `config_path`，`load(None)` 永远用默认 | ✅ 已修（`__main__` 默认读项目根 `config.yaml`） |
| 2 | 抽到的不是正文（是版权页/致谢） | `extractor.body()` `min_skip=600` 排除了真实「第1章@465字」 | ✅ 已修（`min_skip=150`） |
| 3 | Ollama 报 `request body is empty` | `format:"json"` 在 qwen3+ollama0.33 有坑 | ✅ 已修（去掉 format，正则从文本提取 JSON 数组） |
| 4 | 改了代码不生效、静默回退 rule | `__pycache__` 旧字节码 | ✅ 已约定：每次重跑前 `rm -rf __pycache__` |
| 5 | concat 崩 / clip 路径错乱 | `list.txt` 写相对路径，被 concat demuxer 二次解析 | ✅ 已修（写 `c.resolve()` 绝对路径） |
| 6 | 两次运行互相覆盖卡片/片段 | `_cards/_clips` 共享目录 | ✅ 已修（每次运行隔离 `.work_<文件名>/`） |
| 7 | 回退 `say` 后 `voice_N.mp3` 为 0 字节 | `SayProvider` 先出 `.aiff` 再转 mp3；缺输出非空校验 | ✅ **已修**（转完校验 `>0` 字节，否则当场抛错） |
| 8 | run2 卡死 20+ 分钟，无进展、进程僵死 | 未定位：疑似 §5.7 连锁 → edge-tts 无超时 hang | 🟡 **已加超时兜底**（`asyncio.wait_for` 45s；超时抛错→`pipeline` 自动回退 `say`），**待长素材复测确认** |
| 9 | edge-tts 偶发 `NoAudioReceived`（本次实测 1/6 失败、紧接着重测 5/5 成功） | 免费匿名服务偶发抖动 | ✅ 已有兜底（`pipeline` 的 `except` 捕获后切 `say`）。**不必修，但要预期它会偶发降级** |
| 10 | 改了提示词，产出**一点没变** | 缓存键只含 `model/think/句数/章节文本`，**漏了提示词** → 静默命中旧分镜（耗时 0.0s、退出码 0） | ✅ **已修**（T2V-007：键追加提示词指纹；改一个字符即失效，实测 38.4s/miss） |
| 11 | **22 字的附录被出了 12 句**（同义反复；12 张卡同时退化成 2 个图标），而日志**全绿** | 上游守卫只有 `if not text.strip()` —— 挡得住"整章取不到文本"，挡不住"**章的文本只有 5 个字**"；而"出 N 句"是硬约束，缺口只能靠编 | ✅ **已修**（下限判据「**原句数 ≥ `limits.max_sentences`**」+ 四入口接线。⚠️ **行为变更：`--all` 22 集 → 17 集**。见 `doc/21` §04） |

> **#11 的复发判据**：凡是"**必须出 N 个**"的硬约束环节，都要问一句「**上游料不够时会发生什么**」。
> 判据本身也要能被证伪 —— 跑 `python tests/verify_gate.py <book.pdf>`（14 条断言 + 真实截面 + **正文章零误伤**断言）。

**#8 排查进度（2026-09-15 18:20）**：① edge-tts 超时 ✅ ｜ ② `SayProvider` 非空校验 ✅ ｜
③ `pipeline` 逐句打印「句 N/总」⬜ **未做** ｜ ④ 长素材复测 ⬜ **未做**。
→ 下一棒只需补 ③ + ④ 即可闭环。

---

## 6 · 下一步任务（M3 = **C 双线同周**，boss 已拍板）

**线 A · 内容工厂**（把 `素材库/素材卡_*.md` 批量变视频）
- [ ] 修 §5.8 卡死 → 重跑 `人话翻译术` 等 2–3 篇，凑齐 ≥3 条泛化样片
- [ ] 出一个「素材卡 → 短视频」的批量脚本/SOP（对接 `batch` 子命令）
- [ ] 选题：优先利他、对准「Vibe Coder 的工程化启蒙」受众

**线 B · 引擎仓**（`xingtu1996/book2vido`，**当前 PRIVATE · 协议待裁决**）
- [x] ✅ `git init` + 首次 commit `3986c88`（213 文件）—— 2026-09-15
- [x] ✅ `gh repo create xingtu1996/book2vido --private` + push（**boss 已批准私有推送**）
- [ ] **等 boss 看 diff 后拍板**：协议走 A（私有保留权利）/ B（Apache-2.0 分层）/ C（MIT）/ D（AGPL）
      → 见 `doc/12` §05；`LICENSE` 是否从 MIT 换掉
- [ ] 若将来公开：先清「公开前必清」13 + 8 个文件（绝对路径 / CodeMax 字面），再 `--public`
- [ ] README 打磨：样片截图/GIF、真实成本对比、竞品差异（`doc/07-competitors.md`）
- [ ] 卡位：**「免费不烧钱」** vs `huobao`(1.5万★但烧 API 钱) 的空白生态位

**待 boss 拍板**：① 协议 A/B/C/D + 是否公开；② 是否同时开内容分发（择时）；③ 宪法铁律五是否按 `doc/12` §04 改写。

---

## 7 · 文件地图

```
book2vido/
├── README.md / CONSTITUTION.md / LICENSE(MIT・待裁决) / CONTRIBUTING.md / HANDOFF.md(本文)
├── AGENTS.md / CLAUDE.md(→@AGENTS.md) / SECURITY.md / CHANGELOG.md / .editorconfig / .gitignore
├── SESSION_PROVENANCE.json  # ★ 过程信源坐标：会话 id / 五份本地痕迹 / readRecipe / cannot
│                   #     用途：追溯「这活是怎么变成现在这样的」· 换 harness 接手时读
│                   #     ⚠️ 含绝对路径，**内部文件，不得随公开仓分发**
├── config.yaml / requirements.txt / pyproject.toml
├── prompts/        # ★ 提示词资产：scriptwriter.md —— 分镜唯一的「模型行为」来源
│                   #     与 config.yaml 同级（同一套 parents[2] 定位法）· 改它不必动 Python
├── doc/            # KB（入口：doc/README.md 索引）
│                   #     01-llm 02-抽取 03-画面 04-tts 05-合成 06-发布 07-竞品 08-画面资产
│                   #     09-一键安装与分发 10-目录索引 11-产品化路线 12-交付形态与许可决策
│                   #     13-确定性与模型分工 14-产物演进史 15-提示词与模型适配（MD）
│                   #     16-项目总览（MD·入口层）17-结构诊断 18-商业化规划 19-社会价值与爆红预案
│                   #     20-需求收敛与形态定位 21-书到视频规格盘点（★ 逐条目真实账目 + 下限缺陷实证）
│                   #     22-产品诞生始末与终局（★ 七阶段诞生史 + 换 harness 接手 + 公开三道不可逆前置）
│   ├── lessons/    # ★ 错题库（现象/真因/修法/复发判据 + §三发布前速查；条数以该文件为准）
│   ├── learn/      # ★ 学习中心（教学层，5 篇）：AI项目工程化 / 大模型与本地推理 /
│   │               #     提示词即资产 / 确定性与缓存 / 动手实验（配 mermaid 图 + 可跑命令）
│   │               #     ⚠️ 它**不产出新结论**，只把 01–24 的结论讲成人话
│   └── assets/     # audit/（缺陷实证：帧条 + 原片）· evolution/（产物演进四代帧 + 追加规范）
├── demo/           # ★ 看效果：画廊 README.md + index.html（本地可播）
│                   #     videos/ 9 条样片 · gifs/ 9 张自动播放动图 · posters/ 9 张封面 · shots/ 3 张截图（约 7.5 MB）
├── specs/20260915-book2vido-mvp/     # 历史规格（T2V-001）
├── specs/2026091518-book2vido-chapter/  # 历史规格（T2V-002/003）
├── specs/2026091521-book2vido-prompt/   # ★ 当前规格 SSoT（T2V-007 提示词资产化）
├── packaging/      # ★ 打包分发：Info.plist · launcher.sh · build_app.sh（含可分发性门禁）
├── dist/           # 构建产物 Book2Vido.app（约 130 MB，git 忽略）
├── tests/          # ★ **会红的断言**（2026-09-16 从 tools/ 分出；清单见 tests/README.md）
│                   #   verify_deps.py（依赖方向）· verify_prompt.py（与基准逐字节）
│                   #   verify_icons.py（图标自洽）· verify_gate.py（出片下限判据）
│                   #   verify_offline.py（铁律九：外网请求=0）· verify_cache.py ·
│                   #   verify_segmenter.py · verify_narrator_concurrency.py · prompt_golden.txt
├── models/         # ★ 模型**台账**（不存权重，权重在 ~/.ollama/models）：
│                   #   用哪个 / 五步换模型 SOP / 降级路径 / 红线
├── logs/           # 运行日志（**默认不写盘**，需排查时 --log-file logs/xxx.log；*.log 已忽略）
├── tools/          # **量具**（一次性探针 / 基准 / 剖析）：bench_ollama.py · probe_*.py ·
│                   #   profile_pipeline.py · preview_theme.py · ollama_webui.html + start_webui.sh
│                   #   ⚠️ 判据在 tests/，量具在 tools/ —— 分界见 doc/24-目录分区规范.md
├── src/book2vido/  # 实现（icons.py / binpaths.py / outline.py / segmenter.py / cache.py / providers.py / promptlib.py）
└── samples/        # 样片：chapters/ 按章 · g/ --fast 快筛 · *.png 信息卡总览
                    #       + 运行时隔离产物 .work_<文件名>/（git 忽略）
```

---

## 8 · 给下一棒的 checklist

1. 读 `CONSTITUTION.md` + 本文件 §1，确认**不碰公司 key**。
2. `cd book2vido && rm -rf src/book2vido/__pycache__`，跑一条 `run` 确认环境 OK。
3. 排查 §5.8 run2 卡死（先修 §5.7 的 0 字节校验 + edge-tts 超时）。
4. 按 §6 推进；**push / 公开发布前必须找 boss 拍板**。
5. 改动同步 `specs/.../04_tasks.md` 的执行账，别让规格与代码漂移。

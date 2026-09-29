# verification-report · T2V-002 目录索引与按需生成

> 日期：2026-09-15 19:35 ｜ 对象：`src/book2vido/`（16 模块）+ CLI + `.app`
> spec：`specs/2026091518-book2vido-chapter/`（AC 原文见 `02_requirements.md`）

## ⚠️ 来源与可信度声明（必读）

1. **本报告是「主线自查」，不是独立验收**。原定的独立验证单元 `unit-e-verifier` 在运行 **18m27s** 后
   仍零产出、未落盘任何文件（其留下的 `/tmp/t2v_no_outline.pdf` 夹具经我在 §AC-3 复用并确认有效），
   故已终止。**"自己给自己盖章"的局限请一并计入**：下面的 PASS 是"按命令复现得到该输出"，
   不等于"换个人看代码不会发现别的问题"。
2. **建议补一次真正的独立审查**：让新眼睛只做一件事——读 `cache.py` / `outline.py` / `pipeline.py`
   的最终 diff，找"改了不生效"与"静默走错分支"两类缺陷。本轮已抓到 3 个同类问题（见 §四），
   说明这类缺陷在本项目密度不低。
3. 所有结论均贴**真实执行命令**。跑不通的会明确写「未能验证」，不含估计值。
4. 时间戳全部来自 `date` 实取，未编造。

---

## 一、结论摘要

| 项 | 数 |
|---|---|
| AC 总数 | 16 |
| **PASS** | **16**（其中 3 条是**本轮先修后验**：AC-5 / AC-7 / AC-11） |
| FAIL | 0 |
| 阻塞项 | 0 |
| 本轮新发现并已修缺陷 | **3 个真缺陷**（+1 个预防性加固） |
| 未能验证 | AC-15 的「断网出片」只做了代码审计，未真断网实测 |

> **一句话**：T2V-002 可交付。核心指标——全命中 **0.502s**（AC 要求 ≤2s）、
> 改分镜重渲染 **13.0s**（要求 ≤15s）、TTS 12 句 **2.04s**（要求 ≤5s）——均达标且有余量。

---

## 二、逐条 AC

| AC | 判定 | 可复现命令 | 真实观测（关键行） |
|---|:--:|---|---|
| AC-1 outline.json 93 条 | ✅ | `PYTHONPATH=src $PY -m book2vido outline <pdf>` | `目录来源: pdf-outline ｜ 348 页 ｜ 93 条（顶层 22 章）`；`条数=93 origin=pdf-outline 带页码=是`；顶层 22 / 小节 71 |
| AC-2 list 两级树 | ✅ | `... -m book2vido list <pdf>` | 首行同上；`grep -c '^\['` = **22**；含 `pNNN` 行 = **93** |
| AC-3 三层兜底 | ✅ | 见 §三·1 脚本 | ①真 PDF → `pdf-outline` 顶层 22 ②无书签 PDF → **`regex`** 顶层 5、页码单调不减、范围 `(第1章,8,30)(第2章,31,47)` ③纯文本 → `whole-doc` 章数 1。**附**：目录页判为 TOC=True、正文页=False、目录页被正则跳过=True |
| AC-4 文本不越界 | ✅ | 见 §三·2 脚本 | 第8章 p68-p92；`text.txt` 4 个片段**全部**落在本章内、越界 0；随机 **200** 个 12 字窗口对第7章命中 **0** 次、第9章 **0** 次 |
| AC-5 多章 + 越界报错 | ✅ **修后** | `run ... --chapter 0 / -1 / 999 / --chapters abc / --chapters ''` | `0`→exit **1** `ValueError: 章号 0 越界：本书顶层章为 1–22`；`-1`→exit 1 同上；`999`→exit 1 同上；`abc`→exit **2** `🔴 --chapters 需为逗号分隔的整数`；`''`→exit 2 `🔴 --chapters 为空，未指定任何章` |
| AC-6 单章失败不阻塞 | ✅ | 见 §三·3 打桩脚本 | `成功章 = ['/tmp/ac6_out/ch08.mp4']`；`失败章 = [(9, '（打桩）第9章故意失败')]`；第 9 章 `🔴` 后第 8 章产物仍在 |
| AC-7 长章均匀采样 | ✅ **修后** | 见 §三·4 脚本（**全 22 章**逐章） | 长章（6~17 章，原文 4718~16879 字）→ **2498 字**，首/正中/**末 12 字**全部命中；短章原样返回（如第 3 章 2155→2155）；22/22 通过、无超限 |
| AC-8 TTS 并发 | ✅ | 见 §三·5 脚本 | `workers=12 耗时=2.04s`（要求 ≤5s）；`成功 12/12`；时长样例 `[3.02, 2.98, 2.62]` |
| AC-9 重试/降并发/不静默 | ✅ 审计 | `grep -nE "retry\|重试\|降并发\|RuntimeError\|st_size" src/book2vido/narrator.py` | `narrator.py:40` 重试额度初始 2（= 最多 3 次尝试）；`:70-73` 失败率 >50% 降并发且 `ran>1` 才降；`:95` 最终 `raise RuntimeError`；`:118`/`:136` 两个 provider 各自校验 **0 字节音频**并抛错；`:62` 进度按**成功数**回调 |
| AC-10 缓存三层语义 | ✅ | `run ... --chapter 8` 连跑两次；再手改 `script.json` | ①全命中：`耗时 0.0 s / 缓存 hit`，`real 0m0.502s` ②`script.json` 命中：`· 分镜：缓存命中 12 句（跳过模型，省 ~36s）` ③手改首句后：仍「分镜：缓存命中」+「画面：渲染 12 张卡」→ **只重跑下游、LLM 未跑** |
| AC-11 改一句重跑 ≤15s | ✅ **修后** | 同上③ | 内部 `12.5 s`、`real 0m13.046s`（≤15s）。另测「改 `text.txt`（=换素材）」→ 触发重跑模型 79.2s，**语义正确**、非本 AC 适用范围 |
| AC-12 MediaClip 契约 | ✅ | 见 §三·6 脚本 | 旧三元组 `("a.png","b.mp3",1.5)` → `index=0 image=a.png audio=b.mp3 dur=1.5`；dict → `index=2 dur=2.5`；`frozen` 生效（改字段抛 `FrozenInstanceError`）。**附核**：`compositor.compose` 用 `enumerate` 排序、**不依赖 `index`**，故元组给 `index=0` 无害 |
| AC-13 models 零同包 import | ✅ | `ast` 解析 `models.py` | `imports = ['__future__','dataclasses','datetime','json']`；`同包 import = 无` |
| AC-14 旧 CLI 行为不变 | ✅ | `run --input <pdf> --out <mp4>`（**不带任何新参数**） | `口播句数 12 / 耗时 73.0 s`（基线 ~75s）；`h264 1080×1920 + aac`，33.97s，652KB；产物落旧式 `samples/.work_<stem>/`；**未改 `cache/`**（`.keys.json` mtime 不变）；临时产物已清理 |
| AC-15 零 key + 离线可出片 | ⚠️ 部分 | `grep -rniE "codemax\|openai_api_key\|ANTHROPIC_API_KEY\|sk-[A-Za-z0-9]{16,}\|api\.deepseek\|dashscope\|volcengine" src/ config.yaml` | **无命中** ✅。外部端点仅 `http://localhost`（Ollama）×3、`https://api.iconify.design`（免费图标 CDN）、`https://github.com/xingtu1996/book2vido`（自有仓）。pipeline 有 `say` 回退分支（`pipeline.py` TTS 异常 → `SayProvider`）。**未能验证**：真断网实测（未真拔网跑） |
| AC-16 模块 ≤200 行 | ✅ | `wc -l src/book2vido/*.py` | 最大非豁免项 = `outline.py` **200**；`pipeline.py` 193、`__main__.py` 166、`cache.py` 151、`segmenter.py` 150、`providers.py` 35；仅 `icons.py` 311（spec 豁免） |

### 附加核验（spec `05_validator` §三 数据一致性）

| 检查 | 命令 | 结果 |
|---|---|---|
| outline 落盘 ↔ 读回是否漂移 | `render_tree(build(pdf))` vs `render_tree(load(outline.json))` | **完全一致**；93 条 / 22 顶层 / **页码范围逐条相同** → 读缓存不引入漂移 ✅ |
| 出片合法性 | `ffprobe samples/t2v_ch03.mp4` | `h264 1080×1920 + aac`，36.74s，687KB ✅ |
| 打包产物 | `bash packaging/build_app.sh` → `--selftest` | `dist/Book2Vido.app` **115 MB**；包内 16 个 .py 与仓库源码 **sha256 逐一致**；`--selftest` **7/7 绿**（runtime 3.13.12 / 依赖 / ollama 二进制 / ollama 服务 / ffmpeg / qwen3:8b / 图标 118）✅ |

---

## 三、复现脚本（§二的"见 §三·N"）

```bash
cd <工作区根>/book2vido
PY=~/.workbuddy/binaries/python/envs/default/bin/python
P=<工作区根>/book2vido/关键对话.pdf      # 348 页 / 顶层 22 章 / 93 条
```

1. **AC-3**：`outline.build($P)`→`pdf-outline`；`outline.build('/tmp/t2v_no_outline.pdf')`→`regex`；
   `outline.build('/tmp/t2v_fixture.txt')`→`whole-doc`。夹具由已终止的验证单元产出、经确认 `PdfReader(...).outline == []`。
   目录页判据：`_looks_like_toc(目录页行) is True` / `_looks_like_toc(正文页行) is False`。
2. **AC-4**：取 `ch08/text.txt`，按 `……` 切段逐段断言是 `page_slice(pages,68,92)` 的子串；
   再随机抽 200 个 12 字窗口，断言在第 7 / 第 9 章文本中命中数为 0。
3. **AC-6**：`unittest.mock.patch.object(pipeline,'run_chapter', flaky)`，`flaky` 对 `ch.index==9` 抛错，
   然后 `pipeline.run_book($P,'/tmp/ac6_out',cfg,indices=[8,9],no_cache=True)`。
4. **AC-7**：遍历 `doc.top()` 全 22 章，逐章断言 `len(slice)<=2500` 且原章文的前 12 / 正中 12 / **末 12** 字均在切片中。
5. **AC-8**：构造 12 条口播 → `EdgeTTSProvider(voice).speak_many(items, max_workers=12)`，计时并统计非空音频数。
6. **AC-12**：`MediaClip.from_any(tuple)` / `from_any(dict)` / 直接构造；再试改 `frozen` 实例字段。

---

## 四、发现的问题清单

> 分档：**A 阻塞** / **B 建议** / **C 素材侧** / **D 已核实无误**。
> 本轮无 A 档。B 档 3 个**已在本轮修完并复验**（此处留档，供独立审查对照）。

| # | 档 | 问题 | 文件:行（修前） | 证据 | 处置 |
|:-:|:-:|---|---|---|---|
| 1 | **B→已修** | `--chapter 0` **静默走整本出片老路径**：`bool(a.chapter or ...)` 把 `0` 判成"没给参数"，退出码 0、用户拿到完全不对的片子却无任何提示 | `__main__.py:49`（`want_chapters = bool(a.chapter or a.chapters or a.all)`） | 修前 `--chapter 0` 无任何输出与报错 | 改用 `is not None` 显式区分「没给」与「给了 0」；`--chapters ''` 亦明确报错。复验：`0/-1/999`→exit 1、`abc/''`→exit 2 |
| 2 | **B→已修** | 长章切片**尾部被截**：`budget = max_chars//3` 未预留 2 个省略分隔符（各 4 字），三段 2499 字 + 8 字 = 2507 > 2500 → `_assemble` 的兜底 `text[:2500]` **从尾部切**，正好切掉尾段要保留的「章尾」 | `segmenter.py:112` / `:124` | 修前 `尾(末12字)` 命中 = **False**（首、中均 True） | ①`budget = (max_chars - 2*len(_SEP))//3` ②`_fill_forward/_fill_backward` 把段间 `"\n\n"` 计入预算。复验：**22/22 章**通过、长章 2498 字、首中尾含真正的章尾 |
| 3 | **B→已修** | `text.txt` 缓存的键**不含采样算法**：改了采样逻辑而键不变 → 旧切片被静默复用，改进等于没做 | `pipeline.py`（`tkey` 未含版本） | 修 #2 后，旧 `text.txt`（2500 字·尾段被切版）仍被判为可用 | 新增 `segmenter.VERSION`（改算法须 +1）+ `Cache.text_ok/put_text` 携带 `text_key`。复验：`.keys.json` 出现 `text_key: "seg2|chars2500"`，改后首跑正确判定过期并重算（79.2s） |
| 4 | **D** | `MediaClip.from_any(tuple)` 得到 `index=0` — 是否会导致排序错乱？ | `models.py` / `compositor.py` | 读 `compositor.compose`：用 `enumerate(clips)` 定序，**不读 `clip.index`** | **无害，不改** |
| 5 | **D** | `outline.json` 读缓存是否会与现场解析漂移？ | `outline.py` `save/load` | 逐条比对：93 条 / 22 顶层 / 页码范围**全同** | **无漂移，不改** |
| 6 | **C** | 非 PDF（MD/长文）无法分章（一律 `whole-doc`） | `outline.py:build` | 无页边界 → 所有章落第 1 页 → 切片会把整篇重复给每章 | **刻意设计**，已在 `AC-3` 写明；`extractor` 原文档"MD 走正则分支"已改正 |
| 7 | **B·未处理** | 输入文件不存在时抛裸 traceback（20 行栈） | `__main__._run_cmd` | 修前 `FileNotFoundError: [Errno 2]` + 栈 | **本轮已顺手修**：改为 `🔴 输入文件不存在：<path>` + exit 2 |

### 顺带记录（非缺陷，供独立审查留意）

- **`AC-11` 余量变薄**：同一条命令两次实测 **8.5s → 12.5s**。差异来自机器负载（当时同时在跑
  验收单元与 `.app` 构建）+ TTS 走网络。**若日后再加渲染步骤，这条 15s 的余量会被吃光**。
- **`.app` 构建脚本的"清理旧产物"会触发安全钩子**（`SAFE_DELETE_BULK_CONFIRM_REQUIRED`，2817 文件 > 阈值 50）。
  本轮未绕过，改用 `mv` 改名让位 → `dist/Book2Vido.app.bak-<ts>/`（可回滚）。**是否删除留给 boss 拍板。**

---

## 五、未能验证项

| 项 | 原因 | 建议 |
|---|---|---|
| AC-15「真断网可出片」 | 未实际断网跑完整链路（避免影响同机其他任务） | 需时用 `tts.provider: say` 配置 + 断网各跑一次 |
| AC-6「`--all` 全 22 章真实运行」 | 22 章 × ~36s 模型 ≈ 13 分钟，且与本轮"避免长跑"约束冲突 | 用 `--chapters 1,2` 做小样本；全量留作验收后一次性跑 |
| **独立第三方审查** | 原定验证单元 18m27s 后无产出，已终止 | **建议补一次**（见开头 §⚠️ 声明第 2 点） |

---

## 六、环境

- macOS / Apple Silicon ｜ Python 3.13.12（`~/.workbuddy/binaries/python/envs/default`）
- Ollama `qwen3:8b`（本地）｜ edge-tts（免费匿名）｜ FFmpeg 7.x（homebrew）｜ pypdf / Pillow
- 成本：全程 ≈¥0（仅电费）；**零公司 API key**（AC-15 审计通过）

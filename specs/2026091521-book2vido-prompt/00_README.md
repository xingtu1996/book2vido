# T2V-007 · 提示词资产化与模型适配基座

> Ticket: T2V-007 | 创建: 2026-09-15 21:21 | 状态: ✅ 完成（AC 16/16 通过 · 验收见 [05_validator.md](./05_validator.md)）
> 关联: 项目宪法 `../../CONSTITUTION.md`（铁律六）｜前置 spec `../2026091518-book2vido-chapter/`
> 承前: `../doc/13-确定性与模型分工.html` §审计发现（提示词内联 = 可维护性与正确性双缺口）

**一句话目标**：把分镜提示词从 `scriptwriter.py` 的字符串拼接里搬出来，变成**带逐条注释、可独立修改、有版本追溯的资产**；并补上「改了提示词却静默复用旧分镜」这个缺陷。

## Spec 索引

| 文件 | 状态 | 说明 |
|------|:--:|------|
| [00_README.md](./00_README.md) | ✅ | 本文件 |
| [laws.md](./laws.md) | ✅ | 铁律 + 项目宪法 + 门禁 |
| [01_analysis.md](./01_analysis.md) | ✅ | 问题分析 + 五个方案对比 + 影响面 |
| [02_requirements.md](./02_requirements.md) | ✅ | 16 条可测 AC + 安全三条件 |
| [03_design.md](./03_design.md) | ✅ | 接口 + 契约冻结 + 数据流 + 关键决策 |
| [04_tasks.md](./04_tasks.md) | ✅ | 任务 + 覆盖矩阵 |
| [05_validator.md](./05_validator.md) | ✅ | 可执行验证脚本集（7 组 TC） |
| [execution-log.md](./execution-log.md) | 🔄 | 执行事件日志（append-only 事实源） |

> 方法论 SSOT：全局 `specs-engine` skill（本文件为落盘快照，冲突以全局为准）。

## 范围

**IN**

1. `prompts/scriptwriter.md` —— 提示词资产本体：正文 + **就近注释** + frontmatter + 人读区（模型适配记录 / 改动影响面 / 验证 SOP）。
2. `src/book2vido/promptlib.py` —— 加载器：frontmatter / 正文标记 / 剥注释 / 渲染 / 指纹。
3. **缓存键补提示词因子**（`cache.script_key`）+ `ScriptDoc` 溯源字段（`prompt_version` / `prompt_hash`）。
4. `config.yaml` 的 `llm.prompt_file`（不改代码就能试另一版提示词）。
5. `packaging/build_app.sh` 随包分发 `prompts/`，且**漏拷即构建失败**。
6. `tools/verify_prompt.py` + `tools/prompt_golden.txt` —— 改提示词时可逐字节对账。

**OUT（连同理由）**

| 不做 | 理由 |
|---|---|
| 提示词 A/B 自动评测 | 一次只该改一个变量；且"什么算好分镜"的判据本身还没定义 —— 那是独立 spec |
| 多套提示词模板 / 多语言 | 现在只有一种产物形态（中文口播信息卡）。多模板是提前支付复杂度（宪法铁律四） |
| 把 `CONCEPTS` 清单也搬进 `prompts/` | 清单是「词 → 图标名」映射，SSoT 属 `icons.py`；搬走会让 icons 反向依赖 prompts |
| 提示词进 pip `package-data` | 主分发是 `.app`（整目录拷贝）。pip 安装路径未实测 → 记为已知限制，不假装支持 |
| 提示词热加载（改完不重启） | 本项目是批处理 CLI：进程起→出片→退出，无常驻服务可热替换（同 T2V-002 的否决） |

## Spec 深度

深度 = **standard**（跨模块 + 缓存键行为变更）。
改动面：**代码与配置层 13 个文件**（清单见 [04_tasks.md](./04_tasks.md) §二；口径
`git diff --name-only -- src prompts config.yaml packaging tools | wc -l`）+ spec 7 件 + doc 1 篇。
必填 01~05 + execution-log，已全填。

## 质量门禁

> 置 ✅ 前逐项过 —— 见 [laws.md](./laws.md)。核心：三铁律 / 安全三条件 / 级联影响 / 测试 / execution-log / ✅ 三前置。

## 交接与续传

- **① 被否决的方案及原因**（5 个，详见 `01_analysis` §三）：
  留在代码里只加注释（改了仍不进缓存键）；放包内 `src/book2vido/prompts/`（`.app` 的 `parents[2]` 回溯不到，且 pip 需额外配置）；
  写进 `config.yaml`（YAML 长文本转义地狱）；引入 Jinja2（为 3 个变量上一个模板引擎，违铁律三最小依赖精神）；
  用 `version` 号当缓存失效开关（**靠人记得升，迟早会忘**）。
- **② 现场证据原文**（环境一变即不可复现）：
  - 重构前基线：劫持 `urllib.request.urlopen` 抓到的**真实 payload** = **699 字符 / 15 行**
    （不是照抄代码重写一遍 —— 那样证明不了逐字节一致）。
  - 版本指纹：`body_hash=def6f167f61a`、`cache_fp=41737545877c`、`CONCEPTS` 85 词。
  - 四跑对照（本地 qwen3:8b，`--fast`）：① 首跑 **39.0s / miss** → ② 同提示词 **0.0s / hit**
    → ③ **改正文一个字** **38.4s / miss** → ④ 改回原样 **31.2s / miss**（键文件只记最后一次，见 §四）。
  - 外部提示词（config 指到 `/tmp` 的副本、改一个字）：产物 `prompt_hash=7eebba9fa500` ≠ 仓库版 `def6f167f61a`。
  - 缺资产构建自检：退出码 **1** + `✗ 缺少 prompts/scriptwriter.md（分镜提示词资产）`。
- **③ 用户纠偏原话**（逐字）：
  - 「然后翻一下模型驱动分镜提示词，啥的背景注释提示注释（便于后续根据注释优化提示词），可以独立出来，未来模型升成或者适配了，或者我们跟清 sota 模型优化提示词，根据既有的情况啥的，做好分镜啥的。」（2026-09-15 21:18）
  - 上一轮：「缓存就是手段，就是让 LLM 回归到最终的思考上面，技术层面能脚本高效执行，就技术化的执行。」
- **④ 未写入 AC 的隐含约束**：
  - `pipeline.run()`（T2V-001 兼容入口，`.app` 拖拽路径）**行为不得变**；
  - 所有新能力必须离线可跑（TTS 退 `say`）；
  - **提示词改动不得要求改代码** —— 这是 boss 诉求的字面意思，也是本 spec 的存在理由。

- 下一步（下一个动作，一句话）：按 `04_tasks` 收尾 —— 文档挂链（doc/15 + 错题库 + CHANGELOG）→ 提交推送。

## Execution Log（摘要 · 详细见 execution-log.md）

- 21:21 scaffold；核 4 个候选位置、结论是"内联在 `scriptwriter.py:67-82`，且 `CONCEPTS` 清单是注入项"。
- 21:21 **劫持 `urlopen` 抓基线** 699 字符 / 15 行（先固化行为，再动代码）。
- 21:23 `promptlib.py` + `prompts/scriptwriter.md` 落盘；**第一跑就抓到缺陷**：文件头说明里提到了正文标记，子串匹配把它当成了真标记 → 正文只取到 5 个字符。改为**整行精确匹配**（详见 `01_analysis` §七）。
- 21:24 **逐字节一致 699 字符 / 15 行** —— 重构干净的硬证据。
- 21:26 接入 9 个文件（缓存键 / 溯源字段 / config / 打包）。
- 21:30 端到端四跑：miss → hit → **改一字 miss** → 改回 miss。
- 21:33 `.app` 布局模拟：`parents[2]` 回溯正确；缺文件时明确报错含修复指引。
- 21:37 构建自检缺 prompts 时退出码 1；脱敏扫描：新增行零命中。
- **澄清状态**：豁免追问——诉求原话已指明"独立出来 + 带注释 + 便于迭代"，方案选择与代价写进 `01_analysis` §三待 boss 复核。

## 复盘（置 ✅ 前必填）

- **总耗时**：约 **20 分钟**（21:21 → 21:41）；其中**取证与基线 2 分钟、实现 6 分钟、验证 8 分钟、文档 4 分钟**。
- **踩坑（3 个，全部在"验证"环节暴露）**：
  1. **正文标记被注释里的字面量"截胡"**：文件头说明写了「`<!-- @prompt:begin -->` 与 …」，
     子串匹配 `split(BEGIN)` 命中的是**注释里那一处** → 正文只剩 5 个字符。
     改成整行精确匹配后，正文里随便提到标记都不再歧义。
     **这就是"匹配到不该匹配的东西"——不报错、只静默取错内容**，与错题库既有家族同源。
     值得注意的是：**它是被"逐字节 golden 校验"当场抓住的**，不是靠人眼。
  2. **改回原样仍 miss**：`.keys.json` 只记**最后一次**键 → 改错一个字再改回来，仍会重跑一次模型。
     不是 bug（缓存只认"上次是什么"），但必须写进文档，否则用户会以为缓存坏了。
  3. **自己写的验证脚本漏了一步**：AC-11（缺 prompts 则构建自检 die）第一次跑时我忘了真的移走目录，
     于是 `--check` 正常通过、显示退出码 0 —— **探针本身没生效，却差点被当成"通过"**。
     补跑后退出码 1。/ 教训与 `hidden-contract-audit` 的"先证明探针是对的"同条。
- **模式识别**：本 spec 的 3 个坑里 2 个是**探针/校验环节**的问题，1 个是**缓存键语义**问题 ——
  与 T2V-002 复盘里"缺陷高发区在看不见的契约"完全一致（该家族累计已 8 次）。
  另一条更值得记：**"逐字节 golden"这类校验，第一次跑就把实现缺陷抓出来了** ——
  证明"先固化基线、再动代码"的顺序是对的，代价只有 2 分钟。
- **反哺落点**：
  - `doc/lessons/README.md`（L-15 注释声称≠实际 / L-16 标记匹配要整行）
  - `CHANGELOG.md`（T2V-007 段）
  - `AGENTS.md`（新模块清单 + 提示词在哪）
  - `doc/15-提示词与模型适配.md`（**新增**：调优手册）
  - `HANDOFF.md`（文件地图 + 已知限制）
  - 会话记忆 `2026-09-15.md`

## AC 对账（16 / 16 通过 · 证据指针）

| AC | 结论 | 证据 |
|:--:|:--:|---|
| AC-01 | ✅ | `verify_prompt.py`：**699 字符 / 15 行**，与重构前劫持 `urlopen` 抓到的真实 payload 逐字节一致 |
| AC-02 | ✅ | TC-04 四跑：**改正文一个字 → `38.4s / miss`**（改前是 `0.0s / hit`） |
| AC-03 | ✅ | 注入注释 → `body` 逐字节相同、指纹不变 |
| AC-04 | ✅ | `verify_prompt.py` 断言渲染结果不含 `<!--` |
| AC-05 | ✅ | `render()` 少传 `concept_list` → `PromptError`（列出缺失名） |
| AC-06 | ✅ | 删掉 `@prompt:end` → `PromptError`（含 begin/end 存在性） |
| AC-07 | ✅ | `load(path=不存在)` → 报错含三行修复指引（`git checkout` 可查） |
| AC-08 | ✅ | 新产物 `prompt_version='1' prompt_hash='def6f167f61a'`；老 `script.json` 读出空值不抛 |
| AC-09 | ✅ | config 指向 `/tmp` 副本 → 产物 `prompt_hash=7eebba9fa500` ≠ 仓库版 |
| AC-10 | ✅ | 模拟 `.app` 布局加载成功：`<APP>/Contents/Resources/prompts/scriptwriter.md` |
| AC-11 | ✅ | 移走 `prompts/` → `build_app.sh --check` 退出码 **1** + `✗ 缺少 prompts/scriptwriter.md` |
| AC-12 | ✅ | `tools/verify_prompt.py` 与 `--update` / `--show` 均可用 |
| AC-13 | ✅ | 人工核对：正文 + 逐条就近注释 + 三段人读区（适配记录 / 影响面 / 验证）齐备 |
| AC-14 | ✅ | `wc -l src/book2vido/promptlib.py` = **172** ≤ 200 |
| AC-15 | ✅ | 依赖仅 `hashlib` / `re` / `dataclasses` / `pathlib`（零第三方） |
| AC-16 | ✅ | 30 个文件扫描，**新增行零命中**（既有命中属"公开前必清"清单，本批不新增） |

**未达项**：无。**已知限制**（不计入未达项，如实登记）：见 [02_requirements.md](./02_requirements.md) §四
（pip 安装路径未验证 / 改回原样仍重跑一次 / 示例版权待清 / `think` 不在提示词内）。

## 变更日志

| 日期 | 变更 | 作者 |
|------|------|------|
| 2026-09-15 21:21 | 新建（scaffold，深度 standard） | 小研 |
| 2026-09-15 21:24 | 提示词资产 + 加载器落盘，逐字节校验通过 | 小研 |
| 2026-09-15 21:41 | 实施与验证完成，文档待挂链 | 小研 |

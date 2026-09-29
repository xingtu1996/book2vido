# 02 · 需求（AC 与验收口径）

> 深度 standard。16 条 AC，**全部可执行**（命令 / 单元 / 端到端），验证方式见 [05_validator.md](./05_validator.md)。
> 标 ✅ 者为实施期已实测通过（证据记在 `00_README` §②与 `execution-log.md`）。

## 一、AC 表

| # | AC（可测断言） | 验证方式 | 状态 |
|:--:|---|---|:--:|
| AC-01 | 提示词以独立文件存在；**渲染结果与重构前逐字节一致** | `python tools/verify_prompt.py` → 699 字符 / 15 行 | ✅ |
| AC-02 | 改提示词**正文**任一字符 → 该章缓存键变 → 下次运行必重跑模型（`miss`） | TC-04：改字 → 跑 → 看 `cache: miss` | ✅ |
| AC-03 | 改**注释/人读区** → 指纹**不变**（注释不占 token、不改变行为） | TC-03：注入注释 → `body` 逐字节相同 | ✅ |
| AC-04 | 剥注释干净：渲染结果不含 `<!--` / `-->` | `verify_prompt.py` 的断言 | ✅ |
| AC-05 | 占位符全部替换；有残留 → 抛 `PromptError`（不把脏文本送模型） | TC-02：`render()` 少传一个变量 → 必须抛 | ✅ |
| AC-06 | 缺 `@prompt:begin/end` 标记 → 明确报错（不静默取空/取全文） | TC-02 | ✅ |
| AC-07 | 提示词文件不存在 → 明确报错 + **含修复指引** | TC-05：删文件 → 报错含 `git checkout` | ✅ |
| AC-08 | `ScriptDoc` 记 `prompt_version` + `prompt_hash`；**老 `script.json` 仍可读** | TC-06 | ✅ |
| AC-09 | `config.yaml` 的 `llm.prompt_file` 可指向外部提示词（**不改代码**） | TC-07：指向 `/tmp` 副本 → 产物 `prompt_hash` 变 | ✅ |
| AC-10 | 打包随包分发 `prompts/`，且与 `config.yaml` **同级**（`parents[2]` 可回溯） | `.app` 布局模拟：加载成功 | ✅ |
| AC-11 | 缺 `prompts/` 时构建自检**必须失败**（不发出坏包） | 移走目录 → `--check` 退出码 1 | ✅ |
| AC-12 | `tools/verify_prompt.py` 一条命令复算；`--update` 可更新基准 | 直接跑 | ✅ |
| AC-13 | 资产含：逐条**就近注释** + 「模型适配记录」+ 「改动影响面」 | 人工核对 `prompts/scriptwriter.md` 结构 | ✅ |
| AC-14 | 新模块行数 ≤200（项目 AC-16 约束） | `wc -l promptlib.py` = 172 | ✅ |
| AC-15 | **零新依赖**：`promptlib` 只用标准库 | `grep "^import\|^from" promptlib.py` | ✅ |
| AC-16 | 新增/改动内容**零脱敏命中**（真名/绝对路径/公司名/在职自述） | 逐文件正则扫描 | ✅ |

## 二、安全三条件

| 条件 | 本项目口径 |
|---|---|
| **退出** | 三类失败都"响亮"：①提示词文件缺失 → `PromptError`（含修复指引）②标记/占位符有问题 → `PromptError` ③打包缺资产 → 构建 `die` 退出码 1。**任何情况下都不静默退回内置文本**——那会让用户以为"我改的生效了" |
| **幂等** | 同一（书 + 章 + 模型 + think + 句数 + 提示词）→ 同键 → 第二次必 `hit`。提示词指纹进键后，幂等边界从"代码没变"扩展到"**资产也没变**" |
| **回滚** | ①单提交 `git revert` 即可；②删掉 `prompts/` 不会静默出错，而是明确报错（可恢复：`git checkout -- prompts/`）；③`config.yaml` 的 `prompt_file: null` 是默认值，不影响既有用户；④**唯一不可逆项**：历史缓存会失效一次（重跑一次模型，成本≈¥0.0004 + 约 40s），已如实记录 |

## 三、不做什么（防镀金）

| 不做 | 理由 |
|---|---|
| A/B 自动评测、自动择优 | 一次只改一个变量；且"好分镜"的判据本身未定义 → 独立 spec |
| 多模板 / 多语言 | 只有一种产物形态；提前支付复杂度（铁律四） |
| 把 `CONCEPTS` 搬进 `prompts/` | 会造出 `icons → prompts` 的反向依赖；SSoT 保持在图标层 |
| 提示词进 pip `package-data` | 主分发是 `.app`；pip 路径未实测 → **记为已知限制，不假装支持** |
| 热加载（改完不重启） | 批处理 CLI，无常驻进程（同 T2V-002 否决） |

## 四、已知限制（如实登记，不掩盖）

1. **pip 安装路径未验证**：`pyproject.toml` 未配 `package-data`，`pip install` 后 `prompts/` 不会随包。
   主分发形态（`.app`）已覆盖；若将来真走 PyPI，需补 `pyproject` 与一次实测。
2. **改回原样仍会重跑一次**：`.keys.json` 只记最后一次键（详见 `01_analysis` §七 F-B）。
3. **提示词示例仍引用原书内容**：`few-shot` 那条取自《关键对话》——与 demo 样片同一个
   **公开前必清** 待办（见 `CHANGELOG` 与仓库根脱敏清单）。
4. **`think` 不在提示词里**：它由 `config.yaml` 控制（模型行为开关）。调提示词时若同时改它，
   会一次变两个变量 → 已写进 `prompts/scriptwriter.md` 的"怎么改"一节提醒。

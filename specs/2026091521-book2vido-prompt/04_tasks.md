# 04 · 任务与覆盖矩阵

## 一、执行顺序（**串行**，理由见 `laws.md` §三）

```
T0 取证     劫持 urlopen 抓基线 prompt（699 字符 / 15 行）
             └─ 先固化行为，再动代码：没有基线，"重构没改行为"就无从证明
T1 资产     prompts/scriptwriter.md（正文 + 逐条就近注释 + 人读区）
T2 加载器   src/book2vido/promptlib.py
T3 校验     tools/verify_prompt.py + tools/prompt_golden.txt
             └─ ★ 门禁：T1+T2 必须让 T3 通过，才允许往下接代码
T4 接代码   cache.script_key / models.ScriptDoc / scriptwriter / providers / pipeline
T5 配置     config.py DEFAULT + config.yaml（llm.prompt_file）
T6 打包     packaging/build_app.sh（随包 + 缺则 die）
T7 端到端   四跑对照（miss → hit → 改字 miss → 改回 miss）
T8 文档     doc/15 + 错题库 + CHANGELOG + 挂链（README/AGENTS/HANDOFF/doc/README）
T9 收口     脱敏扫描 → 提交 → 推送 → 远端复验
```

**T3 是硬门禁**：它是本 spec 的"逐字节契约"。跳过它直接接代码，
"重构未改行为"就只是一个说法 —— 而实际上 T3 第一次跑就抓出了 F-A 缺陷。

## 二、任务清单

| # | 任务 | 产物 | 状态 |
|:--:|---|---|:--:|
| T0 | 抓基线 | `/tmp/prompt_baseline.txt`（**不入仓**，其内容转化为 golden） | ✅ |
| T1 | 提示词资产 | `prompts/scriptwriter.md`（9.8 KB） | ✅ |
| T2 | 加载器 | `src/book2vido/promptlib.py`（172 行） | ✅ |
| T3 | 校验机制 | `tools/verify_prompt.py` + `tools/prompt_golden.txt`（699 字符） | ✅ |
| T4a | 缓存键补因子 | `cache.py::script_key(+prompt_fp)` | ✅ |
| T4b | 产物溯源 | `models.py::ScriptDoc(+prompt_version/prompt_hash)` | ✅ |
| T4c | provider 化 | `scriptwriter.py`（删除内联串）+ `providers.py` | ✅ |
| T4d | 编排 | `pipeline.py`（传指纹 + 记版本） | ✅ |
| T5 | 配置 | `config.py` / `config.yaml` | ✅ |
| T6 | 打包 | `packaging/build_app.sh`（`cp -R prompts` + 自检 `die`） | ✅ |
| T7 | 端到端 | 四跑对照输出 | ✅ |
| T7b | `.app` 布局 | 模拟 `Contents/Resources/` 加载 + 缺文件报错 | ✅ |
| T7c | 行数/依赖 | `wc -l` = 172；仅标准库 | ✅ |
| T8 | 文档 | `doc/15` + 错题库 L-15/L-16 + CHANGELOG + 4 处挂链 | ✅ |
| T9 | 收口 | 脱敏 → commit → push → `gh api` 复验 | 🔄 |

## 三、AC ⇄ 任务覆盖矩阵

| AC | 由哪个任务产出 | 验证方式 | 结果 |
|:--:|:--:|---|:--:|
| AC-01 | T1+T2+T3 | `verify_prompt.py` 逐字节 = 699 字符/15 行 | ✅ |
| AC-02 | T4a | TC-04 改字 → `miss`（38.4s） | ✅ |
| AC-03 | T2 | TC-03 注入注释 → `body` 相同、指纹不变 | ✅ |
| AC-04 | T2 | `verify_prompt.py` 断言无 `<!--` | ✅ |
| AC-05 | T2 | TC-02 `render()` 少传变量 → `PromptError` | ✅ |
| AC-06 | T2 | TC-02 删标记 → `PromptError` | ✅ |
| AC-07 | T2 | TC-05 删文件 → 报错含 `git checkout` | ✅ |
| AC-08 | T4b | TC-06 新字段 + 老 JSON 兼容 | ✅ |
| AC-09 | T5+T4c | TC-07 `/tmp` 副本 → `prompt_hash=7eebba9fa500` | ✅ |
| AC-10 | T6+T2 | TC-08 `.app` 布局加载成功 | ✅ |
| AC-11 | T6 | TC-08 移走目录 → `--check` 退出码 1 | ✅ |
| AC-12 | T3 | `verify_prompt.py` / `--update` | ✅ |
| AC-13 | T1 | 人工核对三段结构 | ✅ |
| AC-14 | T2 | `wc -l` = 172 ≤ 200 | ✅ |
| AC-15 | T2 | 仅 `hashlib / re / dataclasses / pathlib` | ✅ |
| AC-16 | T1~T6 | 13 文件正则扫描；**新增行零命中** | ✅ |

**覆盖完整性**：16/16 有对应任务与验证方式，无悬空 AC；无未被 AC 覆盖的任务（T0/T7/T9 属验证与收口）。

## 四、不做（防镀金，与 `02_requirements` §三一致）

A/B 自动评测 · 多模板 · 清单搬迁 · pip package-data · 热加载 —— 各有否决理由，见 `laws.md` 与 `01_analysis` §三。

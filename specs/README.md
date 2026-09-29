# specs/ · 开发规格索引

> specs 驱动开发（SDD）。No Spec No Code。详见全局 skill `specs-engine`。

| Spec | 标题 | 深度 | 状态 |
|------|------|------|------|
| [20260915-book2vido-mvp](./20260915-book2vido-mvp/) | 零成本文本转视频流水线 MVP | standard | 主体完成（T16/T17 遗留） |
| [2026091518-book2vido-chapter](./2026091518-book2vido-chapter/) | 目录索引与按需生成（T2V-002） | standard | ✅ **完成**（AC 16/16） |
| [2026091521-book2vido-prompt](./2026091521-book2vido-prompt/) | 提示词资产化与模型适配基座（T2V-007） | standard | ✅ **完成**（AC 16/16） |

> 编号说明：T2V-003～T2V-006 未单独开 spec 目录（属工程化基线 / demo / 铁律 / 演进档案，
> 落点为 `doc/` 各篇 + `CHANGELOG.md`）。下一个待开编号为 **T2V-008**（`batch` 无缓存 + 中间产物未复用）。

> 🔴 **公开前阻塞项：本目录有 3 个文件含绝对路径（刻意未清）**
> `20260915-book2vido-mvp/05_validator.md` ·
> `2026091518-book2vido-chapter/05_validator.md` ·
> `2026091518-book2vido-chapter/verification-report.md`
> 口径：`git grep -lE '/Users/[^/]+/' specs/`
>
> **为什么不改**：它们是**验证记录**，改写等于篡改证据（违反「不改历史」纪律）。
> 2026-09-16 全库脱敏时**只清理了可执行代码与文档示例**，specs 刻意保留原样。
>
> ⚠️ **关键**：这些路径在 **git 历史里同样存在**（首提交即含）。
> 所以「清工作区」**不等于**「可公开」——真要 `--public` 必须先做**历史重写**
> （`git filter-repo` 或压成单条初始提交）。详见 `CHANGELOG.md` 文首「[更名与脱敏]」条目。

## 工作流
意图 → 深度定档 → 01_analysis → 02_requirements(AC) → 03_design → 04_tasks → 写码 → 05_validator → 复盘/AC 对账 → 提交

## 项目宪法
见 `../CONSTITUTION.md`（零公司资源 / 极致省资源 / 集百家之长 / MVP 优先）。

## 交接与续传

| Spec | 交接锚点 | 下一步 |
|------|---------|-------|
| T2V-002 | `2026091518-book2vido-chapter/execution-log.md`（事实源）+ `00_README.md` §交接与续传 | Phase 0~5 **全部 ✅**（AC 16/16，见 `verification-report.md`）→ **仅剩 Phase 6 提交**：`git init` 可做，**`git push` 待 boss 拍板** |
| T2V-007 | `2026091521-book2vido-prompt/execution-log.md`（事实源）+ `00_README.md` §AC 对账 | 全 9 阶段 ✅、已推远端（`fbe7470`）。**续传入口 = `prompts/scriptwriter.md`**：换模型时先跑 `python tools/verify_prompt.py` 固基线，再只换一个变量 |

## 未开票欠账（诚实登记）

| 编号 | 内容 | 为什么还没做 |
|---|---|---|
| T2V-008 | `batch` 无缓存（F1）+ 中间产物未复用（F2） | 属行为变更，按 SDD 纪律需先开 spec。**动因**：`batch` 走的是 T2V-001 兼容入口，没吃到按章 + 三层缓存 |
| T2V-009? | 换模型后的**对照测量**（同一章 A/B 出片差异如何量化） | 提示词资产化后才浮现的新缺口：现手册只说"抽一章看产出"，缺"怎么判断新的更好" |

## 实施期改动点（给接续者）

本 spec 实施中发现 3 处规格缺陷并已 Reverse Sync（详见 `2026091518-book2vido-chapter/01_analysis.md` §七）：

1. **`video_key` 挂分镜内容指纹**（不是 `script_key`）——否则手改分镜被静默丢弃。
2. **命中路径不得重复解析全书**——`outline.json` 读缓存 + `text.txt` 章切片 + `extractor.lazy_pages()` 延迟抽页。
3. **非 PDF 一律 `whole-doc`**——无页边界，正则分章会让每章切片到整篇。

> ⚠️ 接续前**必读**：`CHANGELOG.md`（有外部影响的变化）+ `HANDOFF.md`（已知坑）。

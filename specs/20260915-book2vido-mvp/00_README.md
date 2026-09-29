# T2V-001 · book2vido MVP — 零成本文本转视频流水线

- **TICKET**: T2V-001
- **深度**: standard
- **状态**: 规划完成，待执行
- **作者**: 小研（行途 AI 研究搭档）
- **日期**: 2026-09-15
- **一句话目标**: 把 PDF/MD/长文，用纯本地 + 免费组件，零公司资源跑出一条「能看完」的短视频。
- **关联**: 调研看板 `outputs/文本转视频开源项目调研_2026-09-14.html`；项目宪法 `../../CONSTITUTION.md`

## 范围（MVP）
- IN: PDF/MD → 抽取 → 本地 LLM 口播稿 → 信息卡画面 → 免费 TTS → FFmpeg 成片；批量；成本≈¥0；断网可跑（TTS 可切本地）。
- OUT（后期）: 文生视频动态画面（HyperFrames）、小程序壳、自动发布、多语言。

## 验收门槛（详见 02_requirements）
端到端跑通 `book2vido/关键对话.pdf` → 输出合法 mp4，单条成本日志≈¥0，全程无公司 key 调用。

## Execution Log（执行账）
- 2026-09-15：specs 规划完成（standard 深度），项目骨架 + `doc/` + `specs/` 落盘。
- 2026-09-15：MVP 代码落地 `src/book2vido/`（extractor/scriptwriter/visualizer/narrator/compositor/pipeline + CLI）。
- 2026-09-15：端到端跑通《关键对话》PDF → `samples/关键对话_sample.mp4`（1080×1920, h264+aac, 12 卡）。
  - 模式：`rule` 降级（Ollama 权重拉取中）→ 证明零依赖闭环。
  - 耗时 52.3s，成本 ≈ ¥0.00026（仅电费），**全程零公司 key 调用**（合规铁律一通过）。
  - 下一步：模型就绪后切 `config.yaml: llm.provider=ollama` 重跑，得「精炼口播稿」版（更短、更对准「能看完」）。
- 状态：MVP ✅ 跑通；Ollama 真实 LLM 步待权重就绪。
- 2026-09-15（下午）：内容工厂泛化① `samples/省Token实战包装.mp4`（12 句，66.3 s，≈¥0.00033）✅；② `人话翻译术` 因 edge-tts 回退链路卡死 ❌（见 `HANDOFF.md` §5.8）。
- 2026-09-15（下午）：工程加固——`compositor` 绝对路径 + 运行隔离目录；`pip install -e .` 使根目录可运行；术语统一 `qwen3:8b`（清 7 处 `7b` 漂移）。
- 2026-09-15（下午）：产出 `HANDOFF.md`（会话交接）+ `AGENTS.md`（接续须知），交棒下一模型。

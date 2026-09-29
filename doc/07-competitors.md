# 07 · 参考开源项目对比与差异化

来源：行途调研看板 + GitHub 实拉（2026-09-14/15）。

| 项目 | ★ | 路线 | 成本 | 能否复用 |
|------|---|------|------|----------|
| lzcjsyr/Book2Video | 6 | PDF→口播→静态图/TTS→FFmpeg | 仍烧图像 API | 思路重合，但 provider 绑定重 |
| chatfire-AI/huobao-drama | 15,101 | 全 Agent 全自动短剧 | 烧 Kling/Seedance | CC BY-NC-SA 禁商用，不可复用 |
| HKUDS/ViMax | 12,368 | Agentic 视频生成 | 烧云端视频模型 | MIT，架构可抄，视频环仍烧钱 |
| anil-matcha/ai-short-drama | 492 | 多 Agent 管线 | 烧 Kling/Veo | 同质化 |
| EvoLinkAI/ai-short-drama | 36 | 小说转视频 | 自托管模型 | MIT，轻 |

## 我们的差异化（卡位空白）
- **低成本半自动**这条「不烧钱」路线，头部全在烧钱，Book2Video 仅 6★——空白且适合行途。
- 我们不烧文生视频 / 文生图，用代码生成画面（AntV/Excalidraw/unDraw）+ 本地 LLM + 免费 TTS。
- 开源 MIT，卡位「免费不烧钱文本转视频」心智。

> **⚠️ 本文与 [`doc/16-项目总览.md`](16-项目总览.md) §3 的分工**：
> 本文是**竞品速查表**（快照 + 星数，供引用时重拉）；
> `16` §3 是**「为什么我们不一样」的论证**（三条结构性差异 + 我们主动放弃了什么）。
> 两张表的竞品数据同源，**改一处必须对另一处**，否则就是双副本漂移。

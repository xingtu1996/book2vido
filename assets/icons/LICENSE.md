# 内置图标许可与来源

本目录下的 PNG 图标由 `assets/icons/` 缓存脚本从 **Iconify** 开源图标库抓取并渲染，
供 book2vido 生成画面卡片使用。

| 图标集 | 许可 | 说明 |
|---|---|---|
| [Tabler Icons](https://tabler.io/icons) | MIT | 本项目默认图标集（线描风格，`tabler:*`） |

- 上游聚合服务：<https://iconify.design/>（API 仅做分发，许可归各图标集）
- 抓取方式：`assets` 由 `python -m book2vido fetch-icons` 生成，`?color=` 指定行途蓝 `#056DE8`
- 渲染方式：`rsvg-convert`（优先）或 `cairosvg`
- 再分发：MIT 允许自由使用与再分发，**保留本文件即为合规**。若替换为其它图标集，
  请同步更新上表并遵守对应许可（Apache-2.0 / CC0 等）。

> 缓存的 PNG 为项目产物，可按需删除后重新 `fetch-icons` 生成。

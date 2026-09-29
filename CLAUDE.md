# CLAUDE.md

> **本文件是入口指针，不是内容副本。**
> 事实源是 [`AGENTS.md`](./AGENTS.md)——在这里重复它的内容等于制造第二个副本，
> 而"多副本 + 只改一处"是本项目反复踩的坑（见 [`doc/lessons/README.md`](doc/lessons/README.md) L-01/02/07）。
> 下面那行 `@` 导入由 Claude Code 自动展开。

@AGENTS.md

## Claude Code 专用补充

以下只写"Claude Code 这一个 harness 特有"的部分，通用纪律一律看 `AGENTS.md`：

- **会话开场**：先读 `AGENTS.md` + `HANDOFF.md`（当前状态快照 / 已知坑 / 下一步），再看 `specs/` 里**最新的那个 spec**。
  怀疑环境不对 / 第一次在这台机器上跑 → 补读 [`doc/26-本机环境实况.md`](doc/26-本机环境实况.md)，
  或直接 `python tests/verify_env.py`（一条命令体检完，比读文档快）。
- **写代码前**：扫一眼 `doc/lessons/README.md` §三「复发判据速查」——本项目同一类缺陷已复发多次，那张清单是防它的。
- **改完代码**：必须清 `__pycache__`（`find . -name __pycache__ -type d -prune -exec rm -rf {} +`），
  否则跑旧字节码、静默回退到 rule 降级分支（`AGENTS.md` 硬约束 2）。
- **specs 驱动**：改动同步到 `specs/<最新>/04_tasks.md` 执行账；spec 的 `execution-log.md` 只追加、不改写历史。
- **非交互 shell 的 PATH 陷阱**（本 harness 特有）：Claude Code 起的 shell **不是登录 shell**，
  `/opt/homebrew/bin` 不在 PATH 里 → `ollama` / `ffmpeg` / `rsvg-convert` **全部 command not found**，
  即使它们在 boss 的终端里能跑。
  凡要调外部二进制，先 `export PATH="/opt/homebrew/bin:$PATH"` 或直接用绝对路径。
  **不要因为 `which ffmpeg` 失败就判断"用户没装 ffmpeg"** —— 那是假阴性（doc/26 §三）。
- **对外动作**：`git push` / 建仓 / 公开发布 / 发内容 —— **必须 boss 确认**，不得自行执行。
- **打包**：改完 `packaging/` 后跑 `bash packaging/build_app.sh --check` 看**可分发性**结论；
  产出不可分发的包会被门禁拦下（这是故意的，见 `doc/lessons/README.md` L-10）。

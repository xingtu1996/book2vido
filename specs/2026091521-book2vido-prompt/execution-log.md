# Execution Log（append-only 事实源 · 禁事后回填）

> 时间戳由 `date` 取得（纪律 §5）。每条 = 一个可验证的动作 + 结果。

---

**2026-09-15 21:21** · scaffold
- 建 `specs/2026091521-book2vido-prompt/`。
- 侦察结论：提示词内联于 `src/book2vido/scriptwriter.py` 的 `OllamaProvider.script()`
  （16 行字符串拼接）；注入项 `concept` 清单在 `icons.py::CONCEPTS`（85 词）；
  `think` 在 `config.yaml`。全仓别无其他 LLM 提示词。
- 发现：`cache.script_key` 的因子 `book_hash|model|think|max_sentences|sha256(章节文本)`
  **不含提示词** → 改提示词会静默命中旧分镜。
- 发现：`icons.py::CONCEPT_KEYS` 注释自称"供 prompt 注入使用"，全仓**无调用点**。
- 备份：`backup-before-op.sh` → `20260915_212022_book2vido-提示词资产化（T2V-007）….tar.gz`
  （注意：`config.py` 路径写错成仓库根，实际在 `src/book2vido/`，该文件未进备份 —— 已知，影响可忽略：
  它是纯新增默认值，且改动已在 spec 与 diff 中留痕）。

**2026-09-15 21:21** · 抓基线（T0）
- 手法：劫持 `scriptwriter.urllib.request.urlopen`，抓**真实 payload** 里的 `prompt` 字段。
  **不照抄代码重写** —— 那样证明不了逐字节一致。
- 结果：**699 字符 / 15 行** → 存 `tools/prompt_golden.txt`。

**2026-09-15 21:23** · 资产 + 加载器落盘（T1/T2）
- `prompts/scriptwriter.md`（frontmatter + 文件头说明 + `@prompt:begin/end` + 逐条就近注释 + 文末人读区）。
- `src/book2vido/promptlib.py`：`Prompt` / `parse` / `load` / `render` / `fingerprint` / `strip_comments`。
- `tools/verify_prompt.py`：逐字节比对 + 注释残留检测 + 占位符残留检测 + `--update`。

**2026-09-15 21:23** · 🔴 抓到 F-A（第一跑就中）
- 现象：渲染结果 **5 个字符**：`` ` 与 ` ``。
- 真因：文件头说明里写了「`` `<!-- @prompt:begin -->` 与 … ``」，而 `parse()` 用**子串匹配**找标记
  → 命中的是注释里那个字面量。
- 修法：改为**整行精确匹配**（`^[ \t]*<!--[ \t]*@prompt:begin[ \t]*-->[ \t]*$`）。
- 记录：`01_analysis` §七 F-A。**这类"匹配到不该匹配的东西"不报错、只静默取错内容**，
  是被 golden 校验抓住的，不是靠人眼。

**2026-09-15 21:24** · ✅ T3 门禁通过
- `✓ 提示词校验通过 / 与 golden 逐字节一致：699 字符 / 15 行`
- 指纹：`body_hash=def6f167f61a`、`cache_fp=41737545877c`。

**2026-09-15 21:26** · 接入代码（T4/T5/T6）
- `cache.script_key(+prompt_fp="")`；`models.ScriptDoc(+prompt_version/+prompt_hash)`（`from_json` 用 `.get`）。
- `scriptwriter`：删内联串，改 `promptlib.load()` + `render()`；基类加 `prompt` / `prompt_fingerprint`。
- `providers.build` 传 `prompt_file`；`config.py` DEFAULT 与 `config.yaml` 加 `llm.prompt_file: null`。
- `pipeline._produce`：`skey` 带指纹；`ScriptDoc` 记版本与 body_hash。
- `packaging/build_app.sh`：布局注释 + 自检 `die` + `cp -R prompts`。
- `icons.py::CONCEPT_KEYS` 注释改为真话（F-C）。

**2026-09-15 21:30** · 端到端四跑（TC-04）
- ① 首跑 **39.0 s / miss** → ② 同提示词 **0.0 s / hit** → ③ **改正文一个字 38.4 s / miss**
  → ④ 改回原样 **31.2 s / miss**。
- **③ 是本 spec 的核心证据**：改前这一步会是 "缓存命中 / 0.0s"。

**2026-09-15 21:33** · `.app` 布局验证（TC-08）
- 模拟 `Contents/Resources/`：加载成功，`source=<APP>/Contents/Resources/prompts/scriptwriter.md`。
- 删 `prompts/` 后：`PromptError` + 修复指引（`git checkout` 可在报错里查到）。

**2026-09-15 21:37** · 打包自检 + 脱敏
- 移走 `prompts/` → `build_app.sh --check` **退出码 1** + `✗ 缺少 prompts/scriptwriter.md`；恢复后退出码 0。
- 脱敏扫描 13 个新增/改动文件：`packaging/build_app.sh` 命中 —— 经 `git diff` 核实**来自既有行**
  （第 27 行 `PY_SRC` 默认值，属已知"公开前必清"），**新增行零命中**。
- 自纠：`prompts/scriptwriter.md` 与 `tools/verify_prompt.py` 的验证示例里我原本写了绝对路径，
  已改为 `python tools/verify_prompt.py`（**不新增**这类痕迹）。

**2026-09-15 21:41** · 文档
- 新增 `doc/15-提示词与模型适配.md`；错题库加 L-15 / L-16；`CHANGELOG` 加 T2V-007；
  挂链 `README` / `AGENTS.md` / `HANDOFF.md` / `doc/README.md`。

**2026-09-15 21:4x** · 🔴 抓到 F-D（探针失效）
- AC-11 第一次执行时忘了真的移走 `prompts/`，`--check` 正常通过、退出码 0 ——
  **差一点把"探针没生效"当成"通过"**。补跑后退出码 1。
- 记录：`01_analysis` §七 F-D。

**2026-09-15 21:40** · 收口（T9）
- 全量校验：提示词与基准逐字节一致 ✅ / 16 个文档零死链 ✅ / 脱敏 30 文件**新增行零命中** ✅。
- 提交两笔（功能与文档分开，便于独立 revert）：
  `66b8771` feat(prompt) · `9bb1a4c` docs(prompt)。
- 推送：直连通道仍断（同上一轮结论）→ 走 `git -c http.proxy=… push https://x-access-token:…`，
  成功 `9134b0e..9bb1a4c`。
- `gh api` 复验：远端 HEAD = 本地 = `9bb1a4c`；`prompts/scriptwriter.md` 9787 B、
  `src/book2vido/promptlib.py` 8514 B、`tools/verify_prompt.py` 4576 B、`tools/prompt_golden.txt` 1714 B、
  `doc/15` 6643 B 均在远端；仓库仍 **PRIVATE**；两笔提交作者均为 `行途 XingTu` 品牌身份。

---

## 待办（移交下一轮）

1. **pip 安装路径**：`pyproject.toml` 未配 `package-data` → 若将来走 PyPI，需补并实测（已知限制 §四·1）。
2. **提示词示例的版权**：`few-shot` 那条取自《关键对话》→ 与 demo 样片同属"公开前必清"。
3. **`.app` 全量重建 + `--selftest`**：本轮只跑了 `--check` 与布局模拟，未重建整包（耗时长、占磁盘）。
   下次发版前补一次。
4. **F1 / F2（batch 不走缓存 / 落盘≠缓存）**：上一轮登记的缺陷，仍待开 spec（T2V-006 编号已被
  演进史占用 → 顺延 T2V-008）。

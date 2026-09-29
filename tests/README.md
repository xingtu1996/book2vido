# tests/ · 可回归断言（守护脚本）

> **这里放的是「会红的东西」**：每条都是**可证伪的断言**，跑出来必须是绿的。
> 一次性探索脚本（探针 / 基准 / 剖析）不在这儿，在 [`../tools/`](../tools/)。

## 为什么从 `tools/` 分出来

`tools/` 曾经同时装着两类性质完全不同的脚本：

| | 性质 | 跑的时机 | 红了意味着 |
|---|---|---|---|
| **`tests/`** | **可回归断言** | 改动后 / 发布前 | **不该合入** |
| `tools/` | 一次性探针 · 基准 · 剖析 | 想量一下的时候 | "知道了"，不是"坏了" |

混住的后果不是难看，是**判断失灵**：`tools/` 里 8 个 `verify_*` 和 6 个 `probe_*`
挨在一起，没人说得清"哪些是必须跑绿的"。分出来之后这条界线是目录名本身，不需要记。

> 这条早就写在本项目的诊断里（[`../doc/17-结构诊断与重构方案.html`](../doc/17-结构诊断与重构方案.html)
> 「没有测试目录」），当时的结论是「档 3 延后，触发条件已写明」。
> 触发条件（脚本已多到分不清哪些必须绿）现在成立，故执行。

## 清单（跑法一律在仓库根）

| 脚本 | 守什么 | 什么时候必须跑 |
|---|---|---|
| `verify_deps.py` | **依赖方向**：无环 / 叶子层自足 / 方向禁令 / 导入风格统一 | **动了目录 / 拆了模块 / 抽了公共函数** |
| `verify_icons.py` | **图标资产自洽**：引用 ⊆ 实有（防离线静默降级）+ 实有 ⊆ 引用（防冗余） + 两表键不相交 | 改了词表 / 图标缓存 |
| `verify_gate.py` | **章节取料下限**：14 条边界断言 + 真实书截面 + 正文章零误伤 | 改了取料 / 下限判据 |
| `verify_prompt.py` | **提示词逐字节 golden**（`prompt_golden.txt`）+ 注释剥净 + 占位符替换 | 改了 `prompts/scriptwriter.md` |
| `verify_offline.py` | **铁律九**：socket 层拦全部外网，断言外网请求 = 0 且出片 | 改了抽取 / 画面 / 配音 / 合成任一环 |
| `verify_cache.py` | **缓存分层与失效键**：手改只重跑下游、`enabled=False` 不写盘 | 改了 `cache.py` |
| `verify_segmenter.py` | 分句 / 取料边界（含 TC-07 长章均匀采样） | 改了 `segmenter.py` |
| `verify_narrator_concurrency.py` | 配音并发不串音 | 改了 `narrator.py` / TTS 并发度 |

一键全跑（在仓库根）：

```bash
PY=$HOME/.workbuddy/binaries/python/envs/default/bin/python
for t in deps icons prompt cache segmenter; do $PY tests/verify_$t.py || echo "🔴 $t"; done
```

## 在 pytest / CI 里

`verify_*.py` 不在 pytest 默认的收集规则里，**不配 `python_files` 就一条都跑不到**
（表现为「0 条用例、退出码 5」，看着像通过）。现在 `pyproject.toml` 已经配了，
并且 `tests/test_verify_scripts.py` 会把**离线可跑**的那 5 条（deps / icons /
prompt / cache / segmenter）当子进程跑一遍、断言退出码 0：

```bash
pytest tests/ -q          # 11 passed
```

`env` / `gate` / `offline` / `narrator_concurrency` **不进 CI**：它们分别要
ollama 在跑、要真书、要完整出片、要联网 TTS —— 在 CI 上必然红，而红了不代表代码坏了。
这四条按上面的方式**按需单独跑**。

`gate` 需要真书、`offline` 慢（要跑完整出片），这两条**按需单独跑**。

## 写新守护脚本的三条

1. **纯标准库优先**（`ast` / `pathlib` / `json`）—— 守护脚本自己不该有依赖，
   否则"装不上依赖"会让守护本身失效。
2. **退出码要能用**：0 = 通过，非 0 = 红。别只在屏幕上打 ✅ 然后 `return 0`。
3. **守住的东西必须在本机测不出来** —— 若手测能发现，脚本就是负担不是资产。
   `verify_icons` / `verify_offline` 都是这条的产物：**有网时一切正常，用户离线才发现挂了**。

## 不在这儿

`tools/` 里的 `probe_*`（一次性探针）、`bench_ollama.py`（模型基准）、
`profile_pipeline.py`（环节耗时剖析）、`preview_theme.py`（主题预览出图）
—— 它们是**量具**，不是**判据**。

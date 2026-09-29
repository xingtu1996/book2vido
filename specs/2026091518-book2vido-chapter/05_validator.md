# 05 · 验证计划：目录索引与按需生成

> Ticket: T2V-002 | 日期: 2026-09-15 18:51 | 状态: 🔵

> 📜 本文件是**可执行验证脚本集**，不是事后文档。写代码前先看它，写完逐节跑，失败 → 修 → 重跑（Loop Engineering）。
> 本项目无 HTTP/DB，故验证载体为 **CLI 命令 + 产物断言 + 单元断言**，不使用 curl/SQL。

## 一、数据准备

```bash
# 统一环境变量（本机实测环境：M1 Pro 16GB / qwen3:8b / Ollama 0.33.2）
PY=~/.workbuddy/binaries/python/envs/default/bin/python
cd <工作区根>/book2vido
export PYTHONPATH=src

# 样本（自带内嵌 outline，348 页，93 条目录 / 35 条顶层）
PDF=<工作区根>/book2vido/关键对话.pdf
[ -f "$PDF" ] || echo "🔴 样本缺失，验证不可进行"

# 本地模型服务须在跑（否则 LLM 步降级，AC-4/AC-10 不可验）
curl -s --max-time 5 http://localhost:11434/api/tags | head -c 80 || echo "🔴 Ollama 未启动"

# 干净起点：验证缓存语义前先清缓存（缓存是可选产物，删除 = 回到无缓存行为）
[ -d cache ] && mv cache "cache.bak-$(date +%H%M%S)"
```

**前置检查**：`$PY -c "import PIL,pypdf,yaml,edge_tts; print('deps ok')"` → 须输出 `deps ok`。

## 二、CLI 验证用例

### TC-01: `outline` 产出 93 条目录

```bash
$PY -m book2vido outline "$PDF"
$PY - <<'EOF'
import json, pathlib, sys
f = sorted(pathlib.Path("cache").glob("*/outline.json"))[0]
d = json.loads(f.read_text())
print("origin =", d["origin"], "| chapters =", len(d["chapters"]), "| pages =", d["total_pages"])
assert d["origin"] == "pdf-outline", d["origin"]
assert len(d["chapters"]) == 93, len(d["chapters"])
assert d["total_pages"] == 348
pages = [c["start_page"] for c in d["chapters"]]
assert pages == sorted(pages), "页码非单调"
print("✅ TC-01")
EOF
```

**预期**：`origin = pdf-outline | chapters = 93 | pages = 348`，断言全过。

### TC-02: `list` 打印两级树

```bash
$PY -m book2vido list "$PDF" | head -20
$PY -m book2vido list "$PDF" | grep -c "^第\|^  "   # 顶层 + 缩进层各计数
```

**预期**：顶层 35 行，含页码与标题；样例首行应形如 `[p27] 第1章 何谓关键对话`。

### TC-03: 兜底链三态（AC-3）

```bash
$PY - <<'EOF'
import sys; sys.path.insert(0, "src")
from book2vido import outline

# ① whole-doc：纯文本
open("/tmp/t2v_fixture.md", "w").write("关键对话\n" * 500)
doc = outline.build("/tmp/t2v_fixture.md")
assert doc.origin == "whole-doc" and len(doc.chapters) == 1, (doc.origin, len(doc.chapters))
print("✅ ① whole-doc")

# ② regex：直接调兜底函数，并与主路径交叉核对（主路径可用时即真值）
from book2vido import extractor
import re
P = "<工作区根>/book2vido/关键对话.pdf"
pages = extractor.extract_pages(P)
alt = outline._regex_flat(pages)
main = [c for c in outline.build(P).top() if re.match(r"^第\s*\d+\s*章", c.title)]
assert len(alt) == len(main) == 11, (len(alt), len(main))
assert all(abs(m.start_page - a[2]) <= 1 for m, a in zip(main, alt)), "页码漂移 >1"
print(f"✅ ② regex：{len(alt)} 章，页码与主路径差 ≤1")

# ③ pdf-outline：正常路径
assert outline.build(P).origin == "pdf-outline"
print("✅ ③ pdf-outline")
EOF
```

### TC-04: `--chapter 3` 文本不越界（AC-4 · P0）

```bash
$PY -m book2vido run --input "$PDF" --out samples/t2v_ch03.mp4 --chapter 3
ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 samples/t2v_ch03.mp4
# 文本溯源：送 LLM 的片段必须落在第 3 章页码范围
$PY - <<'EOF'
import json, pathlib
f = sorted(pathlib.Path("cache").glob("*/outline.json"))[0]
d = json.loads(f.read_text()); top = [c for c in d["chapters"] if c["depth"] == 0]
ch3 = top[2]
print(f"第3章 = {ch3['title']}  p{ch3['start_page']}-p{ch3['end_page']}")
EOF
```

**预期**：mp4 生成成功、时长 >0；打印的第 3 章页码区间与 `03_design` 中 `segmenter` 取料范围一致；
送 LLM 的文本不得包含第 2/4 章标题（人工抽样核验）。

### TC-05: `--chapters 1,3,5` 与越界报错（AC-5）

```bash
$PY -m book2vido run --input "$PDF" --out samples/g --chapters 1,3,5
ls samples/g/*.mp4 | wc -l          # 预期 3
$PY -m book2vido run --input "$PDF" --out samples/g --chapter 999; echo "退出码=$?"
# 预期：明确报错 + 非 0 退出码，不得静默产出
```

### TC-06: `--all` 单章失败不阻塞（AC-6）

```bash
$PY -m book2vido run --input "$PDF" --out samples/all --all --fast 2>&1 | tail -20
echo "退出码=$?"
```

**预期**：末行汇总「成功 N / 失败 M」；本次若 M>0，退出码非 0；单章失败后其余章继续。

### TC-07: 长章均匀采样（AC-7 · P0）

```bash
$PY - <<'EOF'
import sys; sys.path.insert(0, "src")
from book2vido import extractor, outline, segmenter
pages = extractor.extract_pages("<工作区根>/book2vido/关键对话.pdf")
doc = outline.build("<工作区根>/book2vido/关键对话.pdf")
top = doc.top()
long_ch = max(top, key=lambda c: c.pages)
t = segmenter.slice_chapter(pages, long_ch, max_chars=2500)
print(f"章「{long_ch.title}」{long_ch.pages} 页 → 片段 {len(t)} 字")
assert len(t) <= 2500
# 均匀采样：首/中/尾三段都应有代表文本
head, mid, tail = t[:200], t[len(t)//2-100:len(t)//2+100], t[-200:]
assert head and mid and tail
print("✅ TC-07")
EOF
```

### TC-08: TTS 并发 ≤5s · 12/12（AC-8 · P0）

```bash
$PY book2vido/tools/probe_tts_concurrency.py 2>&1 | tail -6
```

**预期**：12 线程一行显示耗时 ≤5s、成功 12/12（基线记录：串行 28.9s / 10–12 成功）。

## 三、数据一致性验证

### 链 1: 页文本 ↔ 目录页码

```bash
$PY - <<'EOF'
import sys; sys.path.insert(0, "src")
from book2vido import extractor, outline
p = "<工作区根>/book2vido/关键对话.pdf"
pages = extractor.extract_pages(p); doc = outline.build(p)
assert len(pages) == doc.total_pages, (len(pages), doc.total_pages)
assert 1 <= min(c.start_page for c in doc.chapters)
assert max(c.end_page for c in doc.chapters) <= len(pages)
print(f"✅ 链1：页数 {len(pages)} ↔ 目录页码范围一致")
EOF
```

### 链 2: 章节页码 ↔ 送 LLM 文本（防跨章污染）

```bash
# 断言：segmenter 对第 N 章返回的文本，不包含第 N+1 章标题首 8 字
$PY - <<'EOF'
import sys; sys.path.insert(0, "src")
from book2vido import extractor, outline, segmenter
p = "<工作区根>/book2vido/关键对话.pdf"
pages = extractor.extract_pages(p); doc = outline.build(p); top = doc.top()
bad = []
for a, b in zip(top, top[1:]):
    t = segmenter.slice_chapter(pages, a)
    nxt = b.title[:8]
    if nxt and nxt in t:
        bad.append((a.title, nxt))
print("跨章污染:", bad if bad else "无")
assert not bad
print("✅ 链2")
EOF
```

> ⚠️ 注意：此法对**目录页**天然误报（目录里会出现所有章名）。若第 1 章命中，需人工确认是否取自目录页——
> 这也是 `segmenter` 应跳过「目录页」的验收依据。

### 链 3: `script.json` 往返一致

```bash
$PY - <<'EOF'
import sys, json, pathlib; sys.path.insert(0, "src")
from book2vido.models import ScriptDoc
f = sorted(pathlib.Path("cache").glob("*/ch*/script.json"))[0]
d = ScriptDoc.from_json(f.read_text())
assert d.scenes, "分镜为空"
assert all(2 <= len(s.text) <= 60 for s in d.scenes)
assert d.to_json() and json.loads(d.to_json())["scenes"][0]["text"] == d.scenes[0].text
print(f"✅ 链3：{f.name} {len(d.scenes)} 句往返一致")
EOF
```

### 链 4: 句数 ↔ 卡数 ↔ 音轨数 ↔ 成片时长

```bash
$PY - <<'EOF'
import sys, json, pathlib, subprocess; sys.path.insert(0, "src")
d = sorted(pathlib.Path("cache").glob("*/ch*"))[0]
script = json.loads((d / "script.json").read_text())
n = len(script["scenes"])
cards = len(list(d.glob("card_*.png"))); voices = len(list(d.glob("voice_*.*")))
assert cards >= n and voices >= n, (n, cards, voices)
dur = float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration",
      "-of","default=nw=1:nk=1", str(d / f"{d.name}.mp4")]))
print(f"✅ 链4：句 {n} / 卡 {cards} / 音 {voices} / 成片 {dur:.1f}s")
assert dur > 0
EOF
```

## 四、安全三条件验证（必做，不可跳过）

### 4.1 退出条件

| # | 检查项 | 命令 | 预期 |
|---|--------|---------|------|
| 1 | `--no-cache` 整体关缓存 | `run --no-cache` 后 `ls cache/*/ch*/.keys.json` | 无新缓存写入，行为与今天一致 |
| 2 | TTS 有重试上限 | 注入必失败文本（TC-09 单元） | 重试 ≤2 次后放弃，**不无限重试** |
| 3 | 降并发有下限 | 注入 >50% 失败（TC-09） | 降并发 → 串行 → 抛错，日志可见每档 |
| 4 | `--all` 单章失败不阻塞 | TC-06 | 其余章继续，末尾汇总并返回非 0 |

### 4.2 幂等条件

| # | 检查项 | 命令 | 预期 |
|---|--------|---------|------|
| 1 | 同输入重跑不产生重复产物 | 同命令跑 2 次，比对 `ls ch03/` | 卡/音/片数量不变（覆盖写） |
| 2 | 全命中直接返回 | 第 2 次跑计时 | ≤2s 返回既有 mp4 |
| 3 | `script.json` 命中跳过 LLM | 删 `card_*` 后重跑 | 不重新分镜（无 LLM 耗时），只重渲染 |
| 4 | 章间目录隔离 | 并发跑 `--chapter 3` 与 `--chapter 4` | 各自 `ch03/` `ch04/` 无交叉写 |

### 4.3 回滚条件

| # | 检查项 | 命令 | 预期 |
|---|--------|---------|------|
| 1 | 备份存在且可覆盖 | `ls -la .backups/2026091518-chapter/` | 含改动前 `*.py` |
| 2 | cache 目录可直接删（无副作用） | `mv cache /tmp/ && run` | 行为退化为无缓存，产出正常 |
| 3 | 旧 CLI 不破 | TC-14 | `run --input --out` 行为与 T2V-001 一致 |
| 4 | `extractor.body()` 仍可调用 | `python -c "from book2vido.extractor import body"` | 导入成功（函数保留） |

## 五、合规检查

| # | 检查项 | 命令 | 预期 |
|---|--------|---------|------|
| 1 | 零公司 key（宪法铁律一） | 全仓检索 `codemax\|codeMax\|公司\s*key\|api_key=sk-` | 零命中；`config.yaml` 无任何 key 字段 |
| 2 | 无付费 API 调用 | 检索 `requests\.\|httpx\|openai\|anthropic` | 仅 `urllib.request` 打 `localhost:11434`；无外部付费端点 |
| 3 | 断网可出片（铁律一） | TTS 切 `say`：`config.yaml → tts.provider: say` 后 `run` | 产出合法 mp4（无网） |
| 4 | 成本仍为 ≈¥0 | 看 CLI 成本日志 | 打印 `≈ ¥0.000x（仅电费）` |
| 5 | 模块行数上限（AC-16） | `wc -l src/book2vido/*.py` | 除 `icons.py` 外均 ≤200 |
| 6 | 无 emoji（品牌军规 P028） | 检索 `icons.py` / `visualizer.py` / 新增文件 | 代码与产出的 UI 文案无 emoji |
| 7 | 铁律/宪法违规检查 | 对照 `laws.md` + `CONSTITUTION.md` | 零违规（逐条打勾并可举证） |

## 六、合并后对账

> 逐条 AC 核对最终交付，防「验证过了但某链路漏适配」逃逸。

| AC# | 结论（✅实现 / ⚠️跑偏 / 🔴风险） | 证据（文件 / 命令输出） |
|-----|:---:|------|
| AC-1 | | |
| AC-2 | | |
| AC-3 | | |
| AC-4 | | |
| AC-5 | | |
| AC-6 | | |
| AC-7 | | |
| AC-8 | | |
| AC-9 | | |
| AC-10 | | |
| AC-11 | | |
| AC-12 | | |
| AC-13 | | |
| AC-14 | | |
| AC-15 | | |
| AC-16 | | |

### 审核签字（责任绑定）

> 审核须独立视角；签字者对合并验收负责；内容变更后签字失效。

| 项 | 值 |
|------|------|
| 产品/需求视角审核（AC 对账签字） | 待 boss |
| 合并验收责任 | 小研（待 Phase 5 完成后填） |
| 发布责任（无发布场景 N/A） | N/A |
| 结论（✅可合并 / ⚠️带风险 / 🔴打回）+ 日期 | 待 Phase 5 |

## 七、手工验证

- [ ] 拖 `关键对话.pdf` 到 `Book2Vido.app` → 默认行为与今天一致（AC-14 的人工面）
- [ ] `book2vido list` 输出对着纸质书目录肉眼核验前 5 条页码
- [ ] 手工改 `script.json` 一句话 → 重跑 → 成片里听到改后的词（AC-10 ③）

---

## Loop Engineering 使用说明

```
┌──────────┐   失败    ┌──────────┐   失败    ┌──────────┐
│ 写代码     │ ──────→ │ 跑 §二 TC │ ──────→ │ 查 §三/四 │
│          │ ←────── │          │ ←────── │          │
└──────────┘  修代码  └──────────┘  修代码  └──────────┘
                                                │
                                            全部通过
                                                ↓
                                         ✅ 可提交（Phase 6）
```

**AI 使用**：写码前读全部 TC → 写码后逐节跑并记录 → 失败修码重跑到全过 → `04_tasks` Phase 5 打勾。
**人工审查**：逐项验证，每个勾选项须有通过证据（命令输出 / 文件清单 / ffprobe 结果）。

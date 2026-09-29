# 05 · 验证脚本集

> 全部可执行。约定：`PY=<项目 python>`；在**仓库根**执行；`PYTHONPATH=src`。
> 7 组 TC，覆盖 16 条 AC。**每条都给出实际输出**（实施期实测，非预期值）。

---

## TC-01 · 逐字节一致 ← AC-01 / AC-04 / AC-12

```bash
$PY tools/verify_prompt.py
```

实测输出：

```
✓ 提示词校验通过
   与 golden 逐字节一致：699 字符 / 15 行
   资产：v1 · qwen3:8b · <项目根>/prompts/scriptwriter.md
   指纹：body_hash=def6f167f61a  cache_fp=41737545877c
   注释已剥净 · 占位符全部替换 · concept 清单 85 词
```

**为什么这是硬门禁**：699 字符是**重构前**用 `urlopen` 劫持抓到的真实 payload。
它相等 ⇒ 搬出代码这个动作**没有改变任何送进模型的内容**。

---

## TC-02 · 解析健壮性 ← AC-05 / AC-06

```bash
PYTHONPATH=src $PY - <<'PY'
from book2vido import promptlib
base = open("prompts/scriptwriter.md", encoding="utf-8").read()

# ① 缺 end 标记
try:
    promptlib.parse(base.replace("<!-- @prompt:end -->", ""), "缺end")
    print("✗ 没报错")
except promptlib.PromptError as e:
    print("✓ 缺标记报错:", str(e)[:46])

# ② 占位符漏传
p = promptlib.load()
try:
    p.render(max_n=12, chunk="x")          # 故意不传 concept_list
    print("✗ 没报错")
except promptlib.PromptError as e:
    print("✓ 漏占位符报错:", str(e)[:46])
PY
```

实测：`✓ 缺标记报错: 缺end 缺少正文标记…` / `✓ 漏占位符报错: 提示词「scriptwriter」有未替换的占位符：['concept_list']…`

---

## TC-03 · 注释不影响指纹 ← AC-03

```bash
PYTHONPATH=src $PY - <<'PY'
from book2vido import promptlib
raw = open("prompts/scriptwriter.md", encoding="utf-8").read()
p0 = promptlib.parse(raw, "原")
p1 = promptlib.parse(raw.replace("<!-- @prompt:begin -->\n",
      "<!-- @prompt:begin -->\n<!-- 新加的注释 -->\n"), "加注释")
print("body 逐字节相同:", p0.body == p1.body)
print("指纹相同:", p0.fingerprint(concept_list="A") == p1.fingerprint(concept_list="A"))
PY
```

实测：`body 逐字节相同: True` / `指纹相同: True`
→ **注释真的免费**：不占 token、不改变行为、不让缓存失效。

---

## TC-04 · 改提示词触发缓存失效（端到端）← AC-02

```bash
W=/tmp/tc04; rm -rf $W; mkdir -p $W
printf '# 测试\n\n能用脚本高效完成的事，就交给脚本。\n\n模型只应出现在真正需要判断的地方。\n' > $W/in.md
run_it () { PYTHONPATH=src $PY -m book2vido run --input $W/in.md --chapter 1 \
            --out $W/$1.mp4 --cache-dir $W/cache --fast 2>&1 | grep -E "分镜|缓存"; }
run_it a
run_it b
cp prompts/scriptwriter.md /tmp/tc04.bak
$PY -c "import pathlib;p=pathlib.Path('prompts/scriptwriter.md');p.write_text(p.read_text(encoding='utf-8').replace('口播短视频脚本','口播短视频文案'),encoding='utf-8')"
run_it c
cp /tmp/tc04.bak prompts/scriptwriter.md
run_it d
```

实测（qwen3:8b · `--fast`）：

| 步 | 动作 | 结果 |
|:--:|---|---|
| ① | 首跑 | `分镜：81 字 → 本地模型` · **39.0 s / miss** |
| ② | 同提示词 | `分镜：缓存命中 12 句（跳过模型）` · **0.0 s / hit** |
| ③ | **改正文一个字** | `分镜：81 字 → 本地模型` · **38.4 s / miss** ← 本 spec 的核心修复 |
| ④ | 改回原样 | **31.2 s / miss**（`.keys.json` 只记最后一次键——已知行为，非缺陷） |

**③ 是判据**：改前，这一步会打印"缓存命中"、耗时 0.0s，而用户以为自己的改动生效了。

---

## TC-05 · 缺资产时明确报错 ← AC-07

```bash
PYTHONPATH=src $PY - <<'PY'
from book2vido import promptlib
try:
    promptlib.load(path="/tmp/不存在.md")
except promptlib.PromptError as e:
    print(str(e))
    print("含修复指引:", "git checkout" in str(e))
PY
```

实测：报错含三行指引（默认位置 / `config.yaml` 的 `prompt_file` / `git checkout -- prompts/`），`含修复指引: True`

---

## TC-06 · 产物溯源 + 向后兼容 ← AC-08

```bash
PYTHONPATH=src $PY - <<'PY'
import json
from book2vido.models import ScriptDoc
d = ScriptDoc(1, "标题", [], "qwen3:8b", True, "2026-09-15 21:21",
              prompt_version="1", prompt_hash="def6f167f61a")
j = json.loads(d.to_json()); print("新产物:", j["prompt_version"], j["prompt_hash"])
old = '{"chapter_index":1,"title":"t","scenes":[],"model":"m","think":true,"created":"x"}'
d2 = ScriptDoc.from_json(old)
print("读老 script.json 不炸:", d2.prompt_version == "" and d2.prompt_hash == "")
PY
```

实测：`新产物: 1 def6f167f61a` / `读老 script.json 不炸: True`
（真跑产物里也是 `prompt_version='1' prompt_hash='def6f167f61a'`）

---

## TC-07 · 外部提示词（不改代码）← AC-09

```bash
mkdir -p /tmp/tc07 && sed 's/口播短视频脚本/口播短视频文案/' prompts/scriptwriter.md > /tmp/tc07/alt.md
cat > /tmp/tc07/cfg.yaml <<'EOF'
llm: {provider: ollama, model: "qwen3:8b", think: false, prompt_file: /tmp/tc07/alt.md}
limits: {max_sentences: 12, max_chars: 2500}
cache: {enabled: true, dir: /tmp/tc07/cache}
EOF
PYTHONPATH=src $PY -m book2vido run --input /tmp/tc04/in.md --chapter 1 \
  --out /tmp/tc07/x.mp4 --config /tmp/tc07/cfg.yaml --fast 2>&1 | grep 分镜
$PY -c "import json,glob;print([json.load(open(f))['prompt_hash'] for f in glob.glob('/tmp/tc07/cache/*/ch01/script.json')])"
```

实测：产物 `prompt_hash=['7eebba9fa500']` ≠ 仓库版 `def6f167f61a`
→ **换模型/追 SOTA 时可以拿这个当试验台**：复制一份改，不碰仓库文件。

---

## TC-08 · 打包与降级拒绝 ← AC-10 / AC-11 / AC-14 / AC-15

```bash
# ① 模块行数 / 依赖
wc -l src/book2vido/promptlib.py
grep -E "^(import|from) " src/book2vido/promptlib.py

# ② 模拟 .app 布局（关键：parents[2] 回溯到 Contents/Resources/）
T=/tmp/tc08/Contents/Resources; rm -rf /tmp/tc08; mkdir -p $T/app
cp -R src/book2vido $T/app/book2vido; cp config.yaml $T/; cp -R prompts $T/prompts
$PY -c "import sys;sys.path.insert(0,'$T/app');from book2vido import promptlib;print(promptlib.load().source)"

# ③ 缺资产 → 构建必须失败
mv prompts /tmp/tc08_hold; bash packaging/build_app.sh --check; echo "退出码 $?"; mv /tmp/tc08_hold prompts
```

实测：

```
172 src/book2vido/promptlib.py            ← ≤200 ✓
import hashlib / import re / from dataclasses / from pathlib   ← 零第三方依赖 ✓
<APP>/Contents/Resources/prompts/scriptwriter.md   ← 回溯正确 ✓
✗ 缺少 prompts/scriptwriter.md（分镜提示词资产） / 退出码 1   ← 坏包被拦住 ✓
```

---

## 汇总

| TC | 覆盖 AC | 结果 |
|---|---|---|
| TC-01 | AC-01 / AC-04 / AC-12 | ✅ |
| TC-02 | AC-05 / AC-06 | ✅ |
| TC-03 | AC-03 | ✅ |
| TC-04 | AC-02 | ✅ |
| TC-05 | AC-07 | ✅ |
| TC-06 | AC-08 | ✅ |
| TC-07 | AC-09 | ✅ |
| TC-08 | AC-10 / AC-11 / AC-14 / AC-15 | ✅ |
| 脱敏扫描（`04_tasks` §三 AC-16） | AC-16 | ✅ 新增行零命中 |
| 人工核对（结构三段） | AC-13 | ✅ |

**16/16 通过**；validator-check（无占位符残留 / 无 `TODO`）✅。

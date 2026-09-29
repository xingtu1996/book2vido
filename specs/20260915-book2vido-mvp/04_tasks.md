# 04 · Tasks（MVP 任务清单）

- [x] T1 项目骨架 + `config.yaml` + `requirements.txt`（pypdf/edge-tts/Pillow/pyyaml）
- [x] T2 extractor 模块（pypdf + MD 直读，输出分段文本）
- [x] T3 scriptwriter 模块（OllamaProvider 接 Qwen3-8B + RuleFallbackProvider 降级）
- [x] T4 visualizer 模块（Pillow 信息卡 + 行途蓝规范 + TextPrism 关键词图标）
- [x] T5 narrator 模块（EdgeTTSProvider + SayProvider 降级）
- [x] T6 compositor 模块（FFmpeg 拼卡+语音 → 竖版 mp4）
- [x] T7 CLI 入口 `python -m book2vido run`
- [x] T8 端到端跑 `book2vido/关键对话.pdf` 出第一条样片
- [x] T9 成本日志（打印每条电费估算 / 明确 ¥0）
- [x] T10 validator 自测闭环（见 05_validator）

## 备注
- T3 的 OllamaProvider 已真·跑通：本地 `qwen3:8b`（5.2GB，Ollama 0.33.2）接 `localhost:11434`，零公司资源。
- **精炼样片实测（2026-09-15 终版）**：12 句精炼短口播、28s、成本 ≈ ¥0.00044（仅电费），全程零公司 key。
- 关键修复记录（已落代码）：
  1. `pipeline.run` 未传 config_path → `load(None)` 永远用 DEFAULT（rule）。改 `__main__.py` 默认读项目根 `config.yaml`，`provider: ollama` 才生效。
  2. `extractor.body()` 的 `min_skip=600` 把真实「第1章@465字」排除，退路取书 1/6 处。改 `min_skip=150` 命中正文。
  3. Ollama `format:"json"` 在 qwen3+ollama0.33 返回 `request body is empty`。去掉 format，改从 response 文本正则提取 `[...]` JSON 数组。
  4. 上述修复需 `rm -rf __pycache__` 清旧字节码，否则跑的是修改前缓存逻辑。

## 二轮：工程加固与内容工厂（2026-09-15 下午）

- [x] T11 `compositor` 改**绝对路径** list + `pipeline` 每次运行隔离 `.work_<文件名>/`（修 concat 崩溃 + 跨 run 覆盖）
- [x] T12 加 `pyproject.toml` + `pip install -e .`（**项目根目录**即可 `python -m book2vido`，修开源体验硬伤）
- [x] T13 补 `LICENSE`(MIT) / `.gitignore` / `CONTRIBUTING.md`
- [x] T14 术语一致性：全项目 `7b→8b` 共 7 处（含 `config.py` 默认值 + README/doc/spec）
- [x] T15 内容工厂泛化①：`samples/省Token实战包装.mp4`（12 句，66.3 s，≈¥0.00033，零公司 key）
- [ ] T16 内容工厂泛化②：`人话翻译术` **run2 卡死**，待排查（`HANDOFF.md` §5.8）
- [ ] T17 `git init` + 首次 commit（**push 待 boss 拍板**）
- [x] T18 交接文档：`HANDOFF.md`（会话交接）+ `AGENTS.md`（接续须知）

### 未决 bug（下一棒优先）
- `SayProvider` 回退后 `voice_N.mp3` 可能 0 字节（缺非空校验）；疑似连锁导致 run2 僵死 → 建议加 edge-tts 超时 + 输出校验 + 逐句进度日志。

## 三轮：画面层重建（2026-09-15 傍晚）

**动因**：boss 反馈「生成的视频都没画面」——排查发现是**真 bug**：`visualizer` 硬编码
`/System/Library/Fonts/PingFang.ttc`，本机**无此文件**，`except` 静默回退 Pillow 默认位图字体，
1080×1920 画布上文字只有几像素 → 「糊白纸」。修完后画面可读，但**构图仍是上 1/3 堆字**，
观感仍空。故本轮重建整个画面层。

- [x] T19 **字体候选链**：`PingFang → Hiragino Sans GB → STHeiti Light → Songti`，逐级回退 +
  **缺失打告警**（不再静默糊卡）；`config.py`/`config.yaml` 默认字体同步改
- [x] T20 **图标层**：新增 `src/book2vido/icons.py`
  - 数据源：**Iconify**（聚合 200k+ 开源图标；Tabler MIT 为默认集），`?color=` 直接上**行途蓝**
  - 渲染：`rsvg-convert`（优先）/ `cairosvg`（退路，macOS 需 `DYLD_LIBRARY_PATH=/opt/homebrew/lib`）
  - **中文关键词→图标**映射表 `KEYWORD_ICONS`（~90 条，覆盖 AI/工程化/效率主题）
  - **兜底图标链** `FALLBACK_ICONS`：未命中时按 `zlib.crc32` 稳定散列选图（**不能用内置 `hash()`**，字符串 hash 每进程随机化会导致同词换图）
  - **离线优先**：命中缓存即用；未缓存且无网 → 降级「关键词首字大字」版式，**永不中断出片**
- [x] T21 **版式重建**：序号+品牌 → 关键词大标题+短分隔线 → **主视觉面板**（480×620 圆角、`#F2F7FF`）+ 图标 → 居中正文（字号自适应）→ 水印
- [x] T22 **配套**：`python -m book2vido fetch-icons` 预热命令；`assets/icons/LICENSE.md`（Tabler MIT 归属）；
  `doc/08-画面资产策略.md`（画面层三级策略 + 216 风格资源辨析）；README 快速开始重写（补 `pip install -e .` + `brew install librsvg`）
- [x] T23 重跑成片验证：`samples/省Token实战包装.mp4`（12 句，27.9s，≈¥0.0004，零公司 key）

### 本轮关键结论
- **「216 种手绘插画风格」是文生图提示词库，不是现成素材**；需图像模型 → M1 16GB 成本/速度不达标 → 列为 **L3 预留**。仓库内也**只有它的介绍摘要，没有 216 条提示词本体**（元宝未捕获那个「在线文档」链接）。
- **画面层定为三级**：L1 关键词图标（已落地）/ L2 版式节奏（已落地）/ L3 文生图插画（预留）。
- **emoji 方案被否**：与品牌军规「黑白极简 + 行途蓝、无 emoji」冲突，改用线描图标。

### 遗留（下一棒）
- [ ] concat 时 ffmpeg 报 `Non-monotonic DTS`（`-c copy` 各 clip 音轨起始偏移所致）——输出正常，但建议加 `-fflags +genpts` 或音频重编码消除告警
- [ ] `人话翻译术` run2 卡死仍未定位（T16）
- [ ] T17 `git init` + 首次 commit（push 待 boss 拍板）

## 四轮：本地模型性能实测 + 思考模式显式化（2026-09-15 傍晚）

**动因**：boss 问「Ollama 装好了，有操作界面吗？测一下性能效果」。
**结论**：界面零安装即可现做（见 T27）；性能实测暴露一个**真隐患**（T24）。

- [x] T24 **`think` 显式化**（本轮最重要的代码修复）
  - **病根**：`scriptwriter` 从未传 `think`，行为依赖 qwen3 模型模板的**隐式默认（＝开思考）**。
    换模型/版本会静默改行为，代码里看不出来 → 属设计缺陷，不是性能调优。
  - **实测数据**（同素材口播稿任务）：不传 think 38.2s / 583 tok（思考 738 字）；
    `think=false` 18.4s / 152 tok；`think=true` 62.5s / 1030 tok。速度差 **2–3.4 倍**。
  - **不能一刀切关**：`think=false` 出现过句子碎片化（「用户上手要查六仓」），
    甚至**直接抄提示词里的 few-shot 示例**（首句变成示例原文「关键对话是高风险对话」）。
  - **落地**：`OllamaProvider(..., think=True)` 显式参数 + `config.yaml: llm.think: true`
    （带实测注释）+ `config.py` DEFAULT；CLI 新增 `--fast`（run/batch 均可）临时覆盖为 false。
- [x] T25 **性能基准工具**：`tools/bench_ollama.py`（6 用例：冷启动/暖机/思考对照/真实口播稿/长文；
  输出 TTFT、预填充 t/s、解码 t/s、思考字数、常驻内存）→ `/tmp/ollama_bench.json`
- [x] T26 **实测结论沉淀**：`doc/01-llm-local.md` 新增「性能实测」章（指标表 + think 取舍 + 容量结论）
- [x] T27 **零安装网页台**：`tools/ollama_webui.html`（17KB 单文件，零依赖，行途蓝，无 emoji）
  + `tools/start_webui.sh` 一键启动
  - 能力：流式对话 / **实时性能面板**（TTFT、解码 t/s、预填充、加载、tok 数）/ 参数调节
    （temperature、num_predict、num_ctx、思考开关）/ **卸载模型释放内存** / `?q=` 打开即问
  - **关键实证**：Ollama 默认放行 localhost 源（`Access-Control-Allow-Origin` 回显 + OPTIONS 204），
    因此**零安装**即可有网页界面；但 `file://` 的 Origin 是 `null` → **必须走 http://localhost**（故需 start 脚本）
  - 顺手修：15s 轮询会把模型下拉框重置 → 改为保留用户已选模型
- [x] T28 端到端验证（真浏览器 + CDP，非 mock）：连接态、流式回答、指标渲染、0 JS 异常、
  默认关思考（think blocks=0）全部通过

### 本轮实测硬数据（M1 Pro 16GB / qwen3:8b Q4_K_M / Ollama 0.33.2）
| 指标 | 实测 |
|---|---|
| 解码速率 | 14.3–17.3 tok/s（硬上限，与输入长度无关） |
| 预填充 | 最高 1332 tok/s；2500 字正文约 2s |
| 冷启动 | 4.91s（加载 5.2GB 到 GPU，100% GPU） |
| 常驻内存 | 5.9GB / 16GB |
| 首字延迟 | 关思考 0.12–0.79s；**开思考 27–67s** |
| 批量估算 | 约 40s/篇 → 50 篇 ≈ 33 分钟，夜间可跑 |

### 遗留（下一棒 · 本轮新增）
- [ ] `scriptwriter` 的 **temperature 显式设 0.3**（默认 0.8，怀疑导致抄示例退化），需 A/B 再验一轮
- [ ] `keep_alive` 调大（如 30m），批处理期间避免反复付 4.91s 冷启动
- [ ] `ollama_webui.html` 的 15s 轮询会挂起 headless 的虚拟时间（`--virtual-time-budget` 失效）——
  以后做无头验证要么去掉轮询，要么改用 CDP（本轮已踩，记入 skill）

---

## T29–T34 · 打包分发轮（一键安装 .app）

> 动因：让不懂命令行的人双击即用。这不是新功能，是把项目从"开发者工具"变成"产品"。

- [x] T29 **二进制定位层** `src/book2vido/binpaths.py`
  环境变量 → 随包 vendor → 常见包管理器路径 → PATH。
  **清掉 4 处硬编码**：`compositor.FFMPEG`、`narrator.FFPROBE`、`narrator` 的 ffmpeg、
  `icons` 的 `DYLD_LIBRARY_PATH=/opt/homebrew/lib`（改为动态探测 brew/MacPorts）。
  价值独立于打包：现在 Intel Mac / MacPorts / 自定义安装都能用。
- [x] T30 **堵住 0 字节音频**：`SayProvider.speak` 转换后校验输出非空，
  空了当场抛错（此前会静默产出空 mp3，崩在很远的 concat 阶段）。顺手加 `-nostdin`。
- [x] T31 **`.app` 骨架** `packaging/`：`Info.plist`（声明 PDF/MD/TXT 拖拽接收）、
  `launcher.sh`（双击=说明+开输出目录；拖文件=逐个出片；`--selftest` 自检）、
  `build_app.sh`（组装 + 体积报告 + 可注入外部二进制）。
- [x] T32 **构建通过**：`dist/Book2Vido.app` = **115 MB**（runtime 82M / vendor 31M / app 64K）。
  python 运行时 + 4 个依赖 + ollama 二进制 + 93 图标全部内置。
- [x] T33 **验收：模拟拖 PDF**：`Book2Vido 关键对话.pdf` → 产出 mp4，全程走随包运行时。
- [x] T34 文档 `doc/09-一键安装与分发.md`（体积账 / 三条生死线 / 分发形态对比 / Gatekeeper 现实）

### 三条生死线实测（决定方案能不能成立）
| 验证 | 结果 |
|---|---|
| standalone python 换目录还能跑？ | ✅ 搬到 /tmp 正常，cwd 无关 → 可内置 |
| ffmpeg 能只拷一个文件？ | ❌ `otool -L` 有 **18 个** homebrew 依赖 → **必须换 static build** |
| ollama 是静态的？ | ✅ **0 个** homebrew 依赖 → 可只拷 32MB 单文件 |

> 反直觉：**ffmpeg（420KB）比 ollama（32MB）更难分发**。体积小 ≠ 可移植。

### 已知缺口
- [ ] **ffmpeg 未内置**（当前唯一硬缺口）：需注入 static build
  （`BOOK2VIDO_FFMPEG_SRC=/path/to/ffmpeg bash packaging/build_app.sh`）
- [ ] 未签名公证：对外分发需 `xattr -dr com.apple.quarantine` 或 Apple 开发者证书
- [ ] 仅 arm64：Intel Mac 需各自构建
- [ ] 无 GUI 进度条：出片 40s~2min 期间用户看不到进展，只有完成/失败通知

### 下一轮候选（按价值排序）
- [ ] **目录感知分片**：PDF outline → 章节切片 → 逐片摘要 → 合成「全书 3 分钟版」。
      当前是"整篇抽 12 句"，对长书信息损失大
- [ ] **N 选 1 校验**：单次生成方差大（同任务测出 3 种体裁，见素材卡），
      同素材跑 3 版、按确定性规则挑 1 版（**绝不用"AI 检查 AI"**）


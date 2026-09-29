# Book2Vido 坏例索引（Bad Case Index）

> 记录所有踩过的坑，防止重复犯。每次改之前先扫一眼。
> 维护：doubao / 行途

---

## BCI-001 端口漂移（反复犯）

**症状**：每次重启服务，端口从 8765 跑到 8766/8767，老板浏览器开的还是旧端口，报 ERR_CONNECTION_REFUSED。

**根因**：`start_server()` 从 8765 开始找可用端口，被占了就自动跳下一个。

**修复**：固定 8765，启动前先手动清理旧进程。不要自动找下一个端口。

**教训**：端口要固定，不要"智能"自动找。用户记不住端口。

---

## BCI-002 pkill 杀自己（新犯）

**症状**：start_server 里加了 `pkill -f book2vido.gui` 清理旧进程，结果把自己也杀了，服务直接崩。

**根因**：子进程命令行也包含 `book2vido.gui` 字符串，pkill 模式匹配到了自己。

**修复**：去掉自动 pkill，改成启动前手动清理。

**教训**：pkill 模式要排除自己，或者用更精确的匹配（比如只杀 python3.1 且监听 8765 的）。

---

## BCI-003 Broken pipe（老问题）

**症状**：GUI 后台线程调 `pipeline.run()` 时报 `[Errno 32] Broken pipe`，发生在 "Calling local model..." 阶段。但命令行直跑是通的。

**根因**：ThreadingHTTPServer 的后台线程里，Ollama 的 HTTP 连接有问题。

**修复**：未彻底修。试过子进程方案（subprocess），但引入了新问题（os 没 import、端口冲突）。

**临时方案**：命令行直跑 pipeline 是通的，GUI 里偶尔断了就重试。

**教训**：后台线程跑长任务要隔离，不要在 HTTP handler 线程里直接调。

---

## BCI-004 macOS say 中文音色（新发现）

**症状**：用 `say -v Sandy "中文"` 读出来是英文发音，很怪。

**根因**：macOS 的 `say -v Sandy` 默认读英文。要读中文得用 `say -v "Sandy (中文（中国大陆）)"`。

**修复**：SayProvider 里自动加中文变体。

**教训**：macOS 音色要指定语言变体，不然默认用英文。

---

## BCI-005 "行途"多音字（新发现）

**症状**：TTS 把"行途"读成 háng tú（银行的行），应该是 xíng tú。

**根因**：神经网络模型没见过"行途"这个词，默认按"银行"读。

**修复**：试听文案改成"行·途"（中间加间隔号），引导模型读 xíng。

**教训**：人名/品牌名是多音字时，TTS 要用标点分隔或上下文引导。

---

## BCI-006 前后端字段不对齐（反复犯）

**症状**：前端调 `/api/progress`，后端是 `/api/status?job_id=xxx`，字段名 step/percent vs message/progress。

**根因**：改后端时忘了同步改前端。

**修复**：对齐字段名。

**教训**：前后端接口要写在同一个地方，改一边必须改另一边。

---

## BCI-007 拆分模块丢 import（B-048 复现）

**症状**：拆分 tasks.py 时报 `NameError: Path` / `NameError: threading`。

**根因**：从 server.py 拆函数到 tasks.py 时，没把 import 一起搬过去。

**修复**：补全 import。

**教训**：拆函数要把依赖的 import 一起搬。

---

## BCI-008 URL 编码特殊字符（新犯）

**症状**：音频文件名里的 `·` 字符在 URL 里被编码，后端找不到文件，404。

**根因**：`/api/voices/Xiaoyi_女声·活泼.mp3` 里的 `·` 在 URL 里变成 `%C2%B7`，后端直接 split 不对。

**修复**：加 `urllib.parse.unquote` 解码。

**教训**：文件名有特殊字符时，URL 必须 unquote。

---

## BCI-009 缓存目录里的旧 TTS（老坑）

**症状**：换了配音后，生成的视频还是旧音色。

**根因**：cache/ 目录里的 voice_X.mp3 是旧音色，pipeline 命中缓存就不重新生成。

**修复**：换配音后要清缓存。

**教训**：改 TTS 配置要清 cache。

---

## BCI-010 视频 URL 少后缀（新犯）

**症状**：历史输出点播放报 404，`/api/video/README` 少了 `.mp4`。

**根因**：前端拼 URL 用了 `v.name`（"README"），不是 `v.url`（"/api/video/README.mp4"）。

**修复**：改用接口返回的 `v.url`。

**教训**：接口返回什么就用什么，不要自己拼。

---

## 统计

| 类型 | 数量 |
|---|---|
| 端口/进程 | 2 |
| 前后端对接 | 3 |
| TTS 相关 | 3 |
| 模块拆分 | 1 |
| 其他 | 1 |

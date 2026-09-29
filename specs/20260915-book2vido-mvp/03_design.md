# 03 · Design（架构）

## 模块划分（pipeline）
```
extractor → scriptwriter → visualizer → narrator → compositor
   (pypdf)    (Ollama)      (Pillow+    (edge-tts/  (FFmpeg)
                                 unDraw)    say)
```
- `extractor`: 输入 → 纯文本 + 结构化分段。
- `scriptwriter`: 文本 → 口播稿（句列表）+ 每句分镜（卡类型/关键词）。
- `visualizer`: 分镜 → 信息卡 PNG 序列（行途蓝规范）。
- `narrator`: 口播稿 → 语音轨（按句切分，返回每句时长）。
- `compositor`: 卡序列 + 语音轨 → mp4（每卡时长=句时长）。

## 可插拔 provider 接口
- `LLMProvider.script(text) -> Script`：OllamaProvider / RuleFallbackProvider
- `TTSProvider.speak(text) -> (audio, duration)`：EdgeTTSProvider / SayProvider
- `VisualProvider.card(scene) -> png`：PillowProvider（默认）

## 配置
- `config.yaml`：模型名、TTS 音色、画面规范（行途蓝）、输出目录、provider 选择。
- 命令行：`python -m book2vido run --input <path> --out <mp4> [--batch <dir>]`。

## 复用
- `tools/tuitu_card_gen.py` 的 P028 视觉规范（行途蓝 #056DE8、黑白极简、无 emoji）。
- 见 `doc/` 各组件接入说明。

## 数据流（端到端）
PDF → extractor → 文本 → scriptwriter → [口播稿, 分镜] → visualizer → 卡 PNG + narrator → 语音 → compositor → mp4

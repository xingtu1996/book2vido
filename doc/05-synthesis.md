# 05 · 合成（FFmpeg）

## 角色
把「信息卡序列 + 语音轨」合成成片（mp4）。

## 选型
- **FFmpeg**（本地，免费）：图片序列按语音时长拼接 + 配音轨 + 转场。

## 接入（示意）
```bash
ffmpeg -framerate 1 -i card_%03d.png -i voice.mp3 \
  -vf "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2" \
  -c:v libx264 -c:a aac -shortest out.mp4
```
- 每卡时长 = 对应语音段时长（由 TTS 返回）。
- 竖版 1080×1920（短视频平台默认）。

## 合规
- 本地合成，零公司资源、零成本。

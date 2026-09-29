# 04 · 配音（TTS）

## 角色
把口播稿变成语音轨。

## 选型
| 方案 | 成本 | 网络 | 备注 |
|------|------|------|------|
| **edge-tts**（微软免费） | 免费匿名 | 需网 | 音质好，**非公司资源**，默认 |
| macOS `say -v Tingting` | 免费 | 断网可跑 | 完全本地，音质一般 |

## 接入
```python
import edge_tts
await edge_tts.Communicate(text, "zh-CN-YunxiNeural").save("voice.mp3")
# 或本地：subprocess.run(["say","-v","Tingting","-o","voice.aiff",text])
```
- provider 可插拔（`TTSProvider`）。断网场景自动回退 `say`。

## 合规
- edge-tts 匿名免费，非公司资源。say 完全本地。符合 `CONSTITUTION.md` 铁律一。

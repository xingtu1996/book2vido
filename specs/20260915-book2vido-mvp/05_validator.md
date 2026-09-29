# 05 · Validator（自测闭环）

## 端到端测试命令
```bash
python -m book2vido run \
  --input <工作区根>/book2vido/关键对话.pdf \
  --out <工作区根>/book2vido/samples/关键对话_sample.mp4
```

## 断言（自测通过条件）
1. `samples/关键对话_sample.mp4` 文件存在且 `ffprobe` 显示时长 > 0。
2. 成本日志打印「单条成本 ≈ ¥0（仅电费）」，且无任何公司 key / 付费 API 调用记录。
3. 抽出口播稿句数 > 0，信息卡 PNG 数 = 口播稿句数。
4. 断网（TTS 切 say）仍能产出 mp4。

## 回归
- 改任何 provider 后重跑上述命令，断言不变。
- 批量：`--batch <dir>` 对目录下所有 PDF/MD 产出 mp4。

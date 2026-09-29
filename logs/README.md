# logs/ · 运行日志

> **默认不写盘。** 需要排查时才开：`--log-file logs/xxx.log`。
> 本目录入库的只有这两个说明文件；`*.log` 一律 gitignore（见仓库根 `.gitignore`）。

## 为什么默认关闭

| 考虑 | 说明 |
|---|---|
| 磁盘 | 每次出片都留一份日志，`--all` 跑一本书 = 20+ 份，用户不会去删 |
| 隐私 | 日志里有**输入文件路径 / 章节标题** —— 不出本机这条承诺（`CONSTITUTION.md` 铁律九）不该被日志削弱 |
| 打包 | `.app` 的 `Resources/` 理论上只读，**默认写盘会在只读挂载上直接崩** |
| 收益 | 平时 stdout 已经够读；只有"复现一次疑难"时才需要落盘 |

→ 所以：**需要才开，不用常开。**

## 用法

```bash
# 出片时顺带留一份日志
python -m book2vido run --input 书.pdf --chapter 8 --out out.mp4 \
    --log-file logs/2026-09-16-ch08.log

# 断网判据（铁律九）也建议留档，事后可查
python tests/verify_offline.py --tts say --log-file logs/offline-YYYYMMDD.log
```

日志头部会自动写一行时间戳 + **完整命令行** —— 这是排查时最先要问的
「当时到底跑的是哪条命令」。成片由（输入 + 章节 + 配置 + 模型 + 提示词版本）共同决定，
少了命令行就复现不出来。

## 实现在哪

`src/book2vido/__main__.py` 的 `_Tee` —— 挂在 `sys.stdout` 上的零依赖多写流。

为什么不是 `logging` 模块：本项目全程用 `print` 输出人读的进度文本，
换 logging 要改十几个模块的调用点，换来的只是"能设 level"，而这里只有一种 level。
Tee 的好处是**调用点一个都不用动**，且默认关闭 → 对既有行为零影响。

## 不要往这里放什么

- ❌ 成片 / 中间产物 → `samples/`、`cache/`
- ❌ 崩溃栈的人肉分析 → 那是 `doc/lessons/`（错题库）的内容，日志只是**证据**
- ❌ 输入书籍 → `samples/books/`（且该书因版权不入库）

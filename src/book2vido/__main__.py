"""CLI 入口：run / outline / list / batch / fetch-icons。"""
import argparse
import json
import sys
from pathlib import Path

# ⚠️ parents[1] 与 paths.project_root() 是**两种语义**，别合并：
#    这里要的是「装着 book2vido 包的那层目录」（开发态 = <repo>/src，打包后 = .../app），
#    用于让 `import book2vido` 能解析。paths.project_root() 要的是它的上一层（项目根）。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from book2vido import cache as _cache
from book2vido import outline as _outline
from book2vido import pipeline
from book2vido import segmenter
from book2vido.config import load
from book2vido.paths import project_root

# 默认配置：项目根 config.yaml（不传 --config 也能读到 ollama/tts 设置）
DEFAULT_CONFIG = str(project_root() / "config.yaml")


class _Tee:
    """把 stdout 同时抄一份进日志文件（`--log-file`）。零依赖，**默认关闭**。

    为什么不用 `logging` 模块：本项目全程用 `print` 输出进度（给人读的 console 文本），
    换成 logging 要改十几个模块的调用点，换来的只是「能设 level」——而这里只有一种 level。
    Tee 挂在 `sys.stdout` 上，**调用点一个都不用动**，且默认不启用 → 对现有行为零影响。

    ⚠️ 必须实现 `isatty()`：某些库（含 edge-tts 的进度逻辑）会检测终端，
    不实现会让它们走进「无终端」分支。返回 False 即"按非终端处理"，与重定向行为一致。
    """

    def __init__(self, *streams):
        self._streams = streams

    def write(self, data):
        for s in self._streams:
            s.write(data)
        return len(data)

    def flush(self):
        for s in self._streams:
            if hasattr(s, "flush"):
                s.flush()

    def isatty(self):
        return False


def _open_log(path):
    """打开日志文件并写一行头部（时间戳 + 完整命令行），返回 (tee, file)。"""
    from datetime import datetime
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    f = p.open("a", encoding="utf-8")
    # 头部为什么要记命令行：排查时最先要问的就是「当时到底跑的是哪条命令」——
    # 出片结果由 (输入 + 章节 + 配置 + 模型) 共同决定，缺了命令行就没法复现。
    f.write(f"\n{'=' * 60}\n{datetime.now():%Y-%m-%d %H:%M:%S}  $ book2vido "
            f"{' '.join(sys.argv[1:])}\n{'=' * 60}\n")
    return _Tee(sys.stdout, f), f


def _cost_log(out, scenes, seconds, cache="miss"):
    print("=== book2vido 成本日志（零公司资源）===")
    print(f"输出      : {out}")
    print(f"口播句数  : {scenes}")
    print(f"耗时      : {seconds} s")
    print(f"缓存      : {cache}")
    print(f"单条成本  : ≈ ¥{round(0.03 * seconds / 3600 * 0.6, 5)}（仅电费）")


def _outline_cmd(input_path, config_path):
    """建索引并落盘（人工可改的中间产物）。"""
    cfg = load(config_path)
    doc = _outline.build(input_path)
    c = _cache.Cache(input_path, cfg, root=cfg["cache"].get("dir"),
                     enabled=bool(cfg["cache"]["enabled"]))
    p = _outline.save(doc, c.dir / "outline.json")
    print(_outline.render_tree(doc))
    print(f"\n已落盘: {p}")


def _list_cmd(input_path):
    print(_outline.render_tree(_outline.build(input_path)))


def _run_cmd(a):
    """run 分支：不传章参数 = T2V-001 兼容路径（整本一条片）。"""
    if not Path(a.input).exists():
        # 不把 FileNotFoundError 的 traceback 甩给用户：这是最常见的输错路径，
        # 一句人话比 20 行栈有用（军规 progress_visibility 的反面：报错也要可读）。
        print(f"🔴 输入文件不存在：{a.input}")
        return 2
    cfg = load(a.config)
    if a.jobs:
        cfg["concurrency"]["tts_workers"] = a.jobs
    if a.cache_dir:
        cfg["cache"]["dir"] = a.cache_dir
    think = False if a.fast else None

    # ⚠️ 判定必须用 `is not None`，**不能用 truthiness**：`--chapter 0` 会被判成"没给章参数"
    # 而静默走整本出片的老路径（退出码 0，用户拿到一条完全不对的片子却毫无提示）。
    # 这是本项目最忌讳的"静默走错分支"，故显式区分「没给」与「给了 0」。
    if a.chapter is None and a.chapters is None and not a.all:
        r = pipeline.run(a.input, a.out, a.config, think=think)
        _cost_log(r["out"], r["scenes"], r["seconds"], r.get("cache", "off"))
        return 0

    if a.chapter is not None:
        idx = [a.chapter]
    elif a.chapters is not None:
        try:
            idx = [int(x) for x in a.chapters.split(",") if x.strip()]
        except ValueError:
            print("🔴 --chapters 需为逗号分隔的整数，如 --chapters 1,3,5")
            return 2
        if not idx:
            print("🔴 --chapters 为空，未指定任何章（要全部请用 --all）")
            return 2
    else:
        idx = None      # --all

    # 单章 + --out 以 .mp4 结尾 → 直接写那个文件；多章/--all → --out 视为目录
    single = bool(idx) and len(idx) == 1 and Path(a.out).suffix.lower() == ".mp4"
    r = pipeline.run_book(a.input, a.out, cfg, indices=idx, single_file=single,
                          no_cache=a.no_cache, think=think)
    for x in r["ok"]:
        _cost_log(x["out"], x["scenes"], x["seconds"], x.get("cache", "miss"))
    # 「跳过」排在「失败」之前：前者是正常判断（料不够），后者才是要查的意外。
    # 两者分开报——混在一起会让用户以为工具坏了（`segmenter.InsufficientMaterial`）。
    if r["skipped"]:
        print(f"\n⊘ 跳过 {len(r['skipped'])} 章（料不足以支撑口播，非故障）：")
        # 这里只打**裸原因**：章节号/标题已在本行，再拼一次会变成
        # 「第 22 章「X」：第 22 章「X」可用文本仅…」（异常见 segmenter.InsufficientMaterial）。
        for s in r["skipped"]:
            print(f"   · [{s['chapter']}] {s['title']} —— {s['reason']}")
    if r["failed"]:
        print(f"\n🔴 失败 {len(r['failed'])} 章：")
        for f in r["failed"]:
            print(f"   · 第 {f['chapter']} 章「{f['title']}」：{f['error']}")

    if not r["ok"]:
        # 一条都没出（全跳过或全失败）→ 非 0：调用方要能判断「没拿到东西」。
        # 单章被跳过也走这里（用户要的那条片不存在，脚本不该以为成功）。
        print(f"\n🔴 未产出任何成片（跳过 {len(r['skipped'])} / 失败 {len(r['failed'])}）"
              f" ｜ 耗时 {r['seconds']} s")
        return 1
    parts = [f"出片 {len(r['ok'])} 章"]
    if r["skipped"]:
        parts.append(f"跳过 {len(r['skipped'])} 章")
    if r["failed"]:
        parts.append(f"失败 {len(r['failed'])} 章")
    print(f"\n✅ 完成：{' ｜ '.join(parts)} ｜ 累计 {r['seconds']} s ｜ ≈ ¥{r['cost']}（仅电费）")
    return 1 if r["failed"] else 0


def _batch(batch_dir, out_path, config_path, fast=False):
    out_root = Path(out_path or "samples")
    out_root.mkdir(exist_ok=True, parents=True)
    for p in sorted(Path(batch_dir).iterdir()):
        if p.suffix.lower() in (".pdf", ".md", ".txt"):
            try:
                r = pipeline.run(str(p), str(out_root / f"{p.stem}.mp4"), config_path,
                                 think=(False if fast else None))
            except segmenter.InsufficientMaterial as e:
                # 批量里一条短料不该拖垮整批：记一行、继续下一条。
                # 静默跳过是禁止的（军规 progress_visibility），所以仍然打出来。
                print(f"⊘ 跳过 {p.name}（料不足以支撑口播，非故障）：{e}")
                continue
            print(json.dumps({k: v for k, v in r.items() if k != "out"}, ensure_ascii=False))


def _fetch_icons(config_path):
    """预热图标缓存（联网一次），之后完全离线可用。"""
    from book2vido import icons as _icons
    cache = project_root() / "assets" / "icons"
    ids = sorted(set(_icons.KEYWORD_ICONS.values()) | set(_icons.FALLBACK_ICONS))
    print(f"预热 {len(ids)} 个图标 → {cache}")
    r = _icons.prefetch(ids, cache)
    ok = sum(1 for v in r.values() if v == "ok")
    print(f"完成：{ok}/{len(ids)} 成功（失败项将自动降级为无图标版式）")


def main():
    ap = argparse.ArgumentParser(prog="book2vido", description="文本→视频 零成本流水线")

    # 公共参数：用 argparse 的 `parents` 机制挂到每个子命令上，
    # 这样 `--log-file` 可以写在子命令之后（`book2vido run ... --log-file logs/x.log`），
    # 而不是被迫写在子命令之前 —— 后者反直觉，且和已有参数习惯不一致。
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--log-file",
                        help="把全部输出同时抄进该日志文件（默认不写盘；建议 logs/xxx.log）")

    sub = ap.add_subparsers(dest="cmd")

    # ── outline / list：目录索引（零 LLM，秒出）
    ol = sub.add_parser("outline", parents=[common], help="建目录索引并落盘 outline.json")
    ol.add_argument("input", help="输入 PDF/MD/长文 路径")
    ol.add_argument("--config", default=DEFAULT_CONFIG, help="config.yaml 路径")

    ls = sub.add_parser("list", parents=[common], help="打印章节树")
    ls.add_argument("input", help="输入 PDF/MD/长文 路径")

    # ── run：不带章参数 = 整本一条片（与旧版一致）
    run_p = sub.add_parser("run", parents=[common], help="转视频（可指定章节）")
    run_p.add_argument("--input", required=True, help="输入 PDF/MD/长文 路径")
    run_p.add_argument("--out", required=True, help="输出 mp4 路径；多章/--all 时视为目录")
    run_p.add_argument("--config", default=DEFAULT_CONFIG, help="config.yaml 路径")
    run_p.add_argument("--fast", action="store_true",
                       help="关闭模型思考模式（快约 2 倍，句子质量下降，适合批量初筛）")
    run_p.add_argument("--chapter", type=int, help="只生成第 N 章（1-based 顶层章序号）")
    run_p.add_argument("--chapters", help="多章，逗号分隔，如 1,3,5")
    run_p.add_argument("--all", action="store_true", help="全部顶层章（--out 视为目录）")
    run_p.add_argument("--jobs", type=int, help="TTS 并发度（默认取 config；只影响 TTS，不影响模型）")
    run_p.add_argument("--no-cache", action="store_true", help="关闭缓存，每次全新生成")
    run_p.add_argument("--cache-dir", help="缓存根目录（默认 <项目根>/cache）")

    bat_p = sub.add_parser("batch", parents=[common], help="批量目录转视频")
    bat_p.add_argument("--batch", required=True, help="输入目录（PDF/MD/TXT）")
    bat_p.add_argument("--out", default="samples", help="输出目录")
    bat_p.add_argument("--config", default=DEFAULT_CONFIG, help="config.yaml 路径")
    bat_p.add_argument("--fast", action="store_true", help="关闭思考模式（快约 2 倍）")

    sub.add_parser("fetch-icons", help="预热关键词图标缓存（联网一次，之后离线可用）")

    a = ap.parse_args()

    # ── 日志落盘（可选）：挂上 Tee 后所有 print 同时进文件，调用点无需改动。
    #    `fetch-icons` 子命令没有 --log-file（它只打印两行，没排查价值），故用 getattr 兜底。
    _logf, _orig_stdout = None, sys.stdout
    if getattr(a, "log_file", None):
        sys.stdout, _logf = _open_log(a.log_file)
    try:
        if a.cmd == "run":
            return _run_cmd(a)
        if a.cmd == "outline":
            _outline_cmd(a.input, a.config)
        elif a.cmd == "list":
            _list_cmd(a.input)
        elif a.cmd == "batch":
            _batch(a.batch, a.out, a.config, getattr(a, "fast", False))
        elif a.cmd == "fetch-icons":
            _fetch_icons(DEFAULT_CONFIG)
        else:
            ap.print_help()
        return 0
    finally:
        # 必须关：不关的话最后一段还在缓冲区里，日志会少尾巴（最难查的那种"日志不完整"）。
        if _logf:
            _logf.flush()
            _logf.close()
            sys.stdout = _orig_stdout


if __name__ == "__main__":
    sys.exit(main())

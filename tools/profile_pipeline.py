#!/usr/bin/env python3
"""端到端耗时剖析：把「出一条片」拆成环节并逐段计时。

为什么要有这个脚本：
    谈「极致效率」之前必须先有基线。doc/23 的架构评审全部结论都建立在
    「哪一环真的慢」之上——靠猜会优化错地方（本仓库已踩过：给 Ollama 加并发，
    实测只省 5%，是噪声；真正的收益在 TTS 并发 13x）。

设计：
    - 复跑真实链路（extractor → outline → segmenter → LLM 分镜 → 画面 → TTS → 合成）
    - **强制 no_cache**，否则命中缓存会测出 0.1s 的假象
    - 只计时，不改任何环节行为；产物写 /tmp，不污染仓库

用法：
    python tools/profile_pipeline.py --pdf <路径> [--chapter 3] [--runs 1]
输出：
    终端分段表 + /tmp/t2v_profile.json
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from book2vido import (  # noqa: E402
    cache as cache_mod,
    compositor,
    extractor,
    narrator,
    outline,
    providers,
    segmenter,
)
from book2vido.config import load  # noqa: E402
from book2vido.models import Chapter, MediaClip, ScriptDoc, now_stamp  # noqa: E402


class T:
    """分段计时器：with T() as t 用法，或直接 t.mark('名字')。"""

    def __init__(self):
        self.rows: list[dict] = []
        self._last = time.time()

    def mark(self, name: str, note: str = "") -> None:
        now = time.time()
        self.rows.append({"stage": name, "sec": round(now - self._last, 2), "note": note})
        self._last = now


def profile(pdf: str, chapter: int, cfg: dict, work_root: Path) -> dict:
    t = T()
    work = work_root / f"ch{chapter:02d}"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)

    # ── 1 抽页（全书）
    pages = extractor.extract_pages(pdf)
    t.mark("1·PDF 抽页", f"{len(pages)} 页")

    # ── 2 目录解析
    doc = outline.build(pdf)
    t.mark("2·目录解析", f"{len(doc.top())} 章")

    ch = doc.by_index(chapter)
    if ch is None:
        raise SystemExit(f"章号 {chapter} 越界（本书 {len(doc.top())} 章）")

    # ── 3 切片
    text = segmenter.slice_chapter(pages, ch, cfg["limits"]["max_chars"])
    t.mark("3·章节切片", f"{len(text)} 字")

    # ── 4 分镜（LLM，最贵）
    stage = providers.build(cfg, None)
    scenes = stage.llm.script(text, cfg["limits"]["max_sentences"])
    t.mark("4·LLM 分镜", f"{len(scenes)} 句 / think={cfg['llm']['think']}")

    sdoc = ScriptDoc(ch.index, ch.title, scenes, cfg["llm"]["model"],
                     bool(cfg["llm"]["think"]), now_stamp())

    # ── 5 画面渲染
    images = [stage.viz.card(s, i + 1, work) for i, s in enumerate(scenes)]
    t.mark("5·画面渲染", f"{len(images)} 张卡")

    # ── 6 配音
    items = [(i + 1, s.text, str(work / f"voice_{i + 1}.mp3"))
             for i, s in enumerate(scenes)]
    durs = stage.tts.speak_many(items, max_workers=cfg["concurrency"]["tts_workers"])
    t.mark("6·TTS 配音", f"{len(items)} 句 / workers={cfg['concurrency']['tts_workers']}")

    # ── 7 合成
    out = work_root / f"profile_ch{chapter:02d}.mp4"
    clips = [MediaClip(i + 1, images[i], items[i][2], durs[i + 1])
             for i in range(len(items))]
    compositor.compose(clips, str(out), str(work))
    t.mark("7·FFmpeg 合成", f"{out.stat().st_size // 1024} KB" if out.exists() else "缺失")

    total = round(sum(r["sec"] for r in t.rows), 2)
    return {"chapter": chapter, "title": ch.title, "rows": t.rows, "total": total,
            "out": str(out), "scenes": len(scenes)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--chapter", type=int, default=3)
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--fast", action="store_true", help="think=false，测速度下限")
    ap.add_argument("--config", default=None,
                    help="config.yaml 路径。**默认不传 = 用 config.py 的 DEFAULT"
                         "（provider=rule）**，那测出来的是降级耗时，不是模型耗时。"
                         "要测真实链路必须显式指向项目根 config.yaml。")
    a = ap.parse_args()

    cfg = load(a.config)
    if a.fast:
        cfg["llm"]["think"] = False
    # 强制关缓存：命中缓存会把 LLM 分镜测成 0s，基线就废了
    cfg["cache"]["enabled"] = False

    work_root = Path("/tmp/t2v_profile")
    if work_root.exists():
        shutil.rmtree(work_root)
    work_root.mkdir(parents=True)

    results = []
    for i in range(1, a.runs + 1):
        print(f"\n=== run {i}/{a.runs} ===")
        r = profile(a.pdf, a.chapter, cfg, work_root / f"r{i}")
        results.append(r)
        for row in r["rows"]:
            pct = row["sec"] / r["total"] * 100 if r["total"] else 0
            bar = "█" * int(pct / 2.5)
            print(f"  {row['stage']:<16} {row['sec']:>7.2f}s  {pct:>5.1f}%  {bar:<20} {row['note']}")
        print(f"  {'合计':<16} {r['total']:>7.2f}s")

    (Path("/tmp/t2v_profile.json")).write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n明细 → /tmp/t2v_profile.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

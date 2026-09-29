#!/usr/bin/env python3
"""模型对照：同一份素材，两个模型各出一版口播稿，摆在一起让人读。

为什么需要它（补 models/README §三「换模型五步」的第 ③④ 步）
──────────────────────────────────────────────────────────
基准（bench_ollama.py）只回答「模型本身多快」，但换模型的**真实决策点**是：
    「同一份素材，小模型出的句子能不能用？」
这件事 **没有自动化替代 —— 通顺与否是人的判断**（models/README §三 步骤 ④）。
本工具不替人判断，它只把「该读的东西」摆到一张表里：耗时 / 句数 / 句长 / 概念命中，
再把两版句子**逐句对齐打印**，让一次肉眼扫描就能下结论。

它同时治一个具体的坑：换模型后**只读 meta（句数/耗时）就拍板**，
句数到了 12 句、耗时降了 4 倍，看起来赢麻了 —— 但句子可能是碎的。
把句子原文打印出来，就是为了让「看起来对了」挨一次检查（错题库 L-22 同族）。

用法：
    export PYTHONPATH=src
    python tools/bench_model_compare.py --input samples/xxx.md --models qwen3:8b,qwen3:0.6b
    python tools/bench_model_compare.py --input samples/xxx.md --models qwen3:8b,qwen3:0.6b --think false
"""
from __future__ import annotations

import argparse
import pathlib
import statistics
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from book2vido.scriptwriter import OllamaProvider  # noqa: E402


def read_text(path: pathlib.Path, max_chars: int) -> tuple[str, bool]:
    """取送入模型的文本。

    ⚠️ 口径声明：本工具**不复制** `segmenter.slice_chapter` 的「首/中/尾均匀采样」逻辑
    （不制造第二个实现 —— 见错题库 L-18）。这里只做简单截断，
    并在超长时明确标注「已按前 N 字截断，与生产链路的采样口径不同」。
    对照场景下两版用的是**同一份文本**，所以差异仍只来自模型——这才是本工具要守的变量。
    """
    raw = path.read_text(encoding="utf-8")
    if len(raw) <= max_chars:
        return raw, False
    return raw[:max_chars], True


def run_one(model: str, text: str, think: bool, base_url: str) -> dict:
    p = OllamaProvider(model=model, base_url=base_url, think=think)
    t0 = time.time()
    doc = p.script(text)
    elapsed = time.time() - t0
    scenes = doc.scenes if hasattr(doc, "scenes") else doc
    lens = [len(s.text) for s in scenes]
    return {
        "model": model,
        "sec": round(elapsed, 1),
        "n": len(scenes),
        "avg_len": round(statistics.mean(lens), 1) if lens else 0,
        "max_len": max(lens) if lens else 0,
        "scenes": [s.text for s in scenes],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="同素材两模型口播稿对照")
    ap.add_argument("--input", required=True)
    ap.add_argument("--models", default="qwen3:8b,qwen3:0.6b")
    ap.add_argument("--think", default="true", choices=["true", "false"])
    ap.add_argument("--max-chars", type=int, default=2500)
    ap.add_argument("--base-url", default="http://localhost:11434")
    args = ap.parse_args()

    path = pathlib.Path(args.input)
    if not path.exists():
        print(f"✗ 素材不存在：{path}")
        return 1

    text, truncated = read_text(path, args.max_chars)
    think = args.think == "true"
    print(f"素材：{path.name}（送入 {len(text)} 字）· think={think}")
    if truncated:
        print("  ⚠️ 超长已按前 N 字截断（与生产链路的「首/中/尾采样」口径不同，对照时两版同源，不影响结论）")

    results = []
    for model in [m.strip() for m in args.models.split(",") if m.strip()]:
        print(f"  … {model} 生成中", flush=True)
        try:
            results.append(run_one(model, text, think, args.base_url))
        except Exception as exc:
            print(f"  ✗ {model} 失败：{exc}")
            return 1

    # ── 量化对照 ──
    print("\n【量化】")
    print(f"  {'模型':<14}{'耗时':>8}{'句数':>6}{'均句长':>8}{'最长句':>8}")
    for r in results:
        print(f"  {r['model']:<14}{r['sec']:>7.1f}s{r['n']:>6}{r['avg_len']:>8}{r['max_len']:>8}")
    if len(results) == 2:
        a, b = results
        print(f"\n  耗时比：{a['model']} / {b['model']} = {a['sec']/b['sec']:.2f}x"
              f"（即小模型快 {a['sec']/b['sec']:.1f} 倍）")

    # ── 逐句原文：这一步是给人读的，机器不该替人判断 ──
    print("\n【逐句原文 —— 通顺与否请你自己读】\n")
    max_n = max(len(r["scenes"]) for r in results)
    for i in range(max_n):
        print(f"  ── 第 {i+1} 句 ──")
        for r in results:
            s = r["scenes"][i] if i < len(r["scenes"]) else "（无）"
            print(f"    {r['model']:<12} {s}")
        print()

    print("判据建议：①句长是否稳定（忽长忽短＝断句失控）"
          "②是否有半截句/同义反复 ③专有名词有没有写错"
          "④读完能否知道原文在说什么。四项都要过，别只看耗时。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

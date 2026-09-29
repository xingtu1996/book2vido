#!/usr/bin/env python3
"""qwen3:8b 本地性能基准 — 冷启动 / 首字延迟 / 预填充 / 解码速率 / 思考开销。

只读本地 Ollama，不调用任何云端资源（守 book2vido 铁律①）。

用法：
    python tools/bench_ollama.py                      # 全部用例
    python tools/bench_ollama.py --model qwen3:8b
输出：
    终端表格 + /tmp/ollama_bench.json
"""
from __future__ import annotations

import argparse
from pathlib import Path
import json
import subprocess
import time
import urllib.request

API = "http://localhost:11434/api/generate"


def _ps() -> str:
    try:
        out = subprocess.run(["ollama", "ps"], capture_output=True, text=True, timeout=10).stdout
        lines = [l for l in out.splitlines() if l.strip()]
        return " | ".join(lines[-1].split()) if len(lines) > 1 else "(模型未常驻)"
    except Exception:
        return "(ps 失败)"


def run_case(name, prompt, model, think=None, num_predict=None, timeout=900) -> dict:
    payload: dict = {"model": model, "prompt": prompt, "stream": True}
    if think is not None:
        payload["think"] = think
    if num_predict:
        payload["options"] = {"num_predict": num_predict}

    req = urllib.request.Request(API, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    ttft, final = None, None
    out_text, thinking = [], []

    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            for line in r:
                if not line.strip():
                    continue
                d = json.loads(line)
                if d.get("response"):
                    if ttft is None:
                        ttft = time.perf_counter() - t0
                    out_text.append(d["response"])
                if d.get("thinking"):
                    thinking.append(d["thinking"])
                if d.get("done"):
                    final = d
    except Exception as e:  # noqa: BLE001
        return {"case": name, "error": str(e)}

    wall = time.perf_counter() - t0
    f = final or {}
    ns = 1e9
    pe_c, pe_d = f.get("prompt_eval_count", 0), f.get("prompt_eval_duration", 0)
    ev_c, ev_d = f.get("eval_count", 0), f.get("eval_duration", 0)
    return {
        "case": name,
        "wall_s": round(wall, 2),
        "ttft_s": round(ttft, 2) if ttft else None,
        "load_s": round(f.get("load_duration", 0) / ns, 2),
        "prefill_tok": pe_c,
        "prefill_tps": round(pe_c / (pe_d / ns), 1) if pe_d else None,
        "decode_tok": ev_c,
        "decode_tps": round(ev_c / (ev_d / ns), 1) if ev_d else None,
        "out_chars": len("".join(out_text)),
        "think_chars": len("".join(thinking)),
        "mem": _ps(),
        "text": "".join(out_text)[:400],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen3:8b")
    ap.add_argument("--card",
                    default=str(Path.home() / "xingtu" / "素材库"
                                / "素材卡_省Token实战包装_prompt_skill_config三层聚合_2026-09-06.md"),
                    help="压测用的长文本素材卡（默认取本机行途素材库）")
    a = ap.parse_args()

    # 真实任务：复用 book2vido 的 scriptwriter 提示词
    try:
        chunk = open(a.card, encoding="utf-8").read()[:2500]
    except Exception:
        chunk = "关键对话指那些观点分歧、情绪激烈、结果重大的高风险对话。"
    TASK_PROMPT = (
        "你是一个把书/长文压成口播短视频脚本的助手。\n"
        "请从下面【正文】提炼最多 12 句口语化、能独立听懂的短句，"
        "每句严格 ≤20 字（像朋友聊天，不要书面长句），并给每句一个 2-4 字关键词。\n"
        '只输出一个 JSON 数组，形如 [{"text":"...","keyword":"..."}]，不要任何其他文字。\n\n'
        "正文：\n" + chunk
    )
    CHAT_PROMPT = "用三句话解释什么是大模型的上下文窗口，口语化，像跟朋友聊天。"
    LONG_PROMPT = "写一段 200 字左右的短文，主题：为什么本地小模型适合做内容初筛。"

    cases = [
        ("① 冷启动+短问答(不思考)", CHAT_PROMPT, False, None),
        ("② 暖机短问答(不思考)", CHAT_PROMPT, False, None),
        ("③ 短问答(开思考)", CHAT_PROMPT, True, None),
        ("④ 真实任务·口播稿(不思考)", TASK_PROMPT, False, None),
        ("⑤ 真实任务·口播稿(开思考)", TASK_PROMPT, True, None),
        ("⑥ 长文 200 字(不思考)", LONG_PROMPT, False, None),
    ]

    results = []
    for name, p, think, npred in cases:
        print(f"\n▶ {name} ...", flush=True)
        r = run_case(name, p, a.model, think=think, num_predict=npred)
        results.append(r)
        if "error" in r:
            print(f"   ❌ {r['error']}")
        else:
            print(f"   总耗时 {r['wall_s']}s | 首字 {r['ttft_s']}s | 加载 {r['load_s']}s"
                  f" | 预填充 {r['prefill_tok']}tok@{r['prefill_tps']}t/s"
                  f" | 解码 {r['decode_tok']}tok@{r['decode_tps']}t/s"
                  f" | 思考{r['think_chars']}字")

    print("\n" + "=" * 100)
    hdr = f"{'用例':<26}{'总耗时':>8}{'首字':>7}{'加载':>7}{'预填充':>12}{'解码速率':>11}{'输出':>7}{'思考':>7}"
    print(hdr)
    print("-" * 100)
    for r in results:
        if "error" in r:
            print(f"{r['case']:<26}{'ERROR':>8}  {r['error'][:50]}")
            continue
        print(f"{r['case']:<26}{r['wall_s']:>8}{r['ttft_s'] or 0:>7}{r['load_s']:>7}"
              f"{str(r['prefill_tok']) + '@' + str(r['prefill_tps']):>12}"
              f"{str(r['decode_tps']):>11}{r['out_chars']:>7}{r['think_chars']:>7}")
    print("=" * 100)

    with open("/tmp/ollama_bench.json", "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)
    print("明细已写 /tmp/ollama_bench.json")


if __name__ == "__main__":
    main()

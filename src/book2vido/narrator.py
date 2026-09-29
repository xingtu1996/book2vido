"""配音（TTS）。edge-tts（免费匿名，需网）| say（完全本地，断网可跑）。零公司资源。"""
from __future__ import annotations

import asyncio
import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from . import binpaths


def _duration(p: str) -> float:
    try:
        out = subprocess.check_output(
            [binpaths.ffprobe(), "-v", "error", "-show_entries", "format=duration", "-of", "json", p]
        )
        return float(json.loads(out)["format"]["duration"])
    except Exception:
        return 3.0


class TTSProvider:
    def speak(self, text: str, out_path: str) -> float:
        raise NotImplementedError

    def speak_many(self, items: list[tuple[int, str, str]], max_workers: int = 12,
                   on_progress: Callable[[int, int], None] | None = None) -> dict[int, float]:
        """items = [(index, text, out_path)] → {index: duration}。

        并发是 TTS 自己的事（不该由 pipeline 拼线程池）：TTS 是纯网络 IO 等待，
        实测 12 句并发 2.2s vs 串行 28.9s（13x 加速），这是整条链路最大的白捡收益。
        带重试与自适应降并发，绝不静默产出 0 字节音频或丢条。
        """
        if not items:
            return {}
        total = len(items)
        # pending 里的第 4 项是「剩余重试额度」：初始 2 次重试 = 最多 3 次尝试。
        # 把重试额度放进队列而不是在 speak 里埋递归，是因为降并发要对「整批失败项」生效。
        pending = [(idx, text, out, 2) for idx, text, out in items]
        results: dict[int, float] = {}
        errors: dict[int, Exception] = {}
        workers = max(1, max_workers)

        while pending:
            ran = len(pending)
            failed: list[tuple[int, str, str, int]] = []
            with ThreadPoolExecutor(max_workers=min(workers, ran)) as ex:
                futs = {ex.submit(self.speak, text, out): (idx, text, out, rt)
                        for idx, text, out, rt in pending}
                for fut in as_completed(futs):
                    idx, text, out, rt = futs[fut]
                    try:
                        results[idx] = fut.result()
                    except Exception as e:
                        # 记最后一条异常：最终抛错时要把「失败 index + 原因」交代清楚，
                        # 不然上层 pipeline 回退 SayProvider 时无从判断是限流还是坏文本。
                        errors[idx] = e
                        failed.append((idx, text, out, rt))
                    # 进度报「已成功条数」而不是尝试次数：重试轮会让尝试次数超过总数，
                    # 进度条会显示 15/12 这种越界值（实测第一版就踩了）。
                    if on_progress:
                        on_progress(len(results), total)

            if not failed:
                break

            # 为什么失败率 > 50% 要降并发而不是硬重试：免费 TTS 被限流时，
            # 硬重试只会用同样高的并发加剧限流（实测 6 线程偶发限流、12 线程更凶）。
            # 减半并发让请求错峰，往往能整体跑通；每减半一档都打印，便于事后审计。
            # ran>1 才降：单条重试轮（1 项 100% 失败）降并发无意义，只会产生误导日志。
            if ran > 1 and len(failed) / ran > 0.5:
                workers = max(1, workers // 2)
                print(f"[speak_many] 本轮失败率 {len(failed) / ran:.0%} > 50%，"
                      f"降到 {workers} 线程重跑失败项")

            # 还有重试额度的失败项进下一轮（额度 -1）；额度耗尽的留待最终抛错。
            # 0.3s 退避不是忙等：给限流端点一点喘息，否则瞬时重发等于又打了一波洪峰。
            next_pending: list[tuple[int, str, str, int]] = []
            for idx, text, out, rt in failed:
                if rt > 0:
                    time.sleep(0.3)
                    next_pending.append((idx, text, out, rt - 1))
            pending = next_pending
            if not pending:
                break

        # 最终仍有失败：绝不静默返回不完整结果。上层 pipeline 捕获后回退 SayProvider。
        if len(results) != total:
            failed_idx = sorted(set(i[0] for i in items) - results.keys())
            last = "; ".join(f"#{i}: {type(errors[i]).__name__}: {errors[i]}"
                             for i in failed_idx)
            raise RuntimeError(
                f"speak_many 最终仍失败 {len(failed_idx)}/{total} 条，index={failed_idx}。"
                f"最后异常：{last}")
        return results


class EdgeTTSProvider(TTSProvider):
    def __init__(self, voice: str = "zh-CN-YunxiNeural", timeout: float = 45.0):
        self.voice = voice
        self.timeout = timeout

    def speak(self, text: str, out_path: str) -> float:
        import edge_tts

        async def _run():
            comm = edge_tts.Communicate(text, self.voice)
            # 超时保护：edge-tts 在断网/被限流时会**静默 hang**（不抛错、不返回），
            # 是 run2 卡死 20+ 分钟的疑似成因（HANDOFF §5.8）。
            # 抛 TimeoutError 后由 pipeline 捕获并回退 SayProvider，不阻塞出片。
            await asyncio.wait_for(comm.save(out_path), timeout=self.timeout)

        asyncio.run(_run())
        p = Path(out_path)
        if not p.exists() or p.stat().st_size == 0:
            raise RuntimeError(f"TTS 输出为空（{out_path}）——edge-tts 未产出音频")
        return _duration(out_path)


class SayProvider(TTSProvider):
    def __init__(self, voice: str = "Sandy"):
        self.voice = voice

    def speak(self, text: str, out_path: str) -> float:
        aiff = str(out_path).replace(".mp3", ".aiff")
        # 自动用中文变体：英文音色名加"中文（中国大陆）"
        voice_arg = self.voice
        if "(" not in voice_arg:
            voice_arg = f"{self.voice} (中文（中国大陆）)"
        subprocess.run(["say", "-v", voice_arg, "-o", aiff, text], check=True)
        subprocess.run(
            [binpaths.ffmpeg(), "-nostdin", "-y", "-i", aiff, out_path],
            check=True,
        )
        # 非空校验：0 字节 mp3 会让后续 concat 崩在很远的地方，宁可当场报错
        p = Path(out_path)
        if not p.exists() or p.stat().st_size == 0:
            raise RuntimeError(f"TTS 输出为空（{out_path}）——say→ffmpeg 转换未产出音频")
        return _duration(out_path)

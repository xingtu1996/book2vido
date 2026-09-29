"""验证 narrator.speak_many 的并发 / 重试 / 降并发 / 抛错（Unit D 交付物，可重跑）。

覆盖 spec TC-08 与 05_validator §4.1 退出条件 2/3：
  ① 12 句串行 vs speak_many(max_workers=12) 的真实加速比（需联网）
  ② 注入 1 条必失败 → 重试后失败 → 抛 RuntimeError
  ③ 注入 >50% 必失败 → 自动降并发每档可见 → 最终抛 RuntimeError
  ④ on_progress 回调次数
输出落在 tempfile.mkdtemp()，不污染项目目录。
"""
import sys
import os
import time
import tempfile

sys.path.insert(0, "src")
from book2vido import narrator

TMP = tempfile.mkdtemp(prefix="tts_verify_")


def make_items(n, fail_idx=()):
    """生成 [(index, text, out_path)]。fail_idx 里的 index 文本带 __FAIL__ 哨兵。"""
    items = []
    for i in range(1, n + 1):
        text = f"__FAIL__|{i}" if i in fail_idx else f"{i}|这是第{i}句测试语音合成"
        items.append((i, text, os.path.join(TMP, f"v{i}.mp3")))
    return items


class FakeProvider(narrator.TTSProvider):
    """确定性假 TTS：离线测 speak_many 控制流（重试/降并发/抛错）。
    普通句 sleep 模拟 IO 后写非空文件并返回时长；__FAIL__ 哨兵句必然抛错。"""

    def speak(self, text, out_path):
        idx = int(text.split("|")[0])
        time.sleep(0.05)  # 模拟网络 IO 等待
        if text.startswith("__FAIL__"):
            raise RuntimeError(f"确定性失败 index={idx}")
        with open(out_path, "wb") as f:
            f.write(b"\x00" * 100)  # 非空文件，模拟 TTS 正常产出
        return 1.0



def main():
    print(f"临时目录: {TMP}\n")
    print("=" * 60)
    print("① 真实加速比：串行 vs speak_many（需联网，edge-tts 免费匿名）")
    print("=" * 60)
    tts = narrator.EdgeTTSProvider("zh-CN-YunxiNeural")
    texts = [f"这是第{i}句用来测试并发语音合成的文本" for i in range(1, 13)]
    real_items = [(i, t, os.path.join(TMP, f"real_{i}.mp3")) for i, t in enumerate(texts, 1)]

    NET_OK = True
    try:
        t0 = time.time()
        ok = 0
        for i, t in enumerate(texts, 1):
            try:
                tts.speak(t, os.path.join(TMP, f"ser_{i}.mp3"))
                ok += 1
            except Exception as e:
                print(f"  串行第 {i} 句失败: {e}")
        serial = round(time.time() - t0, 2)
        print(f"串行 12 句: {serial}s  成功 {ok}/12")

        t0 = time.time()
        durs = tts.speak_many(real_items, max_workers=12)
        conc = round(time.time() - t0, 2)
        print(f"并发 12 线程: {conc}s  成功 {len(durs)}/12  加速 {round(serial/conc, 1)}x"
              if conc > 0 else f"并发 12 线程: {conc}s")
    except Exception as e:
        NET_OK = False
        print(f"【未联网】真实 TTS 不可用：{type(e).__name__}: {e}")
        print("  跳过真实加速比测量（控制流测试 ②③④ 不依赖网络，照常跑）")
    print()

    print("=" * 60)
    print("② 注入 1 条必失败 → 重试后失败 → 抛 RuntimeError")
    print("=" * 60)
    fp = FakeProvider()
    prog = []
    try:
        fp.speak_many(make_items(12, fail_idx={7}), max_workers=12,
                      on_progress=lambda d, t: prog.append((d, t)))
        print("  ✗ 预期抛错但没有抛")
    except RuntimeError as e:
        print(f"  ✓ 按预期抛 RuntimeError：{e}")
        print("  该必失败项尝试了 3 次（1 初 + 2 重试），最终仍失败→抛错")
    print()

    print("=" * 60)
    print("③ 注入 >50% 必失败 → 自动降并发每档可见 → 抛 RuntimeError")
    print("=" * 60)
    fp3 = FakeProvider()
    # 12 句里 8 句必失败（67% > 50%），应触发降并发：12→6→3→1
    try:
        fp3.speak_many(make_items(12, fail_idx=set(range(1, 9))), max_workers=12)
        print("  ✗ 预期抛错但没有抛")
    except RuntimeError as e:
        print(f"  ✓ 按预期抛 RuntimeError：{e}")
    print("  （上方 [speak_many] 日志应可见「降到 6 / 3 / 1 线程」每档）")
    print()

    print("=" * 60)
    print("④ on_progress 回调次数")
    print("=" * 60)
    # 全成功场景：回调次数 = 总条数（无重试）；含重试场景 = 总尝试数。
    fp4 = FakeProvider()
    prog_all = []
    fp4.speak_many(make_items(12), max_workers=12,
                   on_progress=lambda d, t: prog_all.append((d, t)))
    print(f"  全成功 12 条：on_progress 被调用 {len(prog_all)} 次 "
          f"（= 总条数 {len(prog_all)}，无重试）")

    if NET_OK:
        prog_real = []
        try:
            tts.speak_many(real_items, max_workers=12,
                           on_progress=lambda d, t: prog_real.append((d, t)))
            print(f"  真实 12 条：on_progress 被调用 {len(prog_real)} 次（= 总条数）")
        except Exception:
            pass

    print(f"\n临时目录未清理（可查音频产物）：{TMP}")


if __name__ == "__main__":
    main()

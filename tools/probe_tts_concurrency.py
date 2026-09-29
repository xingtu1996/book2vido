"""验证 TTS 并发：纯网络 IO 等待，线程池应该有效。同时看免费服务的限流风险。"""
import time, sys, os
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, "src")
from book2vido import narrator

os.makedirs("/tmp/ttsprobe", exist_ok=True)
tts = narrator.EdgeTTSProvider("zh-CN-YunxiNeural")
texts = [f"这是第{i}句用来测试并发语音合成的文本" for i in range(1, 13)]

t0 = time.time()
ok = 0
for i, t in enumerate(texts):
    try:
        tts.speak(t, f"/tmp/ttsprobe/s{i}.mp3"); ok += 1
    except Exception:
        pass
serial = round(time.time() - t0, 1)
print(f"串行 12 句: {serial}s  成功 {ok}/12")

for workers in (6, 12):
    t0 = time.time()
    res = {"ok": 0, "fail": 0}
    def job(a):
        i, t = a
        try:
            tts.speak(t, f"/tmp/ttsprobe/c{workers}_{i}.mp3")
            return True
        except Exception:
            return False
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for r in ex.map(job, list(enumerate(texts))):
            res["ok" if r else "fail"] += 1
    conc = round(time.time() - t0, 1)
    print(f"并发 {workers:>2} 线程: {conc}s  成功 {res['ok']}/12 失败 {res['fail']}  → 加速 {round(serial/conc, 1)}x")

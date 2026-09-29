"""耗时分解探针：找出真正的瓶颈，判断哪些环节值得并行。"""
import time, json, urllib.request, threading, os, sys
sys.path.insert(0, "src")

print("=" * 60)
print("A · Ollama 并发是否有效")
print("=" * 60)

def ask(tag):
    p = {"model": "qwen3:8b", "prompt": "用一句话说明什么是对话", "stream": False,
         "think": False, "options": {"num_predict": 96}}
    r = urllib.request.Request("http://localhost:11434/api/generate",
                               data=json.dumps(p).encode(),
                               headers={"Content-Type": "application/json"})
    t0 = time.time()
    d = json.loads(urllib.request.urlopen(r, timeout=300).read().decode())
    return round(time.time() - t0, 1), d.get("eval_count", 0)

t0 = time.time(); r1 = ask("a"); r2 = ask("b"); serial = round(time.time() - t0, 1)
print(f"串行 2 请求: {serial}s  (各自 {r1[0]}s / {r2[0]}s)")

res = {}
def worker(k):
    res[k] = ask(k)
t0 = time.time()
ths = [threading.Thread(target=worker, args=(f"t{i}",)) for i in range(2)]
[t.start() for t in ths]; [t.join() for t in ths]
conc = round(time.time() - t0, 1)
print(f"并发 2 请求: {conc}s  (各自 {res['t0'][0]}s / {res['t1'][0]}s)")
print(f"→ 并发{'有效' if conc < serial * 0.75 else '无效（Ollama 串行处理）'}，省 {round((1 - conc/serial) * 100)}%")

print()
print("=" * 60)
print("B · 非 LLM 环节耗时（决定哪里值得并行）")
print("=" * 60)
from book2vido import visualizer, narrator
from book2vido.scriptwriter import Scene

viz = visualizer.PillowProvider(accent="#056DE8", font=None, w=1080, h=1920,
                                icons=True, icon_dir=None, icon_size=430)
scenes = [Scene(f"这是第{i}张测试卡片的正文内容", "测试") for i in range(1, 13)]
os.makedirs("/tmp/vizprobe", exist_ok=True)

t0 = time.time()
for i, s in enumerate(scenes):
    viz.card(s, i + 1, "/tmp/vizprobe")
viz_serial = round(time.time() - t0, 1)
print(f"渲染 12 张卡（串行）: {viz_serial}s  → 单张 {round(viz_serial/12, 2)}s")

tts = narrator.EdgeTTSProvider("zh-CN-YunxiNeural")
t0 = time.time()
for i in range(3):
    tts.speak(f"这是第{i}句语音合成测试", f"/tmp/vizprobe/v{i}.mp3")
tts_avg = round((time.time() - t0) / 3, 2)
print(f"TTS 单句: {tts_avg}s  → 12 句约 {round(tts_avg*12, 1)}s")

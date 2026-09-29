#!/usr/bin/env python3
"""最小 tool-calling 实测：Ollama /api/chat 原生 tools 支持验证。
零框架、零依赖，只用标准库。用来回答"要调工具是不是必须上框架"。
"""
import json, urllib.request, time

OLLAMA = "http://localhost:11434"
MODEL = "qwen3:8b"

# 1) 工具声明：就是一段 JSON Schema，跟 OpenAI function calling 同形
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取本机某个文件的内容",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "绝对路径"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "count_words",
            "description": "统计一段中文文本的字数",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    },
]


def chat(messages, tools=None, think=False):
    payload = {"model": MODEL, "messages": messages, "stream": False, "think": think}
    if tools:
        payload["tools"] = tools
    req = urllib.request.Request(
        OLLAMA + "/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    raw = urllib.request.urlopen(req, timeout=180).read().decode()
    d = json.loads(raw)
    return d.get("message", {}), round(time.time() - t0, 1)


# 真实工具实现（模型只负责"决定调哪个"，真执行的是我们的代码）
def read_file(path):
    try:
        return open(path, encoding="utf-8").read()[:400]
    except Exception as e:
        return f"读取失败：{e}"


def count_words(text):
    return f"共 {len(text)} 个字符"


IMPL = {"read_file": read_file, "count_words": count_words}

print("=" * 62)
print("TEST 1 · 单步工具调用")
print("=" * 62)
msgs = [{"role": "user", "content": "帮我看看 /etc/hostname 里写了什么"}]
msg, sec = chat(msgs, tools=TOOLS)
print(f"[{sec}s] role={msg.get('role')} content={msg.get('content')!r}")
calls = msg.get("tool_calls") or []
print(f"tool_calls = {json.dumps(calls, ensure_ascii=False)}")

if calls:
    fn = calls[0]["function"]
    name, args = fn["name"], fn.get("arguments", {})
    if isinstance(args, str):
        args = json.loads(args)
    print(f"\n→ harness 执行: {name}({args})")
    result = IMPL[name](**args)
    print(f"→ 工具返回: {result!r}\n")

    msgs.append(msg)
    msgs.append({"role": "tool", "content": str(result), "tool_name": name})
    msg2, sec2 = chat(msgs, tools=TOOLS)
    print(f"[{sec2}s] 模型最终回答: {msg2.get('content','').strip()[:200]}")

print()
print("=" * 62)
print("TEST 2 · 多步 loop（让模型自己决定收工）")
print("=" * 62)
msgs = [{"role": "user", "content": "先读 /etc/hostname，然后统计它有多少字符。两个工具都要用。"}]
for step in range(1, 6):
    msg, sec = chat(msgs, tools=TOOLS)
    calls = msg.get("tool_calls") or []
    if not calls:
        print(f"\nstep {step} · 无工具调用 → loop 收工")
        print(f"最终回答：{msg.get('content','').strip()[:300]}")
        break
    print(f"\nstep {step} [{sec}s] 调用 {len(calls)} 个工具:")
    msgs.append(msg)
    for c in calls:
        fn = c["function"]
        args = fn.get("arguments", {})
        if isinstance(args, str):
            args = json.loads(args)
        print(f"   → {fn['name']}({args})")
        try:
            r = IMPL[fn["name"]](**args)
        except Exception as e:
            r = f"工具异常：{e}"
        print(f"   ← {str(r)[:80]!r}")
        msgs.append({"role": "tool", "content": str(r), "tool_name": fn["name"]})
else:
    print("\n⚠️ 5 步内未收工 —— 这就是 harness 必须加「步数上限」的原因")

print()
print("=" * 62)
print("TEST 3 · 模型自己的记忆边界")
print("=" * 62)
msgs = [{"role": "user", "content": "我刚才让你读了哪个文件？"}]
msg, sec = chat(msgs, tools=TOOLS)
print(f"[{sec}s] 空 handshake 下的回答：{msg.get('content','').strip()[:160]}")
print("（如果没有把上文的 messages 带进来，模型就答不出——记忆全在请求里）")

#!/usr/bin/env python3
"""验证「断外网仍可出片」—— 在 socket 层拦截所有非本机连接，跑一次真实出片。

为什么必须在 socket 层拦（而不是设 http_proxy 或用防火墙）：
  - 设 `http_proxy` 只对尊重该变量的库有效，`aiohttp` 默认 `trust_env=False`
    （edge-tts 走的就是它）→ 代理方案会漏掉**恰恰最需要验证的那一环**。
  - 在 `getaddrinfo` + `socket.connect` 两层拦，任何 Python 库都逃不掉。
  - 不需要 sudo / 不需要系统级改动，跑完即恢复。

本脚本回答三个问题：
  1. 断外网时这条流水线**会不会挂**？（退出码 + 是否产出成片）
  2. 它**尝试**访问了哪些外网地址？（谁在偷偷依赖网络）
  3. 降级路径**花了多久**？（用户要等多久才看到"它自己降级了"）

用法：
  python tests/verify_offline.py --tts say    # 预期：直通，快
  python tests/verify_offline.py --tts edge   # 预期：失败→回退 say，慢
  python tests/verify_offline.py --tts edge --fast --chapter 3
"""
from __future__ import annotations

import argparse
import socket
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# ── 本机地址白名单：只有这些放行（Ollama 在 localhost:11434）──
ALLOWED = {"127.0.0.1", "::1", "localhost", "0.0.0.0", "", None}

_intercepted: list[tuple[str, str, float, str]] = []
_real_getaddrinfo = socket.getaddrinfo
_real_connect = socket.socket.connect


def _where() -> str:
    """回溯第一个「不在本文件里」的调用帧 —— 用来指认是谁想联网。"""
    import traceback
    for fr in reversed(traceback.extract_stack(limit=14)):
        if "verify_offline.py" in fr.filename:
            continue
        return f"{Path(fr.filename).name}:{fr.lineno} in {fr.name}"
    return "?"


def _gai(host, *a, **k):
    if host not in ALLOWED:
        _intercepted.append(("DNS", str(host), time.time(), _where()))
        raise socket.gaierror(-2, f"simulated offline: cannot resolve {host}")
    return _real_getaddrinfo(host, *a, **k)


def _connect(self, address):
    # AF_UNIX 的地址是**字符串路径**而非 (host, port)：它不是网络连接，
    # 直接放行。实测（本脚本第一版）漏了这一条，把沙箱自身的 IPC socket
    # 拦了 68 次 —— 拦截器自己制造噪声，会淹没真正要看的"谁在联网"。
    if isinstance(address, str):
        return _real_connect(self, address)
    host = address[0]
    port = address[1] if len(address) > 1 else "?"
    if host not in ALLOWED:
        _intercepted.append(("TCP", f"{host}:{port}", time.time(), _where()))
        raise OSError(51, f"Network is unreachable (simulated offline): {host}")
    return _real_connect(self, address)


def install_netblock() -> None:
    socket.getaddrinfo = _gai
    socket.socket.connect = _connect


def make_offline_config(tts_provider: str, tmpdir: Path) -> Path:
    """基于项目 config.yaml 生成一份「断网档」：指定 TTS + 关缓存（强制真跑）。

    关缓存是必须的 —— 否则命中的成片缓存会让测试变成"验证缓存能读"，
    而不是"验证断网时这条链路能跑完"。
    """
    import re
    src = (ROOT / "config.yaml").read_text(encoding="utf-8")
    # 只改 tts.provider 行，其余原样保留（避免臆造配置项）
    out = re.sub(r"(?m)^(\s*provider:\s*)\S+(\s*#.*edge.*)$",
                 lambda m: f"{m.group(1)}{tts_provider}{m.group(2)}", src, count=1)
    assert f"provider: {tts_provider}" in out, "未成功覆盖 tts.provider，检查 config.yaml 格式"
    # 关缓存（cache.enabled: true → false）
    out = re.sub(r"(?m)^(\s*enabled:\s*)true(\s*#.*缓存.*)$",
                 lambda m: f"{m.group(1)}false{m.group(2)}", out, count=1)
    p = tmpdir / "config-offline.yaml"
    p.write_text(out, encoding="utf-8")
    return p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", default=str(ROOT / "samples" / "books" / "关键对话.pdf"))
    ap.add_argument("--tts", choices=["edge", "say"], default="edge",
                    help="测哪一档 TTS（edge=在线，say=本地）")
    ap.add_argument("--chapter", type=int, default=None)
    ap.add_argument("--fast", action="store_true", help="think=false，省时间")
    ap.add_argument("--out-dir", default="/tmp/b2v_offline")
    a = ap.parse_args()

    pdf = Path(a.pdf)
    if not pdf.exists():
        print(f"🔴 缺样例：{pdf}")
        print("   放一本文本型 PDF 到 samples/books/ 即可（版权原因不入库）")
        return 2

    tmpdir = Path(a.out_dir)
    (tmpdir / "out").mkdir(parents=True, exist_ok=True)
    cfg_path = make_offline_config(a.tts, tmpdir)
    # 输出必须是**带扩展名的文件路径**：pipeline 把它直传给 `ffmpeg ... <out>`，
    # 传目录会让 ffmpeg 无法判断封装格式（报 "Unable to choose an output format"）。
    # 本脚本第一版就踩了，报错点在最后一步合成，看着像"链路挂了"，其实是调用方写错。
    out_path = tmpdir / "out" / f"{pdf.stem}__offline_{a.tts}.mp4"

    print("═" * 62)
    print(f"断网仿真 · TTS={a.tts} · think={'false' if a.fast else 'true'} · 缓存=关")
    print("  拦截层：socket.getaddrinfo + socket.socket.connect")
    print(f"  白名单：{sorted(x for x in ALLOWED if x)}（本机 Ollama 放行）")
    print("═" * 62)

    install_netblock()

    from book2vido import pipeline

    t0 = time.time()
    err = None
    result = None
    try:
        result = pipeline.run(str(pdf), str(out_path), str(cfg_path),
                              think=(False if a.fast else None))
    except Exception as e:  # noqa: BLE001 —— 这里就是要抓任何异常看它挂不挂
        err = e
    elapsed = time.time() - t0

    print()
    print("═" * 62)
    print("结果")
    print("═" * 62)
    if err:
        print(f"❌ 失败（{type(err).__name__}）：{err}")
    else:
        out = result.get("out")
        exists = Path(out).exists() if out else False
        size = Path(out).stat().st_size if exists else 0
        print(f"✅ 出片成功：{out}")
        print(f"   {size / 1024:.0f} KB · {result.get('scenes')} 句 · "
              f"{result.get('seconds', 0):.1f}s · 耗时 {elapsed:.1f}s")
    print()
    n = len(_intercepted)
    if n == 0:
        print("🌐 外网访问：0 次 —— 全链路本机自足")
    else:
        hosts: dict[str, int] = {}
        for _, addr, _, _ in _intercepted:
            key = addr.split(":")[0]
            hosts[key] = hosts.get(key, 0) + 1
        print(f"🌐 外网访问被拦：{n} 次，涉及 {len(hosts)} 个目标")
        for h, c in sorted(hosts.items(), key=lambda x: -x[1]):
            print(f"   · {h:34} × {c}")
        print("   首次尝试来自：", _intercepted[0][3])
    print()
    print(f"总耗时：{elapsed:.1f}s")
    return 1 if err else 0


if __name__ == "__main__":
    sys.exit(main())

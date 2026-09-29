"""把 `verify_*.py` 守护脚本接进 pytest —— 让 CI 真正守住它们。

为什么需要这个文件
──────────────────
`tests/` 里的守护脚本原本是「人记得住就去跑一遍」的：命名是 `verify_*.py`，
不在 pytest 默认的收集规则里，于是**一条都不会被 CI 跑到**（表现为
「0 条用例 / 退出码 5」，看着像通过，其实什么都没验证）。

本文件把它们按「能不能在无网、无 ollama、无真书的环境里跑」分成两半：

  ✅ 进 CI（本文件）：deps / icons / prompt / cache / segmenter —— 纯标准库 + 仓库内资产
  ⛔ 不进 CI：env（要 ollama 在跑）、gate（要真书）、offline（要跑完整出片）、
     narrator_concurrency（要联网 TTS）—— 它们在 CI 上必然红，且红了不代表代码坏了，
     是「环境不具备」。这类仍按 tests/README.md 的方式**按需单独跑**。

判据是「红了 = 不该合入」，不是「红了 = 想量一下」—— 见 tests/README.md 开头那张表。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"

CI_SAFE = [
    "verify_deps.py",
    "verify_icons.py",
    "verify_prompt.py",
    "verify_cache.py",
    "verify_segmenter.py",
]


@pytest.mark.parametrize("name", CI_SAFE)
def test_verify_script(name: str):
    """守护脚本必须**退出码 0**（它们自己负责打印失败原因）。"""
    r = subprocess.run([sys.executable, str(TESTS / name)], cwd=ROOT,
                       capture_output=True, text=True)
    # 失败时必须把脚本自己的输出贴出来：守护脚本的失败原因全在它的 print 里，
    # 只报「退出码 1」等于让人重跑一遍才知道发生了什么。
    assert r.returncode == 0, (
        f"{name} 退出码 {r.returncode}\n"
        f"--- stdout ---\n{r.stdout}\n--- stderr ---\n{r.stderr}"
    )

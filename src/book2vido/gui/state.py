"""GUI 的共享可变状态（跨模块单例）。

为什么单独成文件：`gui/server.py` 被拆出 `handlers/env.py` 与 `handlers/tasks.py` 时，
这两个模块**仍在引用 server.py 里的模块级变量**（`GUI_DIR` / `_install_jobs` /
`_install_lock`），但它们**不能**反过来 `from ..server import ...` —— server 会 import
handlers，那是一条环（`ImportError: cannot import name` 或拿到半个模块）。

结果是：名字在本模块里根本不存在 → 一键安装 / 任务启动在运行时抛
`NameError: name '_install_lock' is not defined`（**静态检查 F821 能查出来，
但没人跑过静态检查，所以一直没被发现** —— 这也是本项目把 ruff 接进 CI 的直接原因）。

把状态下沉到这个谁都可以 import 的叶子模块，环就消失了：
server 和 handlers 都只依赖 state，state 不依赖任何包内模块。
"""
from __future__ import annotations

import threading
from pathlib import Path

# GUI 静态资源目录（`gui/` 本身，装 index.html / style.css / app.js / voices/）
GUI_DIR = Path(__file__).resolve().parent

# 安装任务的进度 / 日志。key = install_id（`inst_<timestamp>`）
_install_jobs: dict = {}
_install_lock = threading.Lock()

"""外部二进制定位（ffmpeg / ffprobe / rsvg-convert）。

为什么需要单独一层：
  1. **打包分发**：`.app` 双击启动时 PATH 极窄，不含 /opt/homebrew/bin；
     二进制必须优先用随包内置的 `vendor/`，否则用户必然报「找不到 ffmpeg」。
  2. **跨机器**：Intel Mac 是 /usr/local/bin，MacPorts 又是另一处。
  3. **不写死**：允许 `BOOK2VIDO_FFMPEG` 等环境变量强制覆盖（CI / 测试 / 特殊安装）。

查找优先级：环境变量 → 随包 vendor → 常见包管理器路径 → PATH。
查不到时**不静默**：报错信息里给出可执行的补救命令。
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from .paths import project_root

_CACHE: dict[str, str | None] = {}

# 常见包管理器安装位置（Apple Silicon 优先）
_COMMON_DIRS = [
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "/opt/local/bin",          # MacPorts
    os.path.expanduser("~/.local/bin"),
    "/usr/bin",
]


def _vendor_dirs() -> list[Path]:
    """可能存放随包二进制的目录，按优先级排列。

    .app 布局:  Contents/Resources/runtime/bin/python3   (sys.prefix)
                Contents/Resources/vendor/ffmpeg         (目标)
    开发布局:   <repo>/vendor/ffmpeg
    """
    out: list[Path] = []

    env = os.environ.get("BOOK2VIDO_VENDOR")
    if env:
        out.append(Path(env))

    # .app：sys.prefix = .../Resources/runtime → 兄弟目录 vendor
    try:
        out.append(Path(sys.prefix).parent / "vendor")
    except Exception:
        pass

    # 开发模式：<repo>/vendor（项目根来自 paths，唯一来源）
    # ⚠️ 这一处曾用 parents[2] 硬算 —— 若包被移进子目录，它会**静默指空**，
    #    然后整条链退到 _COMMON_DIRS，本机有 brew ffmpeg 就永远测不出来（doc/17 §S-1）。
    out.append(project_root() / "vendor")
    return out


def resolve(name: str, env_var: str | None = None) -> str | None:
    """定位二进制，返回绝对路径；找不到返回 None。结果带缓存。"""
    if name in _CACHE:
        return _CACHE[name]

    found: str | None = None

    # 1) 环境变量强制覆盖
    if env_var:
        forced = os.environ.get(env_var)
        if forced and Path(forced).exists():
            found = forced

    # 2) 随包内置
    if not found:
        for d in _vendor_dirs():
            cand = d / name
            if cand.is_file() and os.access(cand, os.X_OK):
                found = str(cand)
                break

    # 3) 常见路径
    if not found:
        for d in _COMMON_DIRS:
            cand = Path(d) / name
            if cand.is_file() and os.access(cand, os.X_OK):
                found = str(cand)
                break

    # 4) PATH
    if not found:
        found = shutil.which(name)

    _CACHE[name] = found
    return found


def require(name: str, env_var: str | None = None, hint: str = "") -> str:
    """定位二进制，找不到时抛带补救命令的错误（不静默降级）。"""
    p = resolve(name, env_var)
    if p:
        return p
    tip = hint or (
        f"请任选其一：① 把 {name} 放进项目的 vendor/ 目录；"
        f"② 设置环境变量 {env_var or '（无）'}；③ brew install {name}"
    )
    raise RuntimeError(f"找不到外部命令 `{name}`。{tip}")


# ---- 对外 API：模块内统一从这里取，不要再硬编码绝对路径 ----

def ffmpeg() -> str:
    return require("ffmpeg", "BOOK2VIDO_FFMPEG")


def ffprobe() -> str:
    # ffprobe 通常与 ffmpeg 同目录；若 vendor 只放了 ffmpeg，尝试同目录兜底
    p = resolve("ffprobe", "BOOK2VIDO_FFPROBE")
    if p:
        return p
    ff = resolve("ffmpeg", "BOOK2VIDO_FFMPEG")
    if ff:
        sibling = Path(ff).parent / "ffprobe"
        if sibling.is_file():
            _CACHE["ffprobe"] = str(sibling)
            return str(sibling)
    return require("ffprobe", "BOOK2VIDO_FFPROBE")


def rsvg_convert() -> str | None:
    """可选依赖：没有就返回 None，让调用方回退 cairosvg。"""
    return resolve("rsvg-convert", "BOOK2VIDO_RSVG")


def report() -> dict[str, str | None]:
    """自检用：一次性看清每个外部依赖解析到哪里。"""
    return {
        "ffmpeg": resolve("ffmpeg", "BOOK2VIDO_FFMPEG"),
        "ffprobe": resolve("ffprobe", "BOOK2VIDO_FFPROBE"),
        "rsvg-convert": resolve("rsvg-convert", "BOOK2VIDO_RSVG"),
    }

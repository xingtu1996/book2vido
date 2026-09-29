"""项目根定位的**唯一来源**。

为什么要有这个模块（这是它存在的全部理由）
────────────────────────────────────────────
在此之前，"项目根在哪" 这件事在 **5 个模块里各写了一遍**：

    binpaths.py    Path(__file__).resolve().parents[2] / "vendor"
    visualizer.py  Path(__file__).resolve().parents[2]              ← 曾定义为 project_root()
    cache.py       Path(__file__).resolve().parents[2] / "cache"
    promptlib.py   Path(__file__).resolve().parents[2] / "prompts"
    __main__.py    Path(__file__).resolve().parents[2] / "config.yaml"

同一段逻辑抄 5 份，代价**不在今天，在未来某次改动**：
本项目后续若要按性质分目录（`core/` `stages/` `support/`，见 doc/17），
每个模块的深度会 +1 —— 5 份推导就**同时**失效。而其中两处**不报错**：

  · `cache.py`      → 在错误位置新建 `cache/`，缓存全部 miss，表现为"变慢了"
  · `binpaths.py`   → 找不到随包二进制，退回系统 PATH（本机有 brew ffmpeg，于是本地永远测不出来）

只有 3 处会立刻报错。也就是说，"重构完成、测试全绿"的当天，另两处会**静默降级**。

收敛到一处之后：**改结构只改这个文件**。

放这里为什么是安全的
────────────────────
本模块只依赖标准库（`pathlib`），没有任何包内依赖 ——
所以任何层级的模块都可以依赖它，**不会产生环**。

`.app` 打包后的同一份代码
──────────────────────────
    <App>.app/Contents/Resources/app/book2vido/paths.py
        parents[0] = .../app/book2vido
        parents[1] = .../app
        parents[2] = .../Contents/Resources   ← 项目根

开发态：
    <repo>/src/book2vido/paths.py
        parents[0] = <repo>/src/book2vido
        parents[1] = <repo>/src
        parents[2] = <repo>                    ← 项目根

两种布局下 `config.yaml` / `prompts/` / `assets/` / `vendor/` / `cache/` 都在
`parents[2]` 处同级并列 —— 这也是 `packaging/build_app.sh` 的布局前提。
"""
from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    """项目根目录。

    开发态 = 仓库根；打包后 = `<App>.app/Contents/Resources/`。
    本文件位于 `<root>/src/book2vido/paths.py`（打包后 `<root>/app/book2vido/paths.py`），
    上溯三级即：**文件 → 包目录(book2vido) → src 或 app → 项目根**。

    ⚠️ 若本文件被移动层级（例如移入 `core/`，则需 `parents[3]`），
    **必须同步调整下面的 `parents[n]`** —— 这是全项目唯一需要知道
    "自己在第几层"的地方，移动其他任何模块都不必改这里。
    """
    return Path(__file__).resolve().parents[2]

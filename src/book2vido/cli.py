"""console_scripts 入口（`book2vido` 命令）。

为什么要有它：`python -m book2vido` 走的是 `__main__.py`，而 `pip install .`
生成的 `book2vido` 命令需要一个**可导入的模块路径**（`book2vido.cli:main`）。
若把入口直接指向 `book2vido.__main__:main`，该模块会被**同时**当作
"`__main__` 模块"和"普通模块"两条路径加载（前者在 `python -m` 时成立），
同一个文件出现两份模块对象，`sys.path` 注入与 argparse 的副作用会各跑一遍。

所以这里只做**转发**，真实实现仍在 `__main__.py`（单一事实源）：

    book2vido run --input x.pdf --out y.mp4
        ≡
    python -m book2vido run --input x.pdf --out y.mp4
"""
from __future__ import annotations

import sys
from pathlib import Path

# 与 `__main__.py` 同一处 sys.path 注入：让 `import book2vido` 在
# 开发态（<repo>/src）与打包态（.../app）都能解析。语义说明见 `__main__.py` 顶部。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from book2vido.__main__ import main  # noqa: E402  必须在 sys.path 注入之后

if __name__ == "__main__":
    sys.exit(main())

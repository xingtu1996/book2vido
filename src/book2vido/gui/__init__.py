"""Book2Vido GUI —— 本地 Web 界面。"""
from .server import start_server, main

# 这两个名字是**故意**只 import 不用的（对外再导出，`python -m book2vido.gui` 与
# 外部脚本都从这里取）。不写 `__all__` 的话 ruff 的 F401 会把它判成"没用到的导入"，
# 而 CI 里的 ruff 是门禁 —— 所以这里显式声明"这是公共 API"。
__all__ = ["start_server", "main"]

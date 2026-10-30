"""commands 包 — CLI 命令拆分模块

公共依赖集中在此处导出，子模块统一从这里导入。
"""

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

# 全局共享 console 实例（与 cli.py 中的是同一配置，但各自独立实例）
# 注意：cli.py 中 console 也是 force_terminal=True，行为一致
console = Console(force_terminal=True)

def as_bool(value, default: bool = False) -> bool:
    """把 Typer Option 的默认值兜底成真正的布尔值

    命令函数被其它命令直接调用（而非经 Typer 解析命令行）时，
    未显式传参的 Option 拿到的是 OptionInfo 对象，bool() 为真，
    会把默认 False 的开关当成已开启。
    """
    return value if isinstance(value, bool) else default


def as_int(value, default: int = 0) -> int:
    """同 as_bool，用于数值型 Option"""
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return value


# 这些名称是本包对外导出的公共依赖，子模块通过
# `from app.commands import console, Table, Panel, box` 使用
__all__ = ["console", "Table", "Panel", "Text", "box", "as_bool", "as_int"]

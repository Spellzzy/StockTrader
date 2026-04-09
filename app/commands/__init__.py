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

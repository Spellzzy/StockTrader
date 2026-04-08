"""底部状态栏 Widget

功能:
    - 显示快捷键提示
    - 显示最后刷新时间
    - 显示当前状态信息
"""

from __future__ import annotations

from datetime import datetime

from textual.app import ComposeResult
from textual.widgets import Static
from textual.widget import Widget

from rich.text import Text


class DashboardStatusBar(Widget):
    """底部状态栏"""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._status: str = "启动中..."
        self._last_refresh: str = ""

    def compose(self) -> ComposeResult:
        yield Static("", id="status-content")

    def on_mount(self) -> None:
        self._refresh_display()

    def update_status(self, status: str) -> None:
        """更新状态信息"""
        self._status = status
        self._last_refresh = datetime.now().strftime("%H:%M:%S")
        self._refresh_display()

    def _refresh_display(self) -> None:
        """刷新状态栏显示"""
        content = self.query_one("#status-content", Static)
        line = Text()
        line.append(" [Q]", style="bold white")
        line.append("退出 ", style="dim white")
        line.append("[R]", style="bold white")
        line.append("刷新 ", style="dim white")
        line.append("[Tab]", style="bold white")
        line.append("切换 ", style="dim white")
        line.append("[/]", style="bold white")
        line.append("搜索 ", style="dim white")
        line.append("[Enter]", style="bold white")
        line.append("详情 ", style="dim white")

        # 右侧状态
        line.append("  │  ", style="dim white")
        line.append(self._status, style="white")

        if self._last_refresh:
            line.append(f"  ⏰ {self._last_refresh}", style="dim white")

        content.update(line)

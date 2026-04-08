"""TUI Dashboard 主应用

启动方式:
    stock-ai dashboard  (或缩写 d)
    python -m app.tui.app
"""

from __future__ import annotations

from pathlib import Path

from textual.app import App

from app.tui.services import ServiceContainer
from app.tui.screens.main import MainScreen


class StockTraderDashboard(App):
    """Stock Trader AI — TUI Dashboard"""

    TITLE = "Stock Trader AI"
    SUB_TITLE = "Dashboard"
    CSS_PATH = Path(__file__).parent / "dashboard.tcss"

    # 定时刷新间隔（秒）
    REFRESH_INTERVAL = 30.0

    def __init__(self, refresh_interval: float = 30.0, **kwargs):
        super().__init__(**kwargs)
        self.services = ServiceContainer()
        self._refresh_interval = refresh_interval

    def on_mount(self) -> None:
        """应用挂载 — 推入主屏幕 + 启动定时刷新"""
        self.push_screen(MainScreen())
        self._start_auto_refresh()

    def _start_auto_refresh(self) -> None:
        """启动定时刷新"""
        self.set_interval(self._refresh_interval, self._auto_refresh)

    async def _auto_refresh(self) -> None:
        """定时刷新行情数据"""
        screen = self.screen
        if isinstance(screen, MainScreen):
            try:
                await screen.action_refresh()
            except Exception:
                pass  # 刷新失败不影响 UI

    def on_search_dialog_stock_added(self, event) -> None:
        """收到 SearchDialog.StockAdded 消息 — 关闭弹窗并刷新数据

        消息从 SearchDialog 冒泡到 App 层面处理。
        在 App 层面调用 pop_screen 关闭搜索弹窗，避免 ScreenError。
        """
        from app.tui.screens.search_dialog import SearchDialog

        # 关闭搜索弹窗
        if isinstance(self.screen, SearchDialog):
            try:
                self.pop_screen()
            except Exception:
                pass

        # 刷新自选和行情
        self.call_after_refresh(self._refresh_after_add)

    async def _refresh_after_add(self) -> None:
        """添加自选股后刷新主屏幕"""
        screen = self.screen
        if isinstance(screen, MainScreen):
            try:
                await screen._refresh_after_search()
            except Exception:
                pass

    def on_unmount(self) -> None:
        """应用退出 — 清理资源"""
        self.services.shutdown()


def run_dashboard(refresh_interval: float = 30.0) -> None:
    """启动 Dashboard（供 CLI 调用）"""
    from app.db.database import init_db
    init_db()
    dashboard = StockTraderDashboard(refresh_interval=refresh_interval)
    dashboard.run()


# 支持 python -m app.tui.app 直接启动
if __name__ == "__main__":
    run_dashboard()

"""主屏幕 — 组装所有面板组件

布局:
    ┌─────────────────────────────────────────────────────┐
    │  Header Bar (标题 + 时间)                            │
    ├──────────┬──────────────────┬────────────────────────┤
    │ Watchlist│  Quote Panel     │  Alert Log             │
    │ Sidebar  │  (实时行情)       │  (预警日志)             │
    ├──────────┴──────────────────┴────────────────────────┤
    │  [持仓概览] [交易记录] [AI分析]                        │
    ├─────────────────────────────────────────────────────┤
    │  Status Bar (快捷键提示 + 刷新状态)                    │
    └─────────────────────────────────────────────────────┘

交互:
    / → 搜索弹窗（添加自选）
    Enter → 个股详情页（K线/分时/概况）
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static, TabbedContent, TabPane, DataTable

from app.tui.widgets.watchlist import WatchlistSidebar
from app.tui.widgets.quote_panel import QuotePanel
from app.tui.widgets.alert_log import AlertLog
from app.tui.widgets.portfolio import PortfolioTab
from app.tui.widgets.trades import TradesTab
from app.tui.widgets.ai_panel import AIPanel
from app.tui.widgets.status_bar import DashboardStatusBar


class MainScreen(Screen):
    """Dashboard 主屏幕"""

    BINDINGS = [
        ("q", "quit", "退出"),
        ("r", "refresh", "刷新"),
        ("slash", "search", "搜索"),
        ("tab", "focus_next", "切换面板"),
        ("shift+tab", "focus_previous", "反向切换"),
    ]

    def compose(self) -> ComposeResult:
        # 顶部标题
        yield Static(
            " 📈 Stock Trader AI Dashboard",
            id="header-bar",
        )

        # 三列主体
        with Horizontal(id="main-body"):
            yield WatchlistSidebar(id="watchlist-sidebar")
            yield QuotePanel(id="quote-panel")
            yield AlertLog(id="alert-log")

        # 底部 Tab 区
        with Vertical(id="bottom-tabs"):
            with TabbedContent():
                with TabPane("📊 持仓概览", id="tab-portfolio"):
                    yield PortfolioTab()
                with TabPane("📋 交易记录", id="tab-trades"):
                    yield TradesTab()
                with TabPane("🤖 AI 分析", id="tab-ai"):
                    yield AIPanel()

        # 底部状态栏
        yield DashboardStatusBar(id="status-bar")

    def on_mount(self) -> None:
        """屏幕挂载后触发首次数据加载"""
        self.app.call_after_refresh(self._initial_load)

    async def _initial_load(self) -> None:
        """首次加载所有数据"""
        # 依次触发各面板刷新
        watchlist = self.query_one(WatchlistSidebar)
        quote_panel = self.query_one(QuotePanel)
        alert_log = self.query_one(AlertLog)
        portfolio = self.query_one(PortfolioTab)
        trades = self.query_one(TradesTab)
        status_bar = self.query_one(DashboardStatusBar)

        # 并行加载
        await watchlist.load_data()
        await quote_panel.load_data()
        await alert_log.load_data()
        await portfolio.load_data()
        await trades.load_data()
        status_bar.update_status("就绪")

    async def action_refresh(self) -> None:
        """手动刷新所有面板"""
        status_bar = self.query_one(DashboardStatusBar)
        status_bar.update_status("刷新中...")

        watchlist = self.query_one(WatchlistSidebar)
        quote_panel = self.query_one(QuotePanel)
        alert_log = self.query_one(AlertLog)
        portfolio = self.query_one(PortfolioTab)
        trades = self.query_one(TradesTab)

        await watchlist.load_data()
        await quote_panel.load_data()
        await alert_log.load_data()
        await portfolio.load_data()
        await trades.load_data()

        status_bar.update_status("就绪")

    def action_quit(self) -> None:
        """退出 Dashboard"""
        self.app.exit()

    def action_search(self) -> None:
        """打开搜索弹窗"""
        from app.tui.screens.search_dialog import SearchDialog
        self.app.push_screen(SearchDialog())

    async def _refresh_after_search(self) -> None:
        """搜索添加后刷新自选和行情"""
        watchlist = self.query_one(WatchlistSidebar)
        quote_panel = self.query_one(QuotePanel)
        status_bar = self.query_one(DashboardStatusBar)
        status_bar.update_status("刷新中...")
        await watchlist.load_data()
        await quote_panel.load_data()
        status_bar.update_status("就绪")

    # ==================== 个股详情入口 ====================

    def on_watchlist_sidebar_stock_selected(
        self, event: WatchlistSidebar.StockSelected
    ) -> None:
        """自选股侧边栏选中 → 打开个股详情"""
        self._open_stock_detail(event.stock_code, event.stock_name)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """行情面板选中行 → 打开个股详情"""
        # row_key 是 stock code
        code = str(event.row_key.value) if event.row_key else ""
        if not code:
            return

        # 从行情缓存中找名称
        cache = self.app.services.quotes_cache
        name = cache.get(code, {}).get("name", "") if cache else ""
        self._open_stock_detail(code, name)

    def _open_stock_detail(self, stock_code: str, stock_name: str) -> None:
        """打开个股详情页"""
        from app.tui.screens.stock_detail import StockDetailScreen
        self.app.push_screen(StockDetailScreen(stock_code=stock_code, stock_name=stock_name))

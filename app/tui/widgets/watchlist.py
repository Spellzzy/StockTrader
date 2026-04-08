"""自选股侧边栏 Widget

功能:
    - 展示自选股列表（代码 + 名称 + 价格 + 涨跌%）
    - 支持方向键选中，选中后高亮并通知行情面板
    - 支持数据刷新
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Static, ListView, ListItem, Label
from textual.widget import Widget

from rich.text import Text


class WatchlistSidebar(Widget):
    """自选股侧边栏"""

    class StockSelected(Message):
        """自选股选中事件"""
        def __init__(self, stock_code: str, stock_name: str) -> None:
            super().__init__()
            self.stock_code = stock_code
            self.stock_name = stock_name

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._stocks: list[dict] = []
        self._mounted = False
        self._pending_render = False
        self._pending_error: str | None = None

    def compose(self) -> ComposeResult:
        yield Static(" ⭐ 自选股", classes="sidebar-title")
        yield ListView(id="watchlist-listview")

    def on_mount(self) -> None:
        """组件挂载完成后标记就绪，并刷新待渲染内容"""
        self._mounted = True
        if self._pending_error is not None:
            self._render_error(self._pending_error)
            self._pending_error = None
        elif self._pending_render:
            self._render_list()
            self._pending_render = False

    async def load_data(self) -> None:
        """加载自选股数据（在后台线程执行）"""
        try:
            services = self.app.services
            data = await services.run_sync(
                services.watchlist.list_watched_with_quote
            )
            self._stocks = data or []
            if self._mounted:
                self._render_list()
            else:
                self._pending_render = True
        except Exception as e:
            if self._mounted:
                self._render_error(str(e))
            else:
                self._pending_error = str(e)

    def _render_list(self) -> None:
        """渲染自选股列表"""
        try:
            listview = self.query_one("#watchlist-listview", ListView)
        except Exception:
            self._pending_render = True
            return

        listview.clear()

        if not self._stocks:
            listview.append(ListItem(Label("[dim]暂无自选股[/dim]")))
            return

        for stock in self._stocks:
            code = stock.get("code", "")
            name = stock.get("name", "") or code
            price = stock.get("price", 0)
            change_pct = stock.get("change_percent", 0)

            # 涨跌颜色
            if change_pct > 0:
                color = "red"
                sign = "+"
            elif change_pct < 0:
                color = "green"
                sign = ""
            else:
                color = "dim"
                sign = ""

            # 格式: 茅台 sh600519
            #        1856.00  +2.05%
            line1 = Text()
            line1.append(f"{name[:6]:<6s}", style="bold")
            line1.append(f" {code}", style="dim")

            line2 = Text()
            if price > 0:
                line2.append(f"  {price:.2f}", style=color)
                line2.append(f"  {sign}{change_pct:.2f}%", style=color)
            else:
                line2.append("  --", style="dim")

            item = ListItem(
                Label(line1),
                Label(line2),
                name=code,  # 用于识别选中的股票
            )
            listview.append(item)

    def _render_error(self, msg: str) -> None:
        """渲染错误信息"""
        try:
            listview = self.query_one("#watchlist-listview", ListView)
        except Exception:
            self._pending_error = msg
            return

        listview.clear()
        listview.append(ListItem(Label(f"[red]加载失败: {msg}[/red]")))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """用户选中一只股票"""
        item = event.item
        if item.name:
            # 从缓存中找到对应股票
            stock = next((s for s in self._stocks if s.get("code") == item.name), None)
            name = stock.get("name", "") if stock else ""
            self.post_message(self.StockSelected(stock_code=item.name, stock_name=name))

"""实时行情面板 Widget

功能:
    - DataTable 展示自选股的实时行情（代码/名称/价格/涨跌额/涨跌%/成交量/换手率）
    - 涨红跌绿
    - 支持定时刷新
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static, DataTable
from textual.widget import Widget

from rich.text import Text


class QuotePanel(Widget):
    """实时行情面板"""

    # DataTable 列定义
    COLUMNS = [
        ("代码", 12),
        ("名称", 8),
        ("现价", 10),
        ("涨跌额", 10),
        ("涨跌%", 8),
        ("最高", 10),
        ("最低", 10),
        ("成交量", 12),
        ("换手%", 8),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._quotes: list[dict] = []

    def compose(self) -> ComposeResult:
        yield Static(" 📊 实时行情", classes="panel-title")
        yield DataTable(id="quote-table", zebra_stripes=True)

    def on_mount(self) -> None:
        """初始化 DataTable 列"""
        table = self.query_one("#quote-table", DataTable)
        table.cursor_type = "row"
        for col_name, width in self.COLUMNS:
            table.add_column(col_name, key=col_name, width=width)

    async def load_data(self) -> None:
        """加载行情数据"""
        try:
            services = self.app.services
            data = await services.run_sync(
                services.watchlist.list_watched_with_quote
            )
            self._quotes = data or []

            # 更新共享缓存
            cache = {q["code"]: q for q in self._quotes if q.get("code")}
            services.update_quotes_cache(cache)

            self._render_table()
        except Exception as e:
            self._render_error(str(e))

    def _render_table(self) -> None:
        """渲染行情表格"""
        table = self.query_one("#quote-table", DataTable)
        table.clear()

        for q in self._quotes:
            code = q.get("code", "")
            name = q.get("name", "") or code
            price = q.get("price", 0)
            change = q.get("change", 0)
            change_pct = q.get("change_percent", 0)
            high = q.get("high", 0)
            low = q.get("low", 0)
            volume = q.get("volume", 0)
            turnover = q.get("turnover", 0)

            # 涨跌颜色
            color = self._get_color(change_pct)

            row = [
                Text(code, style="bold"),
                Text(name[:6]),
                self._styled_num(price, ".2f", color),
                self._styled_num(change, "+.2f", color),
                self._styled_num(change_pct, "+.2f", color, suffix="%"),
                self._styled_num(high, ".2f", ""),
                self._styled_num(low, ".2f", ""),
                self._format_volume(volume),
                self._styled_num(turnover, ".2f", "", suffix="%"),
            ]
            table.add_row(*row, key=code)

    def _render_error(self, msg: str) -> None:
        """渲染错误"""
        table = self.query_one("#quote-table", DataTable)
        table.clear()

    @staticmethod
    def _get_color(change_pct: float) -> str:
        if change_pct > 0:
            return "red"
        elif change_pct < 0:
            return "green"
        return "dim"

    @staticmethod
    def _styled_num(
        value: float,
        fmt: str = ".2f",
        color: str = "",
        suffix: str = "",
    ) -> Text:
        """格式化数值并着色"""
        if value == 0 and not color:
            return Text("--", style="dim")
        text = f"{value:{fmt}}{suffix}"
        return Text(text, style=color) if color else Text(text)

    @staticmethod
    def _format_volume(volume: float) -> Text:
        """格式化成交量（自动选择单位）"""
        if volume <= 0:
            return Text("--", style="dim")
        if volume >= 1_0000_0000:
            return Text(f"{volume / 1_0000_0000:.2f}亿")
        if volume >= 1_0000:
            return Text(f"{volume / 1_0000:.1f}万")
        return Text(f"{volume:.0f}")

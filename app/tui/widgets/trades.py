"""交易记录 Tab Widget

功能:
    - DataTable 展示最近交易记录
    - 买入/卖出颜色区分
    - 卖出记录显示盈亏
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import DataTable
from textual.widget import Widget

from rich.text import Text


class TradesTab(Widget):
    """交易记录 Tab"""

    COLUMNS = [
        ("时间", 18),
        ("代码", 12),
        ("名称", 8),
        ("方向", 6),
        ("价格", 10),
        ("数量", 8),
        ("金额", 12),
        ("盈亏", 10),
        ("盈亏%", 8),
        ("策略", 8),
    ]

    def compose(self) -> ComposeResult:
        yield DataTable(id="trades-table", zebra_stripes=True)

    def on_mount(self) -> None:
        table = self.query_one("#trades-table", DataTable)
        table.cursor_type = "row"
        for col_name, width in self.COLUMNS:
            table.add_column(col_name, key=col_name, width=width)

    async def load_data(self) -> None:
        """加载最近交易记录"""
        try:
            services = self.app.services
            trades = await services.run_sync(
                services.trade.list_trades, limit=30
            )
            self._render(trades)
        except Exception as e:
            pass  # 静默处理

    def _render(self, trades: list) -> None:
        """渲染交易记录"""
        table = self.query_one("#trades-table", DataTable)
        table.clear()

        for t in trades:
            action = getattr(t, "action", "")
            is_buy = action == "buy"
            action_text = "买入" if is_buy else "卖出"
            action_color = "red" if is_buy else "green"

            trade_time = getattr(t, "trade_time", None)
            time_str = trade_time.strftime("%m-%d %H:%M") if trade_time else ""

            code = getattr(t, "stock_code", "")
            name = getattr(t, "stock_name", "") or code
            price = getattr(t, "price", 0)
            quantity = getattr(t, "quantity", 0)
            amount = getattr(t, "amount", 0)
            profit = getattr(t, "profit", None)
            profit_rate = getattr(t, "profit_rate", None)
            strategy = getattr(t, "strategy", "") or ""

            # 盈亏列
            if profit is not None:
                pnl_color = "red" if profit >= 0 else "green"
                pnl_sign = "+" if profit >= 0 else ""
                pnl_text = Text(f"{pnl_sign}{profit:.0f}", style=pnl_color)
                pnl_rate = Text(f"{pnl_sign}{profit_rate:.1f}%", style=pnl_color) if profit_rate is not None else Text("--", style="dim")
            else:
                pnl_text = Text("--", style="dim")
                pnl_rate = Text("--", style="dim")

            row = [
                Text(time_str),
                Text(code, style="bold"),
                Text(name[:6]),
                Text(action_text, style=action_color),
                Text(f"{price:.2f}"),
                Text(f"{quantity}"),
                Text(f"{amount:,.0f}"),
                pnl_text,
                pnl_rate,
                Text(strategy[:6], style="dim"),
            ]
            table.add_row(*row, key=str(getattr(t, "id", "")))

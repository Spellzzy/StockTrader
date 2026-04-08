"""持仓概览 Tab Widget

功能:
    - DataTable 展示当前持仓（股票/成本/现价/盈亏/盈亏%/仓位占比）
    - 顶部摘要行（总市值/总盈亏/持仓数）
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static, DataTable
from textual.widget import Widget

from rich.text import Text


class PortfolioTab(Widget):
    """持仓概览 Tab"""

    COLUMNS = [
        ("代码", 12),
        ("名称", 8),
        ("持仓量", 8),
        ("成本价", 10),
        ("现价", 10),
        ("市值", 12),
        ("浮动盈亏", 12),
        ("盈亏%", 8),
        ("今日涨跌%", 10),
    ]

    def compose(self) -> ComposeResult:
        yield Static("", id="portfolio-summary")
        yield DataTable(id="portfolio-table", zebra_stripes=True)

    def on_mount(self) -> None:
        table = self.query_one("#portfolio-table", DataTable)
        table.cursor_type = "row"
        for col_name, width in self.COLUMNS:
            table.add_column(col_name, key=col_name, width=width)

    async def load_data(self) -> None:
        """加载持仓数据"""
        try:
            services = self.app.services
            summary = await services.run_sync(services.portfolio.get_total_summary)
            self._render(summary)
        except Exception as e:
            self._render_error(str(e))

    def _render(self, summary: dict) -> None:
        """渲染持仓表"""
        # 摘要行
        summary_label = self.query_one("#portfolio-summary", Static)
        holding_count = summary.get("holding_count", 0)
        total_cost = summary.get("total_cost", 0)
        total_mv = summary.get("total_market_value", 0)
        total_unrealized = summary.get("total_unrealized_profit", 0)
        total_unrealized_rate = summary.get("total_unrealized_profit_rate", 0)

        color = "red" if total_unrealized >= 0 else "green"
        sign = "+" if total_unrealized >= 0 else ""
        summary_label.update(
            f" 💰 持仓 {holding_count} 只  |  "
            f"总成本 {total_cost:,.0f}  |  "
            f"总市值 {total_mv:,.0f}  |  "
            f"[{color}]浮动盈亏 {sign}{total_unrealized:,.0f} ({sign}{total_unrealized_rate:.2f}%)[/{color}]"
        )

        # 持仓明细
        table = self.query_one("#portfolio-table", DataTable)
        table.clear()

        holdings = summary.get("holdings", [])
        for h in holdings:
            code = h.get("stock_code", "")
            name = h.get("stock_name", "") or code
            qty = h.get("quantity", 0)
            avg_cost = h.get("avg_cost", 0)
            current_price = h.get("current_price", 0)
            market_value = h.get("market_value", 0)
            unrealized = h.get("unrealized_profit", 0)
            unrealized_rate = h.get("unrealized_profit_rate", 0)
            change_pct = h.get("change_percent", 0)

            # 盈亏颜色
            pnl_color = "red" if unrealized >= 0 else "green"
            day_color = "red" if change_pct > 0 else ("green" if change_pct < 0 else "dim")
            pnl_sign = "+" if unrealized >= 0 else ""
            day_sign = "+" if change_pct > 0 else ""

            row = [
                Text(code, style="bold"),
                Text(name[:6]),
                Text(f"{qty}"),
                Text(f"{avg_cost:.2f}"),
                Text(f"{current_price:.2f}", style=day_color),
                Text(f"{market_value:,.0f}"),
                Text(f"{pnl_sign}{unrealized:,.0f}", style=pnl_color),
                Text(f"{pnl_sign}{unrealized_rate:.2f}%", style=pnl_color),
                Text(f"{day_sign}{change_pct:.2f}%", style=day_color),
            ]
            table.add_row(*row, key=code)

    def _render_error(self, msg: str) -> None:
        summary_label = self.query_one("#portfolio-summary", Static)
        summary_label.update(f"[red]加载失败: {msg}[/red]")

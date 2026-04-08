"""AI 分析 Tab Widget

功能:
    - 展示交易统计摘要（胜率/盈亏比/夏普等）
    - 预留 AI 预测评分展示区
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static
from textual.widget import Widget

from rich.text import Text
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns


class AIPanel(Widget):
    """AI 分析面板"""

    def compose(self) -> ComposeResult:
        yield Static(
            "[dim]加载中...[/dim]",
            id="ai-content",
        )

    async def load_data(self) -> None:
        """加载统计分析数据"""
        try:
            services = self.app.services
            summary = await services.run_sync(services.analysis.summary)
            self._render(summary)
        except Exception as e:
            content = self.query_one("#ai-content", Static)
            content.update(f"[red]加载失败: {e}[/red]")

    def _render(self, summary: dict) -> None:
        """渲染分析摘要"""
        content = self.query_one("#ai-content", Static)

        if not summary or summary.get("total_trades", 0) == 0:
            content.update("[dim]暂无交易数据，无法生成分析[/dim]")
            return

        # 构建 Rich 渲染对象
        # 第一栏：交易概况
        t1 = Table(title="📊 交易概况", show_header=False, expand=True, box=None)
        t1.add_column("指标", style="dim", width=12)
        t1.add_column("值", style="bold")
        t1.add_row("总交易", f"{summary.get('total_trades', 0)}")
        t1.add_row("买入", f"{summary.get('buy_count', 0)}")
        t1.add_row("卖出", f"{summary.get('sell_count', 0)}")
        t1.add_row("交易品种", f"{summary.get('stocks_traded', 0)}")
        t1.add_row("活跃期", f"{summary.get('active_period', '--')}")

        # 第二栏：盈亏分析
        t2 = Table(title="💰 盈亏分析", show_header=False, expand=True, box=None)
        t2.add_column("指标", style="dim", width=12)
        t2.add_column("值", style="bold")

        win_rate = summary.get("win_rate", 0)
        wr_color = "red" if win_rate >= 50 else "green"
        t2.add_row("胜率", Text(f"{win_rate:.1f}%", style=wr_color))

        plr = summary.get("profit_loss_ratio", 0)
        plr_color = "red" if plr >= 1 else "green"
        t2.add_row("盈亏比", Text(f"{plr:.2f}", style=plr_color))

        net = summary.get("net_profit", 0)
        net_color = "red" if net >= 0 else "green"
        net_sign = "+" if net >= 0 else ""
        t2.add_row("净盈亏", Text(f"{net_sign}{net:,.0f}", style=net_color))

        t2.add_row("总盈利", Text(f"+{summary.get('total_profit', 0):,.0f}", style="red"))
        t2.add_row("总亏损", Text(f"-{summary.get('total_loss', 0):,.0f}", style="green"))

        # 第三栏：风险指标
        t3 = Table(title="⚠️ 风险指标", show_header=False, expand=True, box=None)
        t3.add_column("指标", style="dim", width=12)
        t3.add_column("值", style="bold")
        t3.add_row("平均盈利", f"+{summary.get('avg_profit', 0):,.0f}")
        t3.add_row("平均亏损", f"-{summary.get('avg_loss', 0):,.0f}")
        t3.add_row("最大盈利", f"+{summary.get('max_profit', 0):,.0f}")
        t3.add_row("最大亏损", f"-{summary.get('max_loss', 0):,.0f}")
        t3.add_row("平均持仓", f"{summary.get('avg_holding_days', 0):.0f}天")
        t3.add_row("手续费", f"{summary.get('total_commission', 0):,.0f}")

        # 组合渲染
        cols = Columns([t1, t2, t3], equal=True, expand=True)
        content.update(cols)

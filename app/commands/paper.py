"""模拟盘命令

    stock-ai paper buy  sh600519 1400 -q 100     # 按价买入
    stock-ai paper buy  sh600519 1400 -a 20000   # 按金额买入（自动折算整手）
    stock-ai paper sell sh600519 1500            # 全部卖出
    stock-ai paper show                          # 账户总览（含实时市值）
    stock-ai paper orders                        # 成交记录
    stock-ai paper reset --yes                   # 重置账户
"""

import typer
from app.commands import console, Table, Panel, box, as_bool, as_int


def register_paper_commands(paper_app: typer.Typer, cli_module=None):
    """注册模拟盘命令"""

    def _broker():
        from app.services.paper_broker import PaperBroker

        return PaperBroker()

    @paper_app.command("buy")
    def paper_buy(
        code: str = typer.Argument(..., help="股票代码"),
        price: float = typer.Argument(..., help="成交价"),
        quantity: int = typer.Option(0, "--quantity", "-q", help="股数（整手，100 的倍数）"),
        amount: float = typer.Option(0.0, "--amount", "-a", help="投入金额（与 -q 二选一）"),
        name: str = typer.Option("", "--name", "-n", help="股票名称"),
    ):
        """模拟买入"""
        from app.services.paper_broker import PaperTradeError

        try:
            order = _broker().buy(code, price, quantity=quantity, amount=amount, name=name)
        except PaperTradeError as e:
            console.print(f"[red]❌ {e}[/red]")
            return

        console.print(
            f"[green]✅ 模拟买入 {order.code} {order.quantity} 股 @ {order.price}[/green]\n"
            f"  金额 {order.amount:,.2f}  佣金 {order.commission:,.2f}  "
            f"剩余现金 {_broker().account.cash:,.2f}"
        )

    @paper_app.command("sell")
    def paper_sell(
        code: str = typer.Argument(..., help="股票代码"),
        price: float = typer.Argument(..., help="成交价"),
        quantity: int = typer.Option(0, "--quantity", "-q", help="卖出股数（0=全部）"),
    ):
        """模拟卖出"""
        from app.services.paper_broker import PaperTradeError

        try:
            order = _broker().sell(code, price, quantity=quantity)
        except PaperTradeError as e:
            console.print(f"[red]❌ {e}[/red]")
            return

        profit_color = "green" if order.realized_profit >= 0 else "red"
        console.print(
            f"[green]✅ 模拟卖出 {order.code} {order.quantity} 股 @ {order.price}[/green]\n"
            f"  金额 {order.amount:,.2f}  佣金 {order.commission:,.2f}  印花税 {order.tax:,.2f}\n"
            f"  本笔盈亏: [{profit_color}]{order.realized_profit:+,.2f}[/{profit_color}]"
        )

    @paper_app.command("show")
    def paper_show():
        """账户总览（持仓市值按实时行情计算）"""
        broker = _broker()
        positions = broker.positions()

        prices = {}
        if positions:
            try:
                from app.services.market_service import MarketService

                prices = MarketService().get_quote(*[p.code for p in positions])
            except Exception:
                prices = {}

        summary = broker.summary(prices={code: (data or {}).get("price", 0) for code, data in prices.items()})

        ret_color = "green" if summary["total_return"] >= 0 else "red"
        console.print(
            Panel(
                f"总资产: {summary['equity']:,.2f}   可用现金: {summary['cash']:,.2f}\n"
                f"持仓市值: {summary['market_value']:,.2f}   持仓数: {summary['position_count']}\n"
                f"总收益: [{ret_color}]{summary['total_return']:+.2f}%[/{ret_color}]\n"
                f"已实现: {summary['realized_profit']:+,.2f}   浮动: {summary['unrealized_profit']:+,.2f}",
                title="💼 模拟盘账户",
                border_style="cyan",
            )
        )

        if not positions:
            console.print("[dim]当前无持仓[/dim]")
            return

        table = Table(box=box.ROUNDED, header_style="bold cyan")
        table.add_column("代码")
        table.add_column("数量", justify="right")
        table.add_column("成本", justify="right")
        table.add_column("现价", justify="right")
        table.add_column("市值", justify="right")
        table.add_column("浮动盈亏", justify="right")

        for position in positions:
            price = float((prices.get(position.code) or {}).get("price", 0) or 0)
            value = position.quantity * (price or position.avg_cost)
            unrealized = (price - position.avg_cost) * position.quantity if price else 0
            color = "green" if unrealized >= 0 else "red"
            table.add_row(
                position.code,
                str(position.quantity),
                f"{position.avg_cost:.2f}",
                f"{price:.2f}" if price else "-",
                f"{value:,.2f}",
                f"[{color}]{unrealized:+,.2f}[/{color}]",
            )
        console.print(table)

    @paper_app.command("orders")
    def paper_orders(
        limit: int = typer.Option(20, "--limit", "-l", help="显示条数"),
    ):
        """成交记录"""
        limit = as_int(limit, default=20)
        orders = _broker().orders(limit=limit)

        if not orders:
            console.print("[dim]暂无成交记录[/dim]")
            return

        table = Table(title="📒 模拟盘成交", box=box.ROUNDED, header_style="bold cyan")
        table.add_column("ID", justify="right")
        table.add_column("日期")
        table.add_column("代码")
        table.add_column("方向")
        table.add_column("价格", justify="right")
        table.add_column("数量", justify="right")
        table.add_column("盈亏", justify="right")

        for order in orders:
            side_color = "green" if order.side == "buy" else "yellow"
            table.add_row(
                str(order.id),
                order.trade_date,
                order.code,
                f"[{side_color}]{'买入' if order.side == 'buy' else '卖出'}[/{side_color}]",
                f"{order.price:.2f}",
                str(order.quantity),
                f"{order.realized_profit:+,.2f}" if order.side == "sell" else "-",
            )
        console.print(table)

    @paper_app.command("reset")
    def paper_reset(
        yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
        initial_cash: float = typer.Option(0.0, "--cash", help="重置后的初始资金（0=沿用配置）"),
    ):
        """重置模拟盘账户"""
        yes = as_bool(yes)
        if not yes:
            console.print("[yellow]这会清空模拟盘所有记录，确认请加 --yes[/yellow]")
            return

        broker = _broker()
        broker.reset(initial_cash=initial_cash or None)
        console.print(f"[green]✅ 模拟盘已重置，初始资金 {broker.account.initial_cash:,.2f}[/green]")

    if cli_module is not None:
        cli_module.paper_buy = paper_buy
        cli_module.paper_sell = paper_sell
        cli_module.paper_show = paper_show
        cli_module.paper_orders = paper_orders
        cli_module.paper_reset = paper_reset

"""回测引擎命令 — 从 cli.py 拆分

包含回测运行、策略列表、多策略对比及回测结果渲染。
"""

import typer
from app.commands import console, Table, Panel, box


def register_backtest_commands(backtest_app: typer.Typer, cli_module=None):
    """将所有回测子命令注册到 backtest_app 上

    Args:
        backtest_app: typer.Typer 实例
        cli_module: cli 模块引用（用于将函数挂回 cli 模块，供 shortcuts.py 调用）
    """

    @backtest_app.command("run")
    def backtest_run(
        code: str = typer.Argument(..., help="股票代码 (如 600519, 支持自动识别sh/sz)"),
        strategy: str = typer.Option("macd_cross", "--strategy", "-s", help="策略名称"),
        days: int = typer.Option(180, "--days", "-d", help="回测天数"),
        capital: float = typer.Option(100000, "--capital", "-k", help="初始资金(元)"),
        stop_loss: float = typer.Option(0.0, "--stop-loss", "--sl", help="止损比例 (0.05=5%)"),
        take_profit: float = typer.Option(0.0, "--take-profit", "--tp", help="止盈比例 (0.1=10%)"),
        position: float = typer.Option(1.0, "--position", help="仓位比例 (0~1)"),
        chart: bool = typer.Option(False, "--chart", "-g", help="显示回测图表"),
    ):
        """运行回测"""
        from app.services.backtest_service import BacktestService
        from app.config import get_config

        # 从配置读取默认值
        config = get_config()
        bt_cfg = config.get("backtest", {})

        # 参数未指定时使用配置默认值
        if capital == 100000 and bt_cfg.get("initial_capital"):
            capital = bt_cfg["initial_capital"]
        if stop_loss == 0.0 and bt_cfg.get("stop_loss"):
            stop_loss = bt_cfg["stop_loss"]
        if take_profit == 0.0 and bt_cfg.get("take_profit"):
            take_profit = bt_cfg["take_profit"]
        if position == 1.0 and bt_cfg.get("position_size"):
            position = bt_cfg["position_size"]

        commission_rate = bt_cfg.get("commission_rate", 0.0003)
        tax_rate = bt_cfg.get("tax_rate", 0.001)

        console.print(f"[cyan]📊 正在回测 {code} | 策略: {strategy} | {days}天 | 资金: {capital:,.0f}元[/cyan]")
        if stop_loss > 0 or take_profit > 0:
            sl_str = f"止损{stop_loss*100:.1f}%" if stop_loss > 0 else "无"
            tp_str = f"止盈{take_profit*100:.1f}%" if take_profit > 0 else "无"
            console.print(f"[dim]  风控: {sl_str} / {tp_str} | 仓位: {position*100:.0f}%[/dim]")

        with console.status("[cyan]获取数据 → 计算指标 → 模拟交易 → 生成报告...[/cyan]"):
            svc = BacktestService()
            result = svc.run(
                code=code,
                strategy=strategy,
                days=days,
                initial_capital=capital,
                commission_rate=commission_rate,
                tax_rate=tax_rate,
                stop_loss=stop_loss,
                take_profit=take_profit,
                position_size=position,
            )

        _render_backtest_result(result)

        if chart and result.total_days > 0:
            from app.visualization.charts import ChartService

            console.print("[dim]📈 正在绘制回测图表...[/dim]")
            cs = ChartService()
            path1 = cs.plot_backtest_equity(result)
            if path1:
                console.print(f"[green]✅ 权益曲线已保存: {path1}[/green]")
            path2 = cs.plot_backtest_trades(result)
            if path2:
                console.print(f"[green]✅ 交易明细图已保存: {path2}[/green]")

    @backtest_app.command("list")
    def backtest_strategies():
        """查看可用的回测策略"""
        from app.services.strategy import list_strategies

        strategies = list_strategies()

        table = Table(
            title="📋 可用回测策略",
            box=box.ROUNDED,
            header_style="bold cyan",
        )
        table.add_column("名称", width=14, style="bold")
        table.add_column("描述", width=30)
        table.add_column("类名", width=22, style="dim")

        for s in strategies:
            table.add_row(s["name"], s["description"], s["class"])

        console.print(table)
        console.print(
            "\n[dim]用法示例:\n"
            "  stock-ai bt sh600519                           # 默认MACD策略回测\n"
            "  stock-ai bt sh600519 -s rsi -d 365             # RSI策略回测365天\n"
            "  stock-ai bt sh600519 -s turtle --sl 0.05 -g    # 海龟策略+5%止损+出图\n"
            "  stock-ai bt sh600519 -s ma_cross -k 200000     # 均线策略+20万资金\n"
            "[/dim]"
        )

    @backtest_app.command("compare")
    def backtest_compare(
        code: str = typer.Argument(..., help="股票代码"),
        days: int = typer.Option(180, "--days", "-d", help="回测天数"),
        capital: float = typer.Option(100000, "--capital", "-k", help="初始资金"),
        strategies: str = typer.Option(
            "macd_cross,ma_cross,rsi,boll,kdj,dual_macd,turtle",
            "--strategies", "-s",
            help="策略列表(逗号分隔)",
        ),
    ):
        """多策略对比回测"""
        from app.services.backtest_service import BacktestService

        strategy_list = [s.strip() for s in strategies.split(",") if s.strip()]
        console.print(f"[cyan]📊 多策略对比回测 {code} | {days}天 | {len(strategy_list)}个策略[/cyan]")

        svc = BacktestService()
        results = []

        for strat in strategy_list:
            with console.status(f"[cyan]回测 {strat}...[/cyan]"):
                try:
                    result = svc.run(code=code, strategy=strat, days=days, initial_capital=capital)
                    results.append(result)
                except Exception as e:
                    console.print(f"[yellow]⚠️ 策略 {strat} 失败: {e}[/yellow]")

        if not results:
            console.print("[red]❌ 所有策略均失败[/red]")
            return

        # 对比表
        table = Table(
            title=f"📊 {code} 多策略对比 ({days}天)",
            box=box.ROUNDED,
            show_lines=True,
            header_style="bold cyan",
        )
        table.add_column("排名", width=4, justify="center")
        table.add_column("策略", width=14)
        table.add_column("总收益", width=10, justify="right")
        table.add_column("年化", width=8, justify="right")
        table.add_column("超额", width=8, justify="right")
        table.add_column("最大回撤", width=8, justify="right")
        table.add_column("夏普", width=6, justify="right")
        table.add_column("胜率", width=6, justify="right")
        table.add_column("盈亏比", width=6, justify="right")
        table.add_column("交易", width=5, justify="right")
        table.add_column("评分", width=8, justify="center")

        # 按总收益排序
        results.sort(key=lambda r: r.total_return, reverse=True)

        for i, r in enumerate(results, 1):
            ret_color = "green" if r.total_return >= 0 else "red"
            excess_color = "green" if r.excess_return >= 0 else "red"
            sharpe_color = "green" if r.sharpe_ratio >= 1 else "yellow" if r.sharpe_ratio >= 0 else "red"
            win_color = "green" if r.win_rate >= 50 else "red"

            # 简单评分
            score = r.sharpe_ratio * 30 + (1 if r.total_return > 0 else -1) * 20 + min(r.win_rate, 80) * 0.5
            if r.max_drawdown > 0:
                score -= r.max_drawdown * 0.5
            stars = min(5, max(1, int(score / 20) + 3))
            stars_str = "⭐" * stars

            table.add_row(
                str(i),
                r.strategy_name,
                f"[{ret_color}]{r.total_return:+.2f}%[/{ret_color}]",
                f"[{ret_color}]{r.annual_return:+.2f}%[/{ret_color}]",
                f"[{excess_color}]{r.excess_return:+.2f}%[/{excess_color}]",
                f"[red]{r.max_drawdown:.2f}%[/red]",
                f"[{sharpe_color}]{r.sharpe_ratio:.2f}[/{sharpe_color}]",
                f"[{win_color}]{r.win_rate:.1f}%[/{win_color}]",
                f"{r.profit_loss_ratio:.2f}",
                str(r.total_trades),
                stars_str,
            )

        console.print(table)

        # 基准信息
        if results:
            console.print(f"[dim]基准(买入持有): {results[0].benchmark_return:+.2f}% | "
                           f"初始资金: {capital:,.0f}元[/dim]")

        # 冠军
        best = results[0]
        console.print(f"\n[bold green]🏆 最优策略: {best.strategy_name} "
                       f"(收益 {best.total_return:+.2f}%, 夏普 {best.sharpe_ratio:.2f})[/bold green]")

    # 将函数挂回 cli_module，供 shortcuts.py 通过 cli_module.xxx 调用
    if cli_module is not None:
        cli_module.backtest_run = backtest_run
        cli_module.backtest_strategies = backtest_strategies
        cli_module.backtest_compare = backtest_compare
        cli_module._render_backtest_result = _render_backtest_result


def _render_backtest_result(result):
    """渲染回测结果为 Rich 面板"""
    if result.total_days == 0:
        console.print("[red]❌ 回测失败 — 数据不足或策略无信号[/red]")
        return

    # 信号颜色
    ret_color = "green" if result.total_return >= 0 else "red"
    excess_color = "green" if result.excess_return >= 0 else "red"
    sharpe_color = "green" if result.sharpe_ratio >= 1 else "yellow" if result.sharpe_ratio >= 0 else "red"
    win_color = "green" if result.win_rate >= 50 else "red"

    # 评级
    if result.sharpe_ratio >= 2 and result.total_return > 0:
        grade = "⭐⭐⭐⭐⭐ 优秀"
    elif result.sharpe_ratio >= 1 and result.total_return > 0:
        grade = "⭐⭐⭐⭐ 良好"
    elif result.sharpe_ratio >= 0.5 and result.total_return > 0:
        grade = "⭐⭐⭐ 一般"
    elif result.total_return > 0:
        grade = "⭐⭐ 及格"
    else:
        grade = "⭐ 亏损"

    lines = [
        f"[bold]📋 基本信息[/bold]",
        f"  策略: [bold]{result.strategy_name}[/bold] ({result.strategy_desc})",
        f"  区间: {result.start_date} → {result.end_date} ({result.total_days}个交易日)",
        f"  初始资金: {result.initial_capital:,.0f}元  终值: [{ret_color}]{result.final_capital:,.0f}元[/{ret_color}]",
        f"  净利润: [{ret_color}]{result.net_profit:+,.2f}元[/{ret_color}]",
        "",
        f"[bold]📊 收益指标[/bold]",
        f"  总收益率: [{ret_color}]{result.total_return:+.2f}%[/{ret_color}]  "
        f"年化收益: [{ret_color}]{result.annual_return:+.2f}%[/{ret_color}]",
        f"  基准收益: {result.benchmark_return:+.2f}% (买入持有)",
        f"  超额收益: [{excess_color}]{result.excess_return:+.2f}%[/{excess_color}]",
        "",
        f"[bold]📉 风险指标[/bold]",
        f"  最大回撤: [red]{result.max_drawdown:.2f}%[/red] ({result.max_drawdown_amount:,.0f}元)",
        f"  夏普比率: [{sharpe_color}]{result.sharpe_ratio:.2f}[/{sharpe_color}]  "
        f"卡玛比率: {result.calmar_ratio:.2f}",
        "",
        f"[bold]🎯 交易统计[/bold]",
        f"  总交易: {result.total_trades}笔  "
        f"(盈 {result.win_count} / 亏 {result.loss_count})",
        f"  胜率: [{win_color}]{result.win_rate:.1f}%[/{win_color}]  "
        f"盈亏比: {result.profit_loss_ratio:.2f}",
        f"  平均盈利: [green]{result.avg_profit:+.2f}%[/green]  "
        f"平均亏损: [red]{result.avg_loss:+.2f}%[/red]",
        f"  最大盈利: [green]{result.max_profit:+.2f}%[/green]  "
        f"最大亏损: [red]{result.max_loss:+.2f}%[/red]",
        f"  平均持仓: {result.avg_holding_days:.1f}天",
        "",
        f"[bold]💰 费用[/bold]",
        f"  手续费: {result.total_commission:,.2f}元  "
        f"印花税: {result.total_tax:,.2f}元  "
        f"合计: {result.total_commission + result.total_tax:,.2f}元",
        "",
        f"[bold]综合评级: {grade}[/bold]",
    ]

    # 止损/止盈提示
    if result.stop_loss > 0 or result.take_profit > 0:
        sl_str = f"止损{result.stop_loss*100:.1f}%" if result.stop_loss > 0 else "无"
        tp_str = f"止盈{result.take_profit*100:.1f}%" if result.take_profit > 0 else "无"
        lines.insert(4, f"  风控: {sl_str} / {tp_str}")

    console.print(Panel(
        "\n".join(lines),
        title=f"[bold]📈 {result.code} 回测报告[/bold]",
        border_style=ret_color,
        padding=(1, 2),
    ))

    # 交易明细表 (如果笔数不多则显示)
    if result.trades and len(result.trades) <= 30:
        table = Table(
            title="📝 交易明细",
            box=box.ROUNDED,
            show_lines=True,
            header_style="bold cyan",
        )
        table.add_column("#", style="dim", width=3)
        table.add_column("买入日期", width=10)
        table.add_column("买入价", width=10, justify="right")
        table.add_column("卖出日期", width=10)
        table.add_column("卖出价", width=10, justify="right")
        table.add_column("数量", width=8, justify="right")
        table.add_column("盈亏", width=12, justify="right")
        table.add_column("收益率", width=8, justify="right")
        table.add_column("持仓", width=6, justify="right")
        table.add_column("退出", width=6)

        reason_map = {"signal": "信号", "stop_loss": "止损", "take_profit": "止盈", "end": "到期"}
        for i, t in enumerate(result.trades, 1):
            p_color = "green" if t.profit >= 0 else "red"
            table.add_row(
                str(i),
                t.entry_date[5:],  # MM-DD
                f"{t.entry_price:.2f}",
                t.exit_date[5:],
                f"{t.exit_price:.2f}",
                f"{t.quantity:,}",
                f"[{p_color}]{t.profit:+,.2f}[/{p_color}]",
                f"[{p_color}]{t.profit_rate:+.2f}%[/{p_color}]",
                f"{t.holding_days}天",
                reason_map.get(t.exit_reason, t.exit_reason),
            )

        console.print(table)

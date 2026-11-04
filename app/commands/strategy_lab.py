"""策略实验室命令 — signal-report / optimize

    stock-ai signal-report sz002555 --all      # 7 个策略的信号质量对比
    stock-ai optimize sz002555 -s ma_cross     # 参数网格 + 滚动窗口验证
"""

import typer
from app.commands import console, Table, Panel, box, as_bool, as_int


def do_signal_report(code: str, all_strategies: bool = False, days: int = 250, horizon: int = 5):
    """信号质量报告"""
    from app.services.strategy_lab import StrategyLab

    all_strategies = as_bool(all_strategies)
    days = as_int(days, 250)
    horizon = as_int(horizon, 5)

    lab = StrategyLab()
    with console.status(f"[cyan]评估 {code} 的策略信号...[/cyan]"):
        results = (
            lab.analyze_all(code, days=days, horizon=horizon)
            if all_strategies
            else [lab.analyze(code, "macd_cross", days=days, horizon=horizon)]
        )

    results = [r for r in results if not r.get("error")]
    if not results:
        console.print("[red]❌ 没有可用的评估结果（行情数据不足？）[/red]")
        return

    from app.commands.tables import Column, render_table

    columns = [
        Column("strategy", "策略", 14, priority=0, justify="left", min_width=12),
        Column("signals", "信号数", 8, priority=1, min_width=7),
        Column("hit", "命中率", 9, priority=2, min_width=8),
        Column("in", "样本内", 9, priority=3, min_width=8),
        Column("out", "样本外", 9, priority=4, min_width=8),
        Column("decay", "衰减", 8, priority=5, min_width=7),
        Column("trades", "配对交易", 9, priority=6),
        Column("win", "胜率", 8, priority=7),
        Column("hold", "平均持仓", 10, priority=8),
    ]

    rows = []
    for r in results:
        hit = r.get("hit_rate", 0)
        hit_color = "green" if hit >= 55 else "yellow" if hit >= 45 else "red"
        decay = r.get("decay", 0)
        decay_color = "red" if decay > 15 else "dim"
        rows.append({
            "strategy": r["strategy"],
            "signals": str(r.get("total_signals", 0)),
            "hit": f"[{hit_color}]{hit:.1f}%[/{hit_color}]",
            "in": f"{r.get('in_sample_hit_rate', 0):.1f}%",
            "out": f"{r.get('out_of_sample_hit_rate', 0):.1f}%",
            "decay": f"[{decay_color}]{decay:+.1f}[/{decay_color}]",
            "trades": str(r.get("paired_trades", 0)),
            "win": f"{r.get('win_rate', 0):.1f}%",
            "hold": f"{r.get('avg_holding_days', 0):.1f}天",
        })

    console.print(render_table(
        columns, rows,
        title=f"🔬 {code} 策略信号质量（未来{horizon}日方向命中率）",
        width=console.width, show_lines=True,
    ))
    console.print(
        "[dim]命中率 = 信号方向与未来 N 日实际涨跌一致的比例；50% 约等于抛硬币。\n"
        "衰减 = 样本内 - 样本外，越大越像过拟合。基准(买入持有): "
        f"{results[0].get('benchmark_return', 0):+.2f}%[/dim]"
    )


def do_optimize(code: str, strategy: str = "ma_cross", days: int = 180, max_combos: int = 8, folds: int = 3):
    """参数寻优 + rolling walk-forward"""
    from app.services.strategy_lab import StrategyLab

    days = as_int(days, 180)
    max_combos = as_int(max_combos, 8)
    folds = as_int(folds, 3)

    lab = StrategyLab()
    with console.status(f"[cyan]网格搜索 {strategy} 参数（{max_combos} 组）...[/cyan]"):
        grid = lab.grid_search(code, strategy, days=days, max_combos=max_combos)

    if not grid["rows"]:
        console.print("[red]❌ 参数网格没有跑出有效结果[/red]")
        return

    table = Table(
        title=f"🎯 {code} / {strategy} 参数网格（共 {grid['combos']} 组）",
        box=box.ROUNDED, header_style="bold cyan", show_lines=True,
    )
    table.add_column("参数")
    table.add_column("总收益", justify="right")
    table.add_column("最大回撤", justify="right")
    table.add_column("夏普", justify="right")
    table.add_column("交易", justify="right")

    for row in grid["rows"][:8]:
        ret = row["total_return"]
        color = "green" if ret >= 0 else "red"
        params = ", ".join(f"{k}={v}" for k, v in row["params"].items()) or "默认"
        table.add_row(
            params,
            f"[{color}]{ret:+.2f}%[/{color}]",
            f"{row['max_drawdown']:.2f}%",
            f"{row['sharpe_ratio']:.2f}",
            str(row["total_trades"]),
        )
    console.print(table)

    with console.status("[cyan]滚动窗口验证（训练段选参数，测试段验证）...[/cyan]"):
        wf = lab.walk_forward(code, strategy, days=days, n_splits=folds, max_combos=max_combos)

    if wf.get("error"):
        console.print(f"[yellow]⚠️ 滚动验证跳过: {wf['error']}[/yellow]")
        return

    wf_table = Table(
        title="🔁 Rolling Walk-Forward",
        box=box.ROUNDED, header_style="bold cyan", show_lines=True,
    )
    wf_table.add_column("折")
    wf_table.add_column("训练段命中率", justify="right")
    wf_table.add_column("样本外命中率", justify="right")
    wf_table.add_column("本折最优参数")
    wf_table.add_column("样本外信号", justify="right")
    wf_table.add_column("可靠性")

    for f in wf["folds"]:
        params = ", ".join(f"{k}={v}" for k, v in f["best_params"].items()) or "默认"
        wf_table.add_row(
            str(f["fold"]),
            f"{f['train_hit_rate']:.1f}%",
            f"{f['test_hit_rate']:.1f}%",
            params,
            str(f["test_signals"]),
            "[green]可用[/green]" if f["reliable"] else "[yellow]样本不足[/yellow]",
        )
    console.print(wf_table)

    if wf["mean_test_hit_rate"] is None:
        console.print(Panel(
            f"[yellow]{wf['conclusion']}[/yellow]\n\n"
            f"有效折数: {wf['reliable_folds']}/{wf['total_folds']} "
            f"（每折至少需要 {wf['min_signals']} 个信号）",
            title="📉 过拟合检查",
            border_style="yellow",
        ))
        return

    decay_color = "red" if wf["decay"] > 15 else "green"
    console.print(Panel(
        f"平均训练段命中率: {wf['mean_train_hit_rate']:.2f}%\n"
        f"平均样本外命中率: {wf['mean_test_hit_rate']:.2f}%\n"
        f"衰减: [{decay_color}]{wf['decay']:+.2f}[/{decay_color}]\n"
        f"有效折数: {wf['reliable_folds']}/{wf['total_folds']}",
        title="📉 过拟合检查",
        border_style=decay_color,
    ))
    console.print(
        "[dim]样本外明显低于训练段说明参数是在历史里挑出来的，不要直接用最优参数实盘。[/dim]"
    )


def register_lab_commands(app: typer.Typer):
    """注册顶层策略实验室命令"""

    @app.command("signal-report", help="策略信号质量报告 (缩写: sr)")
    def signal_report(
        code: str = typer.Argument(..., help="股票代码"),
        all_strategies: bool = typer.Option(False, "--all", "-a", help="评估全部 7 个策略"),
        days: int = typer.Option(250, "--days", "-d", help="K线天数"),
        horizon: int = typer.Option(5, "--horizon", "-n", help="评估未来几日"),
    ):
        do_signal_report(code, all_strategies, days, horizon)

    @app.command("sr", hidden=True)
    def alias_sr(
        code: str = typer.Argument(..., help="股票代码"),
        all_strategies: bool = typer.Option(False, "--all", "-a", help="评估全部策略"),
    ):
        do_signal_report(code, all_strategies)

    @app.command("optimize", help="策略参数寻优 + 滚动验证 (缩写: opt)")
    def optimize(
        code: str = typer.Argument(..., help="股票代码"),
        strategy: str = typer.Option("ma_cross", "--strategy", "-s", help="策略名"),
        days: int = typer.Option(180, "--days", "-d", help="回测天数"),
        max_combos: int = typer.Option(8, "--max-combos", "-m", help="最多参数组合数"),
        folds: int = typer.Option(3, "--folds", "-f", help="滚动窗口折数"),
    ):
        do_optimize(code, strategy, days, max_combos, folds)

    @app.command("opt", hidden=True)
    def alias_opt(
        code: str = typer.Argument(..., help="股票代码"),
        strategy: str = typer.Option("ma_cross", "--strategy", "-s", help="策略名"),
    ):
        do_optimize(code, strategy)

"""可视化报告命令 — stock-ai report / rp

生成单文件 HTML 报告（图表内嵌，可直接双击打开或分享）。
"""

from app.commands import console, Panel, as_bool


def do_report(
    output_dir: str = "",
    with_backtest: bool = False,
    backtest_code: str = "",
    days: int = 180,
    with_chart: bool = True,
):
    """生成 HTML 可视化报告

    Args:
        output_dir: 输出目录，默认 data/reports
        with_backtest: 是否额外跑多策略回测对比
        backtest_code: 回测标的（--with-bt 时必填）
        days: 回测天数
        with_chart: 是否生成图表
    """
    from app.visualization.report import DEFAULT_OUTPUT_DIR, HTMLReport

    with_backtest = as_bool(with_backtest)
    with_chart = as_bool(with_chart)

    if with_backtest and not backtest_code:
        console.print("[yellow]⚠️ --with-bt 需要同时指定 --bt-code[/yellow]")
        return

    builder = HTMLReport(output_dir=output_dir or DEFAULT_OUTPUT_DIR)

    with console.status("[cyan]正在生成可视化报告...[/cyan]"):
        path = builder.build(
            with_backtest=with_backtest,
            backtest_code=backtest_code,
            days=days,
            with_chart=with_chart,
        )

    console.print(
        Panel(
            f"报告已生成:\n[bold]{path}[/bold]\n\n"
            "[dim]单文件 HTML，图表已内嵌，可直接用浏览器打开[/dim]",
            title="📊 可视化报告",
            border_style="cyan",
        )
    )

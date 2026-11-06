"""今日目标最高价命令 — stock-ai target-high

统计分位数口径，不训练模型；输出区间、触及概率与回测质量。
"""

import json

import typer

from app.commands import console, Table, box


def register_forecast_commands(app: typer.Typer):
    @app.command("target-high", help="今日目标最高价（统计区间 + 概率，不训练模型）")
    def target_high(
        code: str = typer.Argument(..., help="股票代码，如 600519 / sh600519"),
        as_json: bool = typer.Option(False, "--json", help="输出原始 JSON"),
    ):
        from app.services.high_forecast_service import HighForecastService

        try:
            d = HighForecastService().forecast(code)
        except ValueError as e:
            console.print(f"[red]❌ {e}[/red]")
            raise typer.Exit(code=1)

        if as_json:
            console.print(json.dumps(d, ensure_ascii=False, default=str))
            return

        phase_cn = {"premarket": "盘前 · 全天", "intraday": "盘中 · 剩余时段", "closed": "已收盘"}.get(
            d["phase"], d["phase"]
        )
        console.print(
            f"[bold]{d['name'] or d['code']} ({d['code']})[/bold] · {phase_cn}"
            f" · 现价 {d['price']} · 今日最高 {d['day_high']}"
        )

        table = Table(title="目标高点区间", box=box.SIMPLE_HEAVY)
        table.add_column("口径")
        table.add_column("目标价", justify="right")
        table.add_column("相对现价", justify="right")
        table.add_column("触及概率", justify="right")
        for key, label in (("p50", "P50 下沿"), ("p75", "P75 中枢"), ("p90", "P90 上沿")):
            table.add_row(
                label, str(d["targets"][key]),
                f"{d['upside_pct'][key]:+.2f}%",
                f"{d['probabilities'][key] * 100:.0f}%",
            )
        console.print(table)

        q = d["quality"]
        console.print(
            f"[dim]历史样本 {d['basis']['sample_days']} 日 · 振幅 P75 "
            f"{d['basis']['amplitude_p75_pct']}% · 时间衰减 {d['basis']['decay']}"
            f" · 涨停上限 {d['basis']['limit_price'] or '不适用'}[/dim]"
        )
        if q.get("samples"):
            console.print(
                f"[dim]walk-forward {q['samples']} 日：P75 触及率 {q['touch_p75'] * 100:.0f}%"
                f" · 区间覆盖率 {q['coverage'] * 100:.0f}% · MAE {q['mae_pct']}%"
                f" vs 昨日高点基线 {q['baseline_mae_pct']}%"
                f"（{'优于基线' if q['better_than_baseline'] else '不优于基线'}）[/dim]"
            )
        console.print(f"[yellow]{d['note']}[/yellow]")

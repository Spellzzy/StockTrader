"""全市场摘选命令 — stock-ai scan-market / scan-history

只挂主 app，不进 shortcuts/registry（避免影响既有命令索引）。
完整的定时/推送/落盘流程见 scripts/scheduled_screen.py。
"""

import typer

from app.commands import console, Panel, Table, box


def register_market_scan_commands(app: typer.Typer):
    """注册全市场摘选命令"""

    @app.command("scan-market", help="全市场摘选：预筛 → 条件筛选 → 打分落库")
    def scan_market(
        pool: str = typer.Option(
            "", "--pool", "-p",
            help="股票池: all_a / watchlist / portfolio / file:... / 逗号分隔代码",
        ),
        top: int = typer.Option(0, "--top", help="覆盖展示 Top N（0=用配置）"),
        force: bool = typer.Option(False, "--force", help="忽略今日同参数缓存，强制重跑"),
        no_save: bool = typer.Option(False, "--no-save", help="不落库（调试用）"),
        report: bool = typer.Option(False, "--report", help="额外把 Markdown 报告落到 data/reports"),
    ):
        from datetime import datetime
        from pathlib import Path

        from app.config import get_config
        from app.db.database import init_db
        from app.services.market_scan_service import MarketScanService, build_report

        init_db()
        cfg = dict(get_config().get("market_scan", {}) or {})
        if top > 0:
            cfg["top_n"] = top

        console.print("[dim]全市场摘选可能需要几分钟（预筛 + 候选 K 线评估）…[/dim]")
        result = MarketScanService(config=cfg).run(
            pool=pool or None, force=force, save=not no_save,
        )

        cached = " · 复用今日缓存" if result.get("cached") else ""
        console.print(Panel(
            f"池 [bold]{result['pool']}[/bold]：{result['universe_count']} 只"
            f" → 预筛 {result['candidate_count']} 只"
            f" → 命中 [bold]{result['hit_count']}[/bold] 只\n"
            f"耗时 {result['duration_seconds']}s{cached}",
            title="🔎 全市场摘选", border_style="cyan",
        ))

        hits = result.get("hits") or []
        if hits:
            table = Table(box=box.SIMPLE_HEAVY)
            table.add_column("#", width=4)
            table.add_column("代码", style="cyan")
            table.add_column("名称")
            table.add_column("现价", justify="right")
            table.add_column("命中", justify="right")
            table.add_column("条件")
            for i, h in enumerate(hits, 1):
                reasons = "、".join(str(r[0]) for r in (h.get("matched") or [])[:3])
                table.add_row(
                    str(i), h["code"], h.get("name", ""),
                    f"{h.get('price', '-')}",
                    f"{h.get('matched_count', 0)}/{h.get('total_rules', 0)}",
                    reasons,
                )
            console.print(table)
        else:
            console.print("[yellow]本次没有股票满足当前条件组合[/yellow]")

        if report:
            path = Path("data/reports") / f"screen_{datetime.now():%Y%m%d}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(build_report(result), encoding="utf-8")
            console.print(f"[dim]报告已落盘: {path}[/dim]")

        console.print("[dim]* 仅为技术面信号，不构成投资建议[/dim]")

    @app.command("scan-history", help="查看历史全市场摘选记录")
    def scan_history(
        limit: int = typer.Option(10, "--limit", "-n", help="显示条数"),
    ):
        from app.db.database import init_db
        from app.services.market_scan_service import MarketScanService

        init_db()
        rows = MarketScanService().list_runs(limit=limit)
        if not rows:
            console.print("[yellow]暂无扫描记录[/yellow]")
            return

        table = Table(title="🗂 全市场摘选历史", box=box.SIMPLE_HEAVY)
        table.add_column("ID", justify="right")
        table.add_column("日期")
        table.add_column("池", style="cyan")
        table.add_column("候选", justify="right")
        table.add_column("命中", justify="right")
        table.add_column("耗时(s)", justify="right")
        for r in rows:
            table.add_row(
                str(r["id"]), r["run_date"], r["pool"],
                str(r["candidate_count"]), str(r["hit_count"]),
                f"{r['duration_seconds']:.1f}",
            )
        console.print(table)

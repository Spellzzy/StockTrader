"""选股命令 — stock-ai screen / sn

读取 config.yaml 中 screener 配置，对股票池逐个评估买入/卖出条件，输出命中清单。
"""

from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    MofNCompleteColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from app.commands import console, Table, Panel, box
from app.theme import get_up, get_down


def do_screen(
    side: str = "both",
    pool: str = "",
    mode_buy: str = "",
    mode_sell: str = "",
    push: bool = False,
    list_conditions: bool = False,
):
    """执行选股扫描

    Args:
        side: "buy" / "sell" / "both"
        pool: 股票池覆盖（"watchlist" / "portfolio" / "all_a" / "file:..." / "code1,code2"）
        mode_buy: 买入聚合模式覆盖（all / any / atleast:N）
        mode_sell: 卖出聚合模式覆盖
        push: 是否推送到通知渠道
        list_conditions: 仅列出所有可用条件
    """
    from app.services.screener_service import ScreenerService, CONDITION_REGISTRY

    # 列出所有条件
    if list_conditions:
        table = Table(title="📋 可用条件列表", box=box.SIMPLE_HEAVY)
        table.add_column("条件名", style="cyan", width=20)
        table.add_column("描述", style="white")
        for name in sorted(CONDITION_REGISTRY.keys()):
            fn = CONDITION_REGISTRY[name]
            doc = (fn.__doc__ or "").strip().split("\n")[0]
            table.add_row(name, doc)
        console.print(table)
        return

    svc = ScreenerService()
    cfg = svc.cfg
    if not cfg:
        console.print(
            "[yellow]⚠️ 未在 config.yaml 中找到 screener 配置段，"
            "请参考 config.yaml.example 添加配置[/yellow]"
        )
        return

    # 覆盖配置
    if mode_buy:
        cfg.setdefault("buy", {})["mode"] = mode_buy
    if mode_sell:
        cfg.setdefault("sell", {})["mode"] = mode_sell

    # 解析股票池
    pool_arg = pool or cfg.get("pool", "watchlist")

    # all_a 首次构建提示
    if pool_arg.startswith("all_a"):
        from app.services.pool_loader import get_cache_info
        info = get_cache_info()
        if info is None or pool_arg.endswith(":refresh"):
            console.print(
                "[yellow]⚠️ 全A代码缓存不存在或需刷新，先构建（首次约1~3分钟）...[/yellow]"
            )
            _build_pool_cache()

    with console.status("[cyan]📋 加载股票池...[/cyan]"):
        codes = svc.resolve_pool(pool_arg)

    if not codes:
        console.print(f"[yellow]股票池为空: {pool_arg}[/yellow]")
        return

    # 大池二次确认提示
    if len(codes) > 1000:
        max_workers = int(cfg.get("max_workers", 4))
        est_min = max(1, len(codes) // (max_workers * 30))
        console.print(
            f"[yellow]⚠️ 当前池规模 {len(codes)} 只，预计耗时 ~{est_min} 分钟 "
            f"(并发 {max_workers}). 按 Ctrl+C 可中断[/yellow]"
        )

    console.print(
        f"[cyan]🔍 选股扫描 — 股票池: {pool_arg} ({len(codes)} 只) | "
        f"模式: {side}[/cyan]\n"
    )

    side = side.lower()
    all_hits = []

    # ============ 买入信号 ============
    if side in ("buy", "both"):
        rules_block = cfg.get("buy", {}) or {}
        rules = rules_block.get("rules", [])
        if rules:
            console.print(
                f"[bold green]📈 买入扫描[/bold green] "
                f"[dim]规则数 {len(rules)} | 模式 {rules_block.get('mode', 'all')}[/dim]"
            )
            buy_hits = _scan_with_progress(svc, codes, side="buy")
            _print_hits(buy_hits, rules, side="buy")
            all_hits.extend(buy_hits)
        else:
            console.print("[dim]未配置买入规则，跳过买入扫描[/dim]")

    # ============ 卖出信号 ============
    if side in ("sell", "both"):
        rules_block = cfg.get("sell", {}) or {}
        rules = rules_block.get("rules", [])
        if rules:
            # 卖出走持仓（需要成本）
            from app.services.portfolio_service import PortfolioService

            holdings = PortfolioService().get_portfolio_with_market_data()
            positions = {h["stock_code"]: h for h in holdings}
            sell_codes = list(positions.keys()) if positions else codes
            if not sell_codes:
                console.print("[dim]当前无持仓，跳过卖出扫描[/dim]")
            else:
                console.print(
                    f"\n[bold red]📉 卖出扫描[/bold red] "
                    f"[dim]规则数 {len(rules)} | 模式 {rules_block.get('mode', 'any')} | "
                    f"持仓 {len(positions)} 只[/dim]"
                )
                sell_hits = _scan_with_progress(
                    svc, sell_codes, side="sell", positions=positions
                )
                _print_hits(sell_hits, rules, side="sell")
                all_hits.extend(sell_hits)
        else:
            console.print("\n[dim]未配置卖出规则，跳过卖出扫描[/dim]")

    # ============ 推送 ============
    if push and all_hits:
        try:
            from app.services.notification import NotificationManager, NotificationLevel

            mgr = NotificationManager()
            if mgr.is_enabled:
                lines = []
                for h in all_hits[:50]:  # 大池命中可能很多，截断防爆
                    icon = "📈" if h.side == "buy" else "📉"
                    lines.append(
                        f"{icon} {h.name}({h.code}) {h.price:.2f} "
                        f"满足{len(h.matched)}/{h.total_rules}条"
                    )
                if len(all_hits) > 50:
                    lines.append(f"... 共 {len(all_hits)} 条，已截断展示前 50 条")
                mgr.notify(
                    title=f"📋 选股扫描结果（{len(all_hits)}条命中）",
                    content="\n".join(lines),
                    level=NotificationLevel.INFO,
                )
                console.print(f"\n[green]✅ 已推送 {len(all_hits)} 条命中信号[/green]")
            else:
                console.print("[yellow]⚠️ 推送渠道未启用[/yellow]")
        except Exception as e:
            console.print(f"[red]推送失败: {e}[/red]")


# ============================================================================
# 池构建 (CLI: stock-ai sn-pool-build)
# ============================================================================


def do_pool_build(force: bool = False):
    """构建/刷新全A代码缓存"""
    from app.services.pool_loader import get_cache_info

    info = get_cache_info()
    if info and not force:
        console.print(
            Panel(
                f"已有缓存: {info['count']} 只 (更新于 {info['updated']})\n"
                f"路径: {info['path']}\n\n"
                f"[dim]如需强制刷新使用 --force[/dim]",
                title="📋 全A代码缓存",
                border_style="cyan",
            )
        )
        return

    _build_pool_cache()
    info = get_cache_info()
    if info:
        console.print(
            Panel(
                f"✅ 构建完成: {info['count']} 只\n路径: {info['path']}",
                title="📋 全A代码缓存",
                border_style="green",
            )
        )


def _build_pool_cache():
    """带进度条调用 pool_loader 构建"""
    from app.services.pool_loader import build_all_a_codes, save_cache
    from app.config import get_config

    cfg = get_config().get("screener", {}) or {}
    exclude_delisted = bool(cfg.get("exclude_delisted", True))
    exclude_st = bool(cfg.get("exclude_st", False))

    with Progress(
        SpinnerColumn(),
        TextColumn("[cyan]🔍 探活全A代码段[/cyan]"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("[green]发现 {task.fields[found]} 只[/green]"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("build", total=1, found=0)

        def _cb(processed: int, total: int, found: int):
            progress.update(task, total=total, completed=processed, found=found)

        codes = build_all_a_codes(
            progress_cb=_cb,
            exclude_delisted=exclude_delisted,
            exclude_st=exclude_st,
        )
        save_cache(codes)


# ============================================================================
# 工具函数
# ============================================================================


def _scan_with_progress(svc, codes, side: str, positions=None):
    """带进度条调用 svc.screen()"""
    with Progress(
        SpinnerColumn(),
        TextColumn(f"[cyan]扫描 {side}[/cyan]"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("[green]命中 {task.fields[hits]}[/green]"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("scan", total=len(codes), hits=0)

        def _cb(processed: int, total: int, found: int):
            progress.update(task, completed=processed, hits=found)

        return svc.screen(codes, side=side, positions=positions, progress_cb=_cb)


def _print_hits(hits: list, rules: list, side: str):
    """渲染命中表格"""
    if not hits:
        console.print(f"  [dim]无命中（{len(rules)}条规则均未达成聚合阈值）[/dim]")
        return

    color = get_up() if side == "buy" else get_down()
    table = Table(box=box.SIMPLE_HEAVY, show_lines=False)
    table.add_column("代码", style="cyan", width=10)
    table.add_column("名称", width=10)
    table.add_column("价格", justify="right", width=8)
    table.add_column("命中", justify="right", width=8)
    table.add_column("满足条件 / 详情", style=color)

    # 命中条件多的排前面
    hits_sorted = sorted(hits, key=lambda h: -len(h.matched))

    for h in hits_sorted:
        matched_str = " ｜ ".join(f"[{color}]{n}[/{color}]={d}" for n, d in h.matched)
        table.add_row(
            h.code,
            h.name or "-",
            f"{h.price:.2f}",
            f"{len(h.matched)}/{h.total_rules}",
            matched_str,
        )

    console.print(table)
    console.print(f"  [bold {color}]共 {len(hits)} 只命中[/bold {color}]")

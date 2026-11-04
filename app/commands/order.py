"""订单命令 — stock-ai order <子命令>

半自动执行层：默认只出草稿，绝不自动真实下单。

    stock-ai order plan --from-watchlist -s macd_cross   # 信号 → 订单草稿
    stock-ai order plan --signals-file signals.csv       # 离线纸面回放
    stock-ai order list
    stock-ai order risk <订单ID>
    stock-ai order submit <订单ID>                      # 默认 dry-run
    stock-ai order fill <订单ID> --price 16.50          # 人工回填成交
    stock-ai order reconcile
"""

import csv
from pathlib import Path

import typer
from app.commands import console, Table, Panel, box, as_bool, as_int


def register_order_commands(order_app: typer.Typer, cli_module=None):
    """注册订单命令"""

    def _service(broker_name: str = ""):
        from app.config import get_config
        from app.services.broker import get_broker
        from app.services.order_service import OrderService

        cfg = get_config()
        broker = get_broker(name=broker_name, cfg=cfg) if broker_name else None
        return OrderService(broker=broker, cfg=cfg)

    def _print_orders(orders):
        if not orders:
            console.print("[dim]暂无订单[/dim]")
            return
        table = Table(box=box.ROUNDED, header_style="bold cyan", show_lines=True)
        table.add_column("幂等键", no_wrap=True)
        table.add_column("代码")
        table.add_column("方向")
        table.add_column("价格", justify="right")
        table.add_column("数量", justify="right")
        table.add_column("金额", justify="right")
        table.add_column("状态")
        table.add_column("策略")
        table.add_column("模式")

        for o in orders:
            side_color = "green" if o.side.value == "buy" else "yellow"
            table.add_row(
                o.client_order_id[:12],
                o.code,
                f"[{side_color}]{'买入' if o.side.value == 'buy' else '卖出'}[/{side_color}]",
                f"{o.price:.2f}",
                str(o.quantity),
                f"{o.amount:,.0f}",
                o.status.value,
                o.strategy,
                "草稿" if o.dry_run else "真实",
            )
        console.print(table)

    # ==================== 编排 / 预览 ====================

    @order_app.command("plan")
    def order_plan(
        signals_file: str = typer.Option("", "--signals-file", "-f", help="离线信号 CSV"),
        from_watchlist: bool = typer.Option(False, "--from-watchlist", "-w", help="用自选股最新策略信号"),
        strategy: str = typer.Option("macd_cross", "--strategy", "-s", help="策略名"),
        quantity: int = typer.Option(100, "--qty", "-q", help="每笔股数（整手）"),
        broker: str = typer.Option("", "--broker", help="通道: manual / mock / paper"),
        no_save: bool = typer.Option(False, "--no-save", help="只预览不落库"),
    ):
        """把信号翻译成订单草稿（不产生任何真实委托）"""
        from app.services.order_planner import Signal, plan_orders

        signals = []
        if signals_file:
            path = Path(signals_file)
            if not path.exists():
                console.print(f"[red]❌ 信号文件不存在: {path}[/red]")
                return
            with open(path, "r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    signals.append(Signal(
                        code=row.get("code", ""),
                        side=row.get("side", "buy"),
                        price=float(row.get("price", 0)),
                        strategy=row.get("strategy", strategy),
                        bar_date=row.get("bar_date", ""),
                        name=row.get("name", ""),
                        quantity=int(row.get("quantity") or 0),
                    ))
        elif as_bool(from_watchlist):
            signals = _signals_from_watchlist(strategy)
        else:
            console.print("[yellow]请指定 --signals-file 或 --from-watchlist[/yellow]")
            return

        if not signals:
            console.print("[yellow]没有可用信号[/yellow]")
            return

        plan = plan_orders(signals, default_quantity=as_int(quantity, 100), broker=broker or "manual")
        console.print(
            f"[cyan]📋 编排结果: {len(plan.orders)} 笔 / 去重 {plan.duplicates} 笔 / "
            f"跳过 {len(plan.skipped)} 笔 / 合计 {plan.total_amount:,.0f} 元[/cyan]"
        )
        _print_orders(plan.orders)

        svc = _service(broker)
        if as_bool(no_save):
            console.print("[dim]--no-save：仅预览，未落库[/dim]")
        else:
            created, duplicated = svc.create_from_plan(plan.orders)
            console.print(f"[green]✅ 落库 {created} 笔，命中幂等跳过 {duplicated} 笔[/green]")

        # 编排阶段就给出风控提示（只读，不阻断草稿；离线回放跳过交易时段检查）
        warned = 0
        for o in plan.orders:
            try:
                violations = svc.risk_check(o, enforce_session=False)
            except Exception as e:
                console.print(f"[yellow]⚠️ 风控检查异常: {e}[/yellow]")
                break
            if violations:
                warned += 1
                console.print(
                    f"[yellow]⚠️ {o.code} 风控提示: {'; '.join(violations)}[/yellow]"
                )
        if warned:
            console.print(
                f"[yellow]共 {warned} 笔触发风控规则，草稿仅供人工核对，"
                "真实提交会被拒绝[/yellow]"
            )

        files = _render_draft(svc, plan.orders)
        if files:
            console.print(f"[dim]草稿: {files['markdown']}[/dim]")

    def _signals_from_watchlist(strategy: str):
        """用自选股最新一根 K 线的策略信号生成订单候选"""
        from app.domain.indicators import FeatureEngine
        from app.services.market_service import MarketService
        from app.services.strategy import get_strategy
        from app.services.watchlist_service import WatchlistService
        from app.services.order_planner import Signal

        market = MarketService()
        engine = FeatureEngine()
        strat = get_strategy(strategy)
        result = []

        for stock in WatchlistService().list_watched():
            try:
                df = market.get_kline_df(stock.code, period="day", count=260)
                if df.empty:
                    continue
                featured = engine.build_features(df, dropna=True)
                if featured.empty:
                    continue
                signaled = strat.generate_signals(featured)
                last = signaled.iloc[-1]
                sig = int(last.get("signal", 0))
                if sig == 0:
                    continue
                result.append(Signal(
                    code=stock.code,
                    side="buy" if sig > 0 else "sell",
                    price=float(last["close"]),
                    strategy=strategy,
                    bar_date=str(last["date"])[:10],
                    name=stock.name or "",
                ))
            except Exception as e:
                console.print(f"[yellow]⚠️ {stock.code} 信号计算失败: {e}[/yellow]")
        return result

    def _render_draft(svc, orders=None) -> dict:
        from app.services.broker.manual import ManualBroker
        from app.config import get_config

        if not isinstance(svc.broker, ManualBroker):
            return {}
        if orders is None:
            orders = svc.list_orders(status="pending_review", limit=200)
        if not orders:
            return {}
        draft_dir = get_config().get("broker", {}).get("draft_dir", "./data/orders")
        return ManualBroker(draft_dir=draft_dir).render_draft(orders)

    # ==================== 增删改查 ====================

    @order_app.command("create")
    def order_create(
        code: str = typer.Argument(..., help="股票代码"),
        side: str = typer.Argument(..., help="buy / sell"),
        price: float = typer.Argument(..., help="委托价"),
        qty: int = typer.Option(100, "--qty", "-q", help="股数（整手）"),
        strategy: str = typer.Option("manual", "--strategy", "-s", help="策略名"),
    ):
        """手工创建一笔订单（只落草稿）"""

        if side.lower() not in ("buy", "sell"):
            console.print("[red]❌ side 只能是 buy / sell[/red]")
            return
        try:
            order, created = _service().create_order(
                code=code, side=side.lower(), price=price,
                quantity=as_int(qty, 100), strategy=strategy,
            )
        except Exception as e:
            console.print(f"[red]❌ 创建失败: {e}[/red]")
            return

        console.print(
            f"[green]{'✅ 订单已创建' if created else '♻️ 命中幂等，复用已有订单'}: "
            f"{order.client_order_id}[/green]"
        )
        if created:
            _print_orders([order])

    @order_app.command("list")
    def order_list(
        status: str = typer.Option("", "--status", help="按状态过滤"),
        limit: int = typer.Option(30, "--limit", "-l", help="显示条数"),
    ):
        """查看订单"""
        _print_orders(_service().list_orders(status=status, limit=as_int(limit, 30)))

    @order_app.command("risk")
    def order_risk(
        oid: str = typer.Argument(..., help="幂等键"),
        offline: bool = typer.Option(False, "--offline", help="跳过交易时段检查"),
    ):
        """对一笔订单跑风控检查（只读）"""
        svc = _service()
        order = svc.get(oid)
        if not order:
            console.print(f"[red]❌ 订单不存在: {oid}[/red]")
            return
        violations = svc.risk_check(order, enforce_session=not as_bool(offline))
        if violations:
            for v in violations:
                console.print(f"[red]  ✗ {v}[/red]")
            console.print(f"[red]风控不通过（{len(violations)} 项）[/red]")
        else:
            console.print("[green]✅ 风控通过[/green]")

    @order_app.command("submit")
    def order_submit(
        oid: str = typer.Argument(..., help="幂等键"),
        dry_run: bool = typer.Option(True, "--dry-run/--live", help="默认仅草稿；--live 为真实提交"),
        yes: bool = typer.Option(False, "--yes", "-y", help="人工二次确认（--live 必填）"),
        broker: str = typer.Option("", "--broker", help="通道: manual / mock / paper"),
    ):
        """提交订单（默认 dry-run）"""
        from app.services.order_service import OrderNotFound, OrderRejected

        dry_run = as_bool(dry_run, default=True)
        svc = _service(broker)
        try:
            result = svc.submit(
                oid, confirmed=as_bool(yes), dry_run=dry_run,
                enforce_session=not dry_run,
            )
        except (OrderNotFound, OrderRejected) as e:
            console.print(f"[red]❌ {e}[/red]")
            return

        mode = "[green]草稿[/green]" if dry_run else "[yellow]真实提交[/yellow]"
        console.print(f"{mode} | 状态: {result['status']} | {result['message']}")
        if not dry_run:
            console.print("[red]⚠️ 已请求真实提交，请务必核对券商端委托回报[/red]")

    @order_app.command("fill")
    def order_fill(
        oid: str = typer.Argument(..., help="幂等键"),
        price: float = typer.Argument(..., help="实际成交价"),
        qty: int = typer.Option(0, "--qty", "-q", help="成交量（0=剩余全部）"),
        no_trade: bool = typer.Option(False, "--no-trade", help="只更新订单，不写 trades 表"),
    ):
        """人工回填成交 → 写交易记录 + 推送 + 重建持仓"""
        from app.services.order_service import OrderNotFound, OrderRejected

        try:
            result = _service().fill(
                oid, price=price, quantity=as_int(qty, 0),
                write_trade=not as_bool(no_trade),
            )
        except (OrderNotFound, OrderRejected) as e:
            console.print(f"[red]❌ {e}[/red]")
            return

        console.print(
            f"[green]✅ 成交回填 {result['filled_quantity']} 股 @ {result['filled_price']} "
            f"| 状态 {result['status']} | trade_id={result['trade_id']}[/green]"
        )

    @order_app.command("cancel")
    def order_cancel(oid: str = typer.Argument(..., help="幂等键")):
        """撤单"""
        from app.services.order_service import OrderRejected

        try:
            order = _service().cancel(oid)
        except OrderRejected as e:
            console.print(f"[red]❌ {e}[/red]")
            return
        console.print(f"[green]✅ 已撤单: {order.client_order_id}[/green]")

    @order_app.command("draft")
    def order_draft():
        """重新导出当日草稿"""
        files = _render_draft(_service())
        if not files:
            console.print("[yellow]当前通道不是 manual，或没有待执行订单[/yellow]")
            return
        console.print(f"[green]✅ 草稿已生成: {files['markdown']}[/green]")
        console.print(f"[dim]CSV: {files['csv']}[/dim]")

    # ==================== 运维 ====================

    @order_app.command("expire")
    def order_expire():
        """清理超时未成交订单"""
        ids = _service().expire_stale()
        console.print(f"[green]✅ 超时处理 {len(ids)} 笔[/green]")

    @order_app.command("recover")
    def order_recover():
        """重启恢复：把状态不明的真实委托标为 UNKNOWN（不会重下）"""
        ids = _service().recover_on_startup()
        console.print(f"[green]✅ 恢复标记 {len(ids)} 笔（等待对账）[/green]")

    @order_app.command("reconcile")
    def order_reconcile():
        """对账：已成交订单 vs trades 表"""
        r = _service().reconcile()
        color = "green" if r["ok"] else "red"
        console.print(
            Panel(
                f"已成交订单: {r['filled_orders']}\n"
                f"订单关联交易: {r['order_linked_trades']}\n"
                f"缺成交记录: {len(r['missing_trades'])}\n"
                f"状态不明订单: {r['unknown_orders']}",
                title="🔍 订单对账",
                border_style=color,
            )
        )
        for oid in r["missing_trades"]:
            console.print(f"[red]  ✗ {oid} 缺 trades 记录[/red]")
        if r["unknown_orders"]:
            console.print("[yellow]⚠️ 有状态不明订单，禁止重新提交，请人工核对券商回报[/yellow]")

    if cli_module is not None:
        cli_module.order_plan = order_plan
        cli_module.order_list = order_list
        cli_module.order_reconcile = order_reconcile

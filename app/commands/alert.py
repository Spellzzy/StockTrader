"""预警监控命令 — 从 cli.py 拆分

包含预警规则的添加、列表、删除、开关、重置、检测、历史和类型查询。
"""

import typer
from app.commands import console, Table, Panel, box


def register_alert_commands(alert_app: typer.Typer, cli_module=None):
    """将所有预警子命令注册到 alert_app 上

    Args:
        alert_app: typer.Typer 实例
        cli_module: cli 模块引用（用于将函数挂回 cli 模块，供 shortcuts.py 调用）
    """

    @alert_app.command("add")
    def alert_add_cmd(
        code: str = typer.Argument(..., help="股票代码 (如 600519, 支持自动识别sh/sz)"),
        condition: str = typer.Argument(..., help="条件类型 (price_above/rsi_below/macd_cross 等)"),
        threshold: float = typer.Option(None, "--threshold", "-t", help="阈值 (价格/百分比)"),
        repeat: bool = typer.Option(False, "--repeat", "-r", help="触发后继续监控(可重复触发)"),
        note: str = typer.Option("", "--note", "-n", help="备注"),
    ):
        """添加预警规则"""
        from app.services.alert_service import AlertService

        svc = AlertService()

        try:
            alert = svc.add_alert(
                stock_code=code,
                condition_type=condition,
                threshold=threshold,
                repeat=repeat,
                note=note,
            )
        except ValueError as e:
            console.print(f"[red]❌ {e}[/red]")
            raise typer.Exit(1)

        repeat_str = "🔁 重复触发" if repeat else "🔔 单次触发"
        console.print(Panel(
            f"[bold]{alert.stock_code}[/bold] {alert.stock_name or ''}\n"
            f"条件: {alert.condition_desc}\n"
            f"模式: {repeat_str}\n"
            f"备注: {alert.note or '无'}",
            title=f"✅ 预警已添加 (ID: {alert.id})",
            border_style="green",
        ))

    @alert_app.command("list")
    def alert_list_cmd(
        code: str = typer.Option("", "--code", "-c", help="按股票代码过滤"),
        active: bool = typer.Option(False, "--active", "-a", help="仅显示启用的"),
    ):
        """查看预警规则列表"""
        from app.services.alert_service import AlertService

        svc = AlertService()
        alerts = svc.list_alerts(stock_code=code, active_only=active)

        if not alerts:
            console.print("[yellow]📭 没有预警规则。使用 [bold]stock-ai alert-add <代码> <条件>[/bold] 添加[/yellow]")
            return

        table = Table(
            title="🔔 预警规则列表",
            box=box.ROUNDED,
            show_lines=True,
            header_style="bold cyan",
        )
        table.add_column("ID", style="dim", width=4)
        table.add_column("代码", width=10)
        table.add_column("名称", width=10)
        table.add_column("条件", width=22)
        table.add_column("状态", width=8, justify="center")
        table.add_column("触发", width=5, justify="center")
        table.add_column("模式", width=5, justify="center")
        table.add_column("最后触发", width=12)
        table.add_column("备注", width=12)

        for a in alerts:
            # 状态颜色
            if a.is_active:
                if a.is_triggered and not a.repeat:
                    status = "[yellow]已触发[/yellow]"
                else:
                    status = "[green]监控中[/green]"
            else:
                status = "[dim]已暂停[/dim]"

            last_trigger = a.last_triggered_at.strftime("%m-%d %H:%M") if a.last_triggered_at else "-"
            mode = "🔁" if a.repeat else "🔔"

            table.add_row(
                str(a.id),
                a.stock_code,
                a.stock_name or "",
                a.condition_desc or "",
                status,
                str(a.trigger_count),
                mode,
                last_trigger,
                (a.note or "")[:12],
            )

        console.print(table)
        console.print(f"[dim]共 {len(alerts)} 条预警规则[/dim]")

    @alert_app.command("delete")
    def alert_delete_cmd(
        alert_id: int = typer.Argument(..., help="预警规则 ID"),
        yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
    ):
        """删除预警规则"""
        from app.services.alert_service import AlertService

        svc = AlertService()
        alert = svc.get_alert(alert_id)
        if not alert:
            console.print(f"[red]❌ 找不到 ID={alert_id} 的预警规则[/red]")
            raise typer.Exit(1)

        if not yes:
            console.print(f"即将删除: {alert.stock_code} {alert.condition_desc}")
            confirm = typer.confirm("确定删除？")
            if not confirm:
                return

        svc.delete_alert(alert_id)
        console.print(f"[green]✅ 已删除预警规则 ID={alert_id}[/green]")

    @alert_app.command("toggle")
    def alert_toggle_cmd(
        alert_id: int = typer.Argument(..., help="预警规则 ID"),
    ):
        """启用/暂停预警规则"""
        from app.services.alert_service import AlertService

        svc = AlertService()
        alert = svc.toggle_alert(alert_id)
        if not alert:
            console.print(f"[red]❌ 找不到 ID={alert_id} 的预警规则[/red]")
            raise typer.Exit(1)

        status = "[green]已启用[/green]" if alert.is_active else "[yellow]已暂停[/yellow]"
        console.print(f"✅ 预警 ID={alert_id} ({alert.stock_code} {alert.condition_desc}) → {status}")

    @alert_app.command("reset")
    def alert_reset_cmd(
        alert_id: int = typer.Argument(..., help="预警规则 ID"),
    ):
        """重置预警（清除已触发状态，重新开始监控）"""
        from app.services.alert_service import AlertService

        svc = AlertService()
        alert = svc.reset_alert(alert_id)
        if not alert:
            console.print(f"[red]❌ 找不到 ID={alert_id} 的预警规则[/red]")
            raise typer.Exit(1)

        console.print(f"[green]✅ 已重置预警 ID={alert_id}，重新进入监控状态[/green]")

    @alert_app.command("check")
    def alert_check_cmd():
        """立即检测一次所有预警"""
        from app.services.alert_service import AlertService

        svc = AlertService()
        active_alerts = svc.list_alerts(active_only=True)

        if not active_alerts:
            console.print("[yellow]📭 没有活跃的预警规则[/yellow]")
            return

        console.print(f"[cyan]🔍 检测 {len(active_alerts)} 条活跃预警...[/cyan]")

        with console.status("[cyan]获取行情数据并检测中...[/cyan]"):
            triggered = svc.check_alerts(verbose=True)

        if triggered:
            console.print(f"\n[bold red]🚨 {len(triggered)} 条预警已触发！[/bold red]\n")
            for t in triggered:
                alert = t["alert"]
                msg = t["message"]
                console.print(Panel(
                    f"[bold]{alert.stock_code}[/bold] {alert.stock_name or ''}\n"
                    f"条件: {alert.condition_desc}\n"
                    f"[bold red]{msg}[/bold red]",
                    title=f"🚨 预警触发 (ID: {alert.id})",
                    border_style="red",
                ))
        else:
            console.print(f"[green]✅ 所有预警未触发，一切正常[/green]")

    @alert_app.command("history")
    def alert_history_cmd(
        code: str = typer.Option("", "--code", "-c", help="按股票代码过滤"),
        alert_id: int = typer.Option(0, "--id", help="按预警规则 ID 过滤"),
        limit: int = typer.Option(20, "--limit", "-l", help="显示条数"),
    ):
        """查看预警触发历史"""
        from app.services.alert_service import AlertService

        svc = AlertService()
        history = svc.list_history(
            stock_code=code,
            alert_id=alert_id if alert_id > 0 else None,
            limit=limit,
        )

        if not history:
            console.print("[yellow]📭 没有触发记录[/yellow]")
            return

        table = Table(
            title="📜 预警触发历史",
            box=box.ROUNDED,
            show_lines=True,
            header_style="bold cyan",
        )
        table.add_column("时间", width=16)
        table.add_column("代码", width=10)
        table.add_column("名称", width=10)
        table.add_column("条件", width=18)
        table.add_column("触发值", width=10, justify="right")
        table.add_column("阈值", width=10, justify="right")
        table.add_column("触发时价格", width=10, justify="right")
        table.add_column("涨跌幅", width=8, justify="right")
        table.add_column("消息", width=25)

        for h in history:
            chg = h.change_percent or 0
            chg_color = "green" if chg >= 0 else "red"

            table.add_row(
                h.triggered_at.strftime("%m-%d %H:%M:%S") if h.triggered_at else "-",
                h.stock_code,
                h.stock_name or "",
                h.condition_desc or "",
                f"{h.trigger_value:.2f}" if h.trigger_value is not None else "-",
                f"{h.threshold:.2f}" if h.threshold is not None else "-",
                f"{h.price:.2f}" if h.price else "-",
                f"[{chg_color}]{chg:+.2f}%[/{chg_color}]",
                (h.message or "")[:25],
            )

        console.print(table)
        console.print(f"[dim]共 {len(history)} 条触发记录[/dim]")

    @alert_app.command("types")
    def alert_types_cmd():
        """查看支持的预警条件类型"""
        from app.services.alert_service import AlertService

        types = AlertService.get_condition_types()

        table = Table(
            title="📋 支持的预警条件类型",
            box=box.ROUNDED,
            header_style="bold cyan",
        )
        table.add_column("类型代码", width=18, style="bold")
        table.add_column("名称", width=16)
        table.add_column("需要阈值", width=8, justify="center")
        table.add_column("单位", width=6)

        for t in types:
            need = "[green]✓[/green]" if t["need_threshold"] else "[dim]✗[/dim]"
            table.add_row(t["type"], t["name"], need, t["unit"])

        console.print(table)
        console.print(
            "\n[dim]用法示例:\n"
            "  stock-ai alert-add sh600519 price_above -t 1900      # 价格突破1900元提醒\n"
            "  stock-ai alert-add sz000985 rsi_below -t 30           # RSI跌破30超卖提醒\n"
            "  stock-ai alert-add sh600519 macd_cross                # MACD金叉提醒\n"
            "  stock-ai alert-add sh600519 change_below -t 5 -r      # 跌超5%提醒(可重复)\n"
            "[/dim]"
        )

    # 将函数挂回 cli_module，供 shortcuts.py 通过 cli_module.xxx 调用
    if cli_module is not None:
        cli_module.alert_add_cmd = alert_add_cmd
        cli_module.alert_list_cmd = alert_list_cmd
        cli_module.alert_delete_cmd = alert_delete_cmd
        cli_module.alert_toggle_cmd = alert_toggle_cmd
        cli_module.alert_reset_cmd = alert_reset_cmd
        cli_module.alert_check_cmd = alert_check_cmd
        cli_module.alert_history_cmd = alert_history_cmd
        cli_module.alert_types_cmd = alert_types_cmd

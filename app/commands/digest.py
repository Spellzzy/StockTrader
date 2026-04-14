"""智能日报命令 — 从 cli.py 拆分

包含 digest 生成、推送、自动预警等命令。
"""

import typer
from app.commands import console, Table, Panel, box


def register_digest_commands(digest_app: typer.Typer, cli_module=None):
    """将所有 digest 子命令注册到 digest_app 上

    Args:
        digest_app: typer.Typer 实例
        cli_module: cli 模块引用（用于将函数挂回 cli 模块，供 shortcuts.py 调用）
    """

    @digest_app.command("run")
    def digest_run(
        dl: bool = typer.Option(False, "--dl", help="使用深度学习模型"),
        llm: bool = typer.Option(False, "--llm", help="对重点股票追加 LLM 深度分析"),
        top: int = typer.Option(3, "--top", "-t", help="追加分析看涨 Top N"),
        bottom: int = typer.Option(2, "--bottom", "-b", help="追加分析看跌 Top N"),
        push: bool = typer.Option(False, "--push", "-p", help="生成后推送到已配置的通知渠道"),
        auto_alert: bool = typer.Option(False, "--auto-alert", help="自动为高风险股票配置预警"),
    ):
        """生成自选股智能日报

        扫描所有自选股，AI 分析信号强弱，输出人话结论。
        加 --push 自动推送到微信/钉钉等渠道。
        加 --llm 对重点股票追加 LLM 深度分析（需配置 LLM）。
        """
        from app.services.smart_digest import SmartDigestService

        svc = SmartDigestService()

        # 检查自选股
        watched = svc.watchlist.list_watched()
        if not watched:
            console.print(
                "[yellow]⭐ 收藏列表为空，先用 [bold]stock-ai star <代码>[/bold] 添加自选股[/yellow]"
            )
            return

        console.print(
            f"[cyan]📊 正在生成智能日报 ({len(watched)} 只自选股)...[/cyan]"
        )

        # 生成日报
        if push:
            with console.status("[cyan]🔍 AI 扫描 + 生成摘要 + 推送中...[/cyan]"):
                result = svc.generate_and_push(
                    use_dl=dl, use_llm=llm, top_n=top, bottom_n=bottom,
                )
            digest = result["digest"]
            push_results = result["push_results"]
        else:
            with console.status("[cyan]🔍 AI 扫描 + 生成摘要中...[/cyan]"):
                digest = svc.generate(
                    use_dl=dl, use_llm=llm, top_n=top, bottom_n=bottom,
                )
            push_results = []

        if not digest:
            console.print("[red]❌ 生成智能日报失败[/red]")
            return

        # 显示 Rich 格式的日报
        console.print()
        console.print(Panel(
            digest["plain_text"],
            title=f"[bold]📊 自选股智能日报 ({digest['date']})[/bold]",
            border_style="blue",
            padding=(1, 2),
        ))

        # 显示推送结果
        if push_results:
            console.print()
            for ch_name, success, err in push_results:
                if success:
                    console.print(f"  [green]✅ {ch_name} — 推送成功[/green]")
                else:
                    console.print(f"  [red]❌ {ch_name} — 推送失败: {err}[/red]")
        elif push:
            console.print(
                "[yellow]⚠️ 消息推送未启用或无已配置的渠道。"
                "使用 [bold]stock-ai notify-list[/bold] 查看配置[/yellow]"
            )

        # 自动预警
        if auto_alert:
            new_alerts = svc.auto_configure_alerts(digest)
            if new_alerts:
                console.print(f"\n[cyan]🔔 已为 {len(new_alerts)} 只高风险股票自动配置预警:[/cyan]")
                for a in new_alerts:
                    console.print(
                        f"  ⚠️ {a['name']} ({a['code']}) — "
                        f"跌幅超 {abs(a['threshold'])}% 时预警"
                    )
            else:
                console.print("[dim]无需新增自动预警[/dim]")

        # 底部提示
        console.print()
        console.print("[dim]⚠️ 以上分析仅供参考，不构成投资建议[/dim]")

    @digest_app.command("push")
    def digest_push(
        dl: bool = typer.Option(False, "--dl", help="使用深度学习模型"),
        llm: bool = typer.Option(False, "--llm", help="追加 LLM 分析"),
    ):
        """生成并推送智能日报（等同于 digest run --push）"""
        from app.services.smart_digest import SmartDigestService
        from app.services.notification import NotificationLevel

        svc = SmartDigestService()

        if not svc.notifier.is_enabled:
            console.print(
                "[yellow]⚠️ 消息推送未启用或无已配置的渠道[/yellow]\n"
                "[dim]请在 config.yaml 的 notification.channels 中启用至少一个渠道[/dim]\n"
                "[dim]使用 [bold]stock-ai notify-list[/bold] 查看当前配置[/dim]"
            )
            return

        watched = svc.watchlist.list_watched()
        if not watched:
            console.print(
                "[yellow]⭐ 收藏列表为空[/yellow]"
            )
            return

        with console.status(
            f"[cyan]📊 生成 + 推送智能日报 ({len(watched)} 只自选股)...[/cyan]"
        ):
            result = svc.generate_and_push(use_dl=dl, use_llm=llm)

        digest = result["digest"]
        push_results = result["push_results"]

        if not digest:
            console.print("[red]❌ 生成失败[/red]")
            return

        # 简要显示
        bullish_count = len(digest["bullish"])
        bearish_count = len(digest["bearish"])
        neutral_count = len(digest["neutral"])
        console.print(
            f"[green]✅ 日报已生成[/green] — "
            f"{digest['total']}只: "
            f"[green]{bullish_count}涨[/green] "
            f"[yellow]{neutral_count}平[/yellow] "
            f"[red]{bearish_count}跌[/red]"
        )

        for ch_name, success, err in push_results:
            if success:
                console.print(f"  [green]✅ {ch_name} — 推送成功[/green]")
            else:
                console.print(f"  [red]❌ {ch_name} — 推送失败: {err}[/red]")

    @digest_app.command("preview")
    def digest_preview(
        dl: bool = typer.Option(False, "--dl", help="使用深度学习模型"),
    ):
        """预览智能日报（仅扫描，不推送不 LLM，快速查看）"""
        from app.services.smart_digest import SmartDigestService

        svc = SmartDigestService()

        watched = svc.watchlist.list_watched()
        if not watched:
            console.print(
                "[yellow]⭐ 收藏列表为空[/yellow]"
            )
            return

        with console.status(
            f"[cyan]🔍 快速扫描 {len(watched)} 只自选股...[/cyan]"
        ):
            digest = svc.generate(use_dl=dl, use_llm=False)

        if not digest:
            console.print("[red]❌ 扫描失败[/red]")
            return

        # 表格形式展示
        table = Table(
            title=f"📊 自选股快报 ({digest['date']})",
            box=box.ROUNDED,
            show_lines=True,
            header_style="bold cyan",
        )
        table.add_column("排名", width=4, justify="center")
        table.add_column("代码", width=10)
        table.add_column("名称", width=10)
        table.add_column("信号", width=6, justify="center")
        table.add_column("评分", width=8, justify="right")
        table.add_column("置信度", width=8, justify="right")
        table.add_column("评级", width=8, justify="center")
        table.add_column("关键因子", width=30)

        # 合并所有结果并按评分排序
        all_items = (
            digest["bullish"] + digest["neutral"] + digest["bearish"]
        )
        all_items.sort(key=lambda x: x["score"], reverse=True)

        for i, item in enumerate(all_items, 1):
            sig = item["signal"]
            if sig == "看涨":
                sig_color = "green"
            elif sig == "看跌":
                sig_color = "red"
            else:
                sig_color = "yellow"

            stars = "⭐" * item["stars"]
            factors = " | ".join(item["key_factors"][:2]) if item["key_factors"] else "-"

            table.add_row(
                str(i),
                item["code"],
                item["name"],
                f"[{sig_color}]{sig}[/{sig_color}]",
                f"[{sig_color}]{item['score']:+.1f}[/{sig_color}]",
                f"{item['confidence']:.1f}%",
                stars,
                factors,
            )

        console.print(table)

        # 汇总
        console.print(
            f"\n[dim]📈 {digest['total']}只自选股: "
            f"[green]{len(digest['bullish'])}涨[/green] "
            f"[yellow]{len(digest['neutral'])}平[/yellow] "
            f"[red]{len(digest['bearish'])}跌[/red] | "
            f"使用 [bold]stock-ai digest run --llm[/bold] 获取 LLM 深度分析[/dim]"
        )

    # 将函数挂回 cli_module，供 shortcuts.py 调用
    if cli_module is not None:
        cli_module.digest_run = digest_run
        cli_module.digest_push = digest_push
        cli_module.digest_preview = digest_preview

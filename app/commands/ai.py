"""AI 预测分析命令 — 从 cli.py 拆分

包含 ML/DL 预测、LLM 深度分析、自选股扫描、模型管理等命令。
"""

import typer
from app.commands import console, Table, Panel, box


def register_ai_commands(ai_app: typer.Typer, cli_module=None):
    """将所有 AI 子命令注册到 ai_app 上

    Args:
        ai_app: typer.Typer 实例
        cli_module: cli 模块引用（用于将函数挂回 cli 模块，供 shortcuts.py 调用）
    """

    @ai_app.command("predict")
    def ai_predict(
        code: str = typer.Argument(..., help="股票代码 (如 600519, 支持自动识别sh/sz)"),
        dl: bool = typer.Option(False, "--dl", help="同时使用深度学习模型"),
        llm: bool = typer.Option(False, "--llm", help="追加 LLM 分析点评"),
    ):
        """AI 预测股票走势"""
        from app.ai.predictor_service import PredictorService

        with console.status(f"[cyan]🔮 正在分析 {code} ...[/cyan]"):
            svc = PredictorService()
            result = svc.predict(code, use_dl=dl)

        if not result or not result.get("combined"):
            console.print(f"[red]❌ 预测失败，数据不足或模型异常[/red]")
            return

        combined = result["combined"]

        # 信号颜色
        sig = combined["signal"]
        if sig == "看涨":
            sig_color = "green"
        elif sig == "看跌":
            sig_color = "red"
        else:
            sig_color = "yellow"

        stars_str = "⭐" * combined.get("stars", 0) + "☆" * (5 - combined.get("stars", 0))

        # 主面板
        lines = [
            f"[bold {sig_color}]📊 综合信号: {sig}[/bold {sig_color}]  {stars_str}",
            f"综合评分: [bold]{combined.get('score', 0):+.1f}[/bold]  "
            f"置信度: [bold]{combined.get('confidence', 0):.1f}%[/bold]",
            "",
        ]

        # ML 结果
        for key, label in [("ml_xgb", "XGBoost"), ("ml_rf", "RandomForest")]:
            ml = result.get(key)
            if ml:
                c = "green" if ml["signal"] == "看涨" else "red" if ml["signal"] == "看跌" else "yellow"
                lines.append(
                    f"  {label}: [{c}]{ml['signal']}[/{c}] "
                    f"({ml['confidence']:.1f}%) "
                    f"[dim]模型准确率 {ml.get('model_accuracy', 0):.1%}[/dim]"
                )

        # DL 结果
        dl_res = result.get("dl")
        if dl_res:
            c = "green" if dl_res["signal"] == "看涨" else "red" if dl_res["signal"] == "看跌" else "yellow"
            lines.append(
                f"  LSTM: [{c}]{dl_res['signal']}[/{c}] "
                f"({dl_res['confidence']:.1f}%) "
                f"[dim]模型准确率 {dl_res.get('model_accuracy', 0):.1%}[/dim]"
            )

        # 关键因子
        factors = combined.get("key_factors", [])
        if factors:
            lines.append("")
            lines.append("[bold]关键因子:[/bold]")
            for f in factors[:6]:
                lines.append(f"  {f}")

        # Top 特征
        ml_xgb_res = result.get("ml_xgb")
        if ml_xgb_res and "top_features" in ml_xgb_res:
            lines.append("")
            lines.append("[bold]Top 特征重要性:[/bold]")
            for feat in ml_xgb_res["top_features"][:5]:
                bar_len = int(feat["importance"] * 100)
                bar = "█" * min(bar_len, 20)
                lines.append(f"  {feat['name']:<16} {bar} {feat['importance']:.3f}")

        # 指标快照
        if ml_xgb_res and "indicators" in ml_xgb_res:
            ind = ml_xgb_res["indicators"]
            lines.append("")
            lines.append("[bold]技术指标快照:[/bold]")
            indicators_display = []
            for k, v in list(ind.items())[:12]:
                indicators_display.append(f"{k}={v}")
            # 每行 4 个
            for i in range(0, len(indicators_display), 4):
                chunk = indicators_display[i:i+4]
                lines.append("  " + "  ".join(f"[dim]{x}[/dim]" for x in chunk))

        horizon = 5
        if ml_xgb_res:
            horizon = ml_xgb_res.get("horizon", 5)

        console.print(Panel(
            "\n".join(lines),
            title=f"[bold]🔮 {code} AI 预测报告 (未来{horizon}日)[/bold]",
            border_style=sig_color,
            padding=(1, 2),
        ))

        # 追加 LLM 点评
        if llm:
            if not svc.has_llm:
                console.print("[yellow]⚠️ LLM 未配置，跳过 LLM 点评。使用 stock-ai analyze 查看配置方法[/yellow]")
                return

            with console.status("[cyan]🧠 LLM 正在分析...[/cyan]"):
                analysis = svc.analyze(code, use_dl=dl)

            report = analysis.get("report")
            if report:
                _render_analysis_report(code, report, result)
            elif analysis.get("error"):
                console.print(f"[yellow]⚠️ LLM 分析失败: {analysis['error']}[/yellow]")

    @ai_app.command("train")
    def ai_train(
        code: str = typer.Argument(..., help="股票代码"),
        dl: bool = typer.Option(False, "--dl", help="同时训练深度学习模型"),
    ):
        """训练 AI 预测模型"""
        from app.ai.predictor_service import PredictorService

        console.print(f"[cyan]🏋️ 开始训练 {code} 的预测模型...[/cyan]")
        svc = PredictorService()
        results = svc.train(code, use_dl=dl)

        if not results:
            console.print("[red]❌ 训练失败[/red]")
            return

        ml = results.get("ml")
        if ml:
            meta = ml.get("meta", {})
            console.print(f"\n[bold]📊 ML 训练完成[/bold]")
            console.print(f"  样本: {meta.get('total_samples', 0)} (训练 {meta.get('train_size', 0)} / 测试 {meta.get('test_size', 0)})")
            console.print(f"  特征数: {meta.get('n_features', 0)}")

            dist = meta.get("label_distribution", {})
            console.print(f"  标签分布: 涨 {dist.get('涨', 0)} | 震荡 {dist.get('震荡', 0)} | 跌 {dist.get('跌', 0)}")

            for model_key, model_name in [("rf", "RandomForest"), ("xgb", "XGBoost")]:
                m = ml.get(model_key)
                if m:
                    acc = m["accuracy"]
                    c = "green" if acc > 0.5 else "yellow" if acc > 0.4 else "red"
                    console.print(f"  {model_name}: [{c}]准确率 {acc:.2%}[/{c}]")

        dl_result = results.get("dl_lstm")
        if dl_result:
            console.print(f"\n[bold]🧠 DL-LSTM 训练完成[/bold]")
            console.print(f"  准确率: {dl_result['accuracy']:.2%}")
            dl_meta = dl_result.get("meta", {})
            console.print(f"  设备: {dl_meta.get('device', 'cpu')}")
            console.print(f"  轮数: {dl_meta.get('epochs', 0)}")

        dl_err = results.get("dl")
        if isinstance(dl_err, dict) and "error" in dl_err:
            console.print(f"\n[yellow]⚠️ {dl_err['error']}[/yellow]")

        console.print(f"\n[green]✅ 训练完成！使用 [bold]stock-ai predict {code}[/bold] 查看预测[/green]")

    @ai_app.command("analyze")
    def ai_analyze(
        code: str = typer.Argument(..., help="股票代码 (如 600519, 支持自动识别sh/sz)"),
        dl: bool = typer.Option(False, "--dl", help="同时使用深度学习模型"),
    ):
        """LLM 深度分析报告（技术+基本+资金+消息面）"""
        from app.ai.predictor_service import PredictorService

        svc = PredictorService()

        # 先检查 LLM 是否可用
        if not svc.has_llm:
            console.print(Panel(
                "[yellow]LLM 未配置[/yellow]\n\n"
                "请在 [bold]config.yaml[/bold] 中配置 LLM:\n"
                "  ai:\n"
                "    llm:\n"
                "      provider: openai       [dim]# openai/deepseek/moonshot/ollama[/dim]\n"
                "      api_key: sk-xxx        [dim]# API Key (ollama 不需要)[/dim]\n"
                "      model: gpt-4o          [dim]# 模型名称[/dim]\n"
                "\n"
                "[green]💡 免费方案: 安装 Ollama 后设置 provider: ollama, model: qwen2.5:7b[/green]",
                title="⚠️ LLM 配置缺失",
                border_style="yellow",
            ))
            return

        with console.status(f"[cyan]🧠 正在分析 {code}（收集多维数据 + LLM 推理中）...[/cyan]"):
            result = svc.analyze(code, use_dl=dl)

        if result.get("error"):
            console.print(f"[red]❌ 分析失败: {result['error']}[/red]")
            return

        report = result.get("report")
        if not report:
            console.print("[red]❌ 未获取到分析报告[/red]")
            return

        # 渲染分析报告
        _render_analysis_report(code, report, result.get("prediction"))

    @ai_app.command("scan")
    def ai_scan(
        dl: bool = typer.Option(False, "--dl", help="同时使用深度学习模型"),
        llm: bool = typer.Option(False, "--llm", help="对前5名追加 LLM 分析"),
    ):
        """扫描所有自选股，输出信号排名"""
        from app.ai.predictor_service import PredictorService
        from app.services.watchlist_service import WatchlistService

        watched = WatchlistService().list_watched()
        if not watched:
            console.print("[yellow]⭐ 收藏列表为空，先用 [bold]stock-ai star <代码>[/bold] 添加自选股[/yellow]")
            return

        codes = [s.code for s in watched]
        console.print(f"[cyan]🔍 扫描 {len(codes)} 只自选股...[/cyan]")

        with console.status("[cyan]分析中...[/cyan]"):
            svc = PredictorService()
            results = svc.scan(codes, use_dl=dl)

        if not results:
            console.print("[red]❌ 扫描失败[/red]")
            return

        table = Table(
            title="🔮 自选股 AI 信号排名",
            box=box.ROUNDED,
            show_lines=True,
            header_style="bold cyan",
        )
        table.add_column("排名", width=4, justify="center")
        table.add_column("代码", width=10)
        table.add_column("信号", width=6, justify="center")
        table.add_column("评分", width=8, justify="right")
        table.add_column("置信度", width=8, justify="right")
        table.add_column("评级", width=8, justify="center")
        table.add_column("关键因子", width=30)

        for i, r in enumerate(results, 1):
            combined = r.get("combined", {})
            sig = combined.get("signal", "?")
            if sig == "看涨":
                sig_color = "green"
            elif sig == "看跌":
                sig_color = "red"
            else:
                sig_color = "yellow"

            score = combined.get("score", 0)
            stars_str = "⭐" * combined.get("stars", 0)
            factors = combined.get("key_factors", [])
            factor_str = " | ".join(factors[:2]) if factors else "-"

            table.add_row(
                str(i),
                r["code"],
                f"[{sig_color}]{sig}[/{sig_color}]",
                f"[{sig_color}]{score:+.1f}[/{sig_color}]",
                f"{combined.get('confidence', 0):.1f}%",
                stars_str,
                factor_str,
            )

        console.print(table)
        console.print(f"[dim]共扫描 {len(results)} 只股票，使用 stock-ai predict <代码> 查看详细报告[/dim]")

        # LLM 追加分析前5名
        if llm:
            if not svc.has_llm:
                console.print("\n[yellow]⚠️ LLM 未配置，跳过 LLM 点评[/yellow]")
                return

            top_n = min(5, len(results))
            console.print(f"\n[cyan]🧠 正在对前 {top_n} 名进行 LLM 深度分析...[/cyan]")
            for i, r in enumerate(results[:top_n], 1):
                code = r["code"]
                with console.status(f"[cyan]({i}/{top_n}) 分析 {code}...[/cyan]"):
                    analysis = svc.analyze(code, use_dl=dl)
                report = analysis.get("report")
                if report:
                    rating = report.get("overall_rating", "?")
                    short_view = report.get("short_term_view", "")
                    console.print(f"  {i}. [bold]{code}[/bold] → {rating} | {short_view}")
                elif analysis.get("error"):
                    console.print(f"  {i}. [bold]{code}[/bold] → [red]失败[/red]")

    @ai_app.command("models")
    def ai_models(
        code: str = typer.Option("", "--code", "-c", help="筛选指定股票的模型"),
    ):
        """查看已训练的模型"""
        from app.ai.model_manager import ModelManager

        mgr = ModelManager()
        models = mgr.list_models(code or None)

        if not models:
            console.print("[yellow]📭 暂无已训练的模型[/yellow]")
            return

        table = Table(title="🤖 已训练模型列表", box=box.ROUNDED, header_style="bold cyan")
        table.add_column("类型", width=4)
        table.add_column("文件名", width=40)
        table.add_column("大小", width=10, justify="right")

        for m in models:
            table.add_row(m["kind"], m["file"], f"{m['size_kb']:.1f} KB")

        console.print(table)

    # 将函数挂回 cli_module，供 shortcuts.py 通过 cli_module.xxx 调用
    if cli_module is not None:
        cli_module.ai_predict = ai_predict
        cli_module.ai_train = ai_train
        cli_module.ai_analyze = ai_analyze
        cli_module.ai_scan = ai_scan
        cli_module.ai_models = ai_models
        cli_module._render_analysis_report = _render_analysis_report


def _render_analysis_report(code: str, report: dict, prediction: dict = None):
    """渲染 LLM 分析报告"""
    rating = report.get("overall_rating", "中性")
    confidence = report.get("confidence", 0)

    # 评级颜色
    if any(kw in rating for kw in ["看多", "看涨", "强烈看多"]):
        rating_color = "green"
    elif any(kw in rating for kw in ["看空", "看跌", "强烈看空"]):
        rating_color = "red"
    else:
        rating_color = "yellow"

    # 信心条
    conf_bar = "█" * (confidence // 5) + "░" * (20 - confidence // 5)
    conf_color = "green" if confidence >= 70 else "yellow" if confidence >= 40 else "red"

    lines = []
    lines.append(f"[bold {rating_color}]🎯 综合评级: {rating}[/bold {rating_color}]")
    lines.append(f"信心度: [{conf_color}]{conf_bar}[/{conf_color}] {confidence}%")
    lines.append("")

    # 技术面
    tech = report.get("technical_analysis", "")
    if tech:
        lines.append("[bold cyan]📊 技术面分析[/bold cyan]")
        lines.append(f"  {tech}")
        lines.append("")

    # 基本面
    fund = report.get("fundamental_analysis", "")
    if fund:
        lines.append("[bold cyan]📈 基本面分析[/bold cyan]")
        lines.append(f"  {fund}")
        lines.append("")

    # 资金面
    money = report.get("money_flow_analysis", "")
    if money:
        lines.append("[bold cyan]💰 资金面分析[/bold cyan]")
        lines.append(f"  {money}")
        lines.append("")

    # 消息面
    news = report.get("news_summary", "")
    sentiment = report.get("news_sentiment", "neutral")
    if news:
        sentiment_map = {"positive": "🟢 正面", "negative": "🔴 负面", "neutral": "🟡 中性"}
        lines.append(f"[bold cyan]📰 消息面[/bold cyan] ({sentiment_map.get(sentiment, sentiment)})")
        lines.append(f"  {news}")
        lines.append("")

    # 操作建议
    short = report.get("short_term_view", "")
    mid = report.get("mid_term_view", "")
    if short or mid:
        lines.append("[bold cyan]🎯 操作建议[/bold cyan]")
        if short:
            lines.append(f"  [bold]短期[/bold]: {short}")
        if mid:
            lines.append(f"  [bold]中期[/bold]: {mid}")
        lines.append("")

    # 风险提示
    risks = report.get("risk_warnings", [])
    if risks:
        lines.append("[bold red]⚠️ 风险提示[/bold red]")
        for r in risks:
            lines.append(f"  • {r}")
        lines.append("")

    # ML/DL 预测摘要（如果有）
    if prediction and prediction.get("combined"):
        combined = prediction["combined"]
        sig = combined.get("signal", "?")
        score = combined.get("score", 0)
        sig_color = "green" if sig == "看涨" else "red" if sig == "看跌" else "yellow"
        lines.append(f"[dim]📐 ML/DL 预测: [{sig_color}]{sig}[/{sig_color}] "
                      f"(评分{score:+.1f}, {combined.get('models_used', 0)}个模型)[/dim]")

    lines.append("")
    lines.append("[dim]⚠️ 以上分析仅供参考，不构成投资建议[/dim]")

    console.print(Panel(
        "\n".join(lines),
        title=f"[bold]🧠 {code} AI 深度分析报告[/bold]",
        border_style=rating_color,
        padding=(1, 2),
    ))

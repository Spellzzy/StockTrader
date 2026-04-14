"""顶级快捷命令 + 缩写别名 — 从 cli.py 拆分

本模块包含所有 @app.command 注册的扁平化快捷命令及其 hidden 缩写别名。
调用 register_shortcuts(app) 即可将所有命令注册到 typer app 上。

注意：
- Typer 的命令参数依赖函数签名，无法用纯数据表驱动注册
- 因此保留显式定义，但集中到此模块中，保持 cli.py 精简
"""

import typer


def register_shortcuts(app: typer.Typer, cli_module):
    """将所有快捷命令注册到 app 上

    Args:
        app: typer.Typer 实例
        cli_module: cli 模块引用（用于调用 cli 中定义的子命令组函数）
    """

    # ===================== 引用 cli 中的子命令组函数 =====================
    # 这些函数定义在 cli.py 的子命令组中（如 trade_app, portfolio_app 等）
    # 通过 cli_module 引用获取

    # --- 辅助内部函数 ---
    def _parse_time(time_str):
        return cli_module._parse_time(time_str)

    # ==================== 交易管理 ====================

    def _do_buy(code, price, quantity, name, reason, strategy, time):
        from app.services.trade_service import TradeService
        from app.services.portfolio_service import PortfolioService
        from app.commands import console, Panel

        trade_time = _parse_time(time)
        svc = TradeService()
        trade = svc.add_trade(
            stock_code=code, action="buy", price=price, quantity=quantity,
            stock_name=name, reason=reason, strategy=strategy, trade_time=trade_time,
        )
        display_name = trade.stock_name or name
        console.print(Panel(
            f"[red]买入[/red] {code} {display_name}\n"
            f"价格: {price}  数量: {quantity}  金额: {trade.amount:,.2f}\n"
            f"手续费: {trade.commission:.2f}  印花税: {trade.tax:.2f}",
            title=f"[OK] 买入成功 (ID: {trade.id})", border_style="green",
        ))
        PortfolioService().rebuild_portfolio()

    def _do_sell(code, price, quantity, name, reason, strategy, time):
        from app.services.trade_service import TradeService
        from app.services.portfolio_service import PortfolioService
        from app.commands import console, Panel

        trade_time = _parse_time(time)
        svc = TradeService()
        trade = svc.add_trade(
            stock_code=code, action="sell", price=price, quantity=quantity,
            stock_name=name, reason=reason, strategy=strategy, trade_time=trade_time,
        )
        display_name = trade.stock_name or name
        console.print(Panel(
            f"[green]卖出[/green] {code} {display_name}\n"
            f"价格: {price}  数量: {quantity}  金额: {trade.amount:,.2f}\n"
            f"手续费: {trade.commission:.2f}  印花税: {trade.tax:.2f}",
            title=f"[OK] 卖出成功 (ID: {trade.id})", border_style="green",
        ))
        PortfolioService().rebuild_portfolio()

    # --- buy / b ---
    @app.command("buy", help="快速买入 (缩写: b)")
    def quick_buy(
        code: str = typer.Argument(..., help="股票代码 (如 600519, 支持自动识别sh/sz)"),
        price: float = typer.Argument(..., help="成交价格"),
        quantity: int = typer.Argument(..., help="成交数量(股)"),
        name: str = typer.Option("", "--name", "-n", help="股票名称"),
        reason: str = typer.Option("", "--reason", "-r", help="交易理由"),
        strategy: str = typer.Option("", "--strategy", "-s", help="所用策略"),
        time: str = typer.Option("", "--time", help="交易时间 (YYYY-MM-DD HH:MM:SS)"),
    ):
        """快速买入"""
        _do_buy(code, price, quantity, name, reason, strategy, time)

    @app.command("b", hidden=True)
    def alias_b(
        code: str = typer.Argument(..., help="股票代码"),
        price: float = typer.Argument(..., help="成交价格"),
        quantity: int = typer.Argument(..., help="成交数量(股)"),
        name: str = typer.Option("", "--name", "-n", help="股票名称"),
        reason: str = typer.Option("", "--reason", "-r", help="交易理由"),
        strategy: str = typer.Option("", "--strategy", "-s", help="所用策略"),
        time: str = typer.Option("", "--time", help="交易时间"),
    ):
        """buy 的缩写"""
        _do_buy(code, price, quantity, name, reason, strategy, time)

    # --- sell / s ---
    @app.command("sell", help="快速卖出 (缩写: s)")
    def quick_sell(
        code: str = typer.Argument(..., help="股票代码 (如 600519, 支持自动识别sh/sz)"),
        price: float = typer.Argument(..., help="成交价格"),
        quantity: int = typer.Argument(..., help="成交数量(股)"),
        name: str = typer.Option("", "--name", "-n", help="股票名称"),
        reason: str = typer.Option("", "--reason", "-r", help="交易理由"),
        strategy: str = typer.Option("", "--strategy", "-s", help="所用策略"),
        time: str = typer.Option("", "--time", help="交易时间 (YYYY-MM-DD HH:MM:SS)"),
    ):
        """快速卖出"""
        _do_sell(code, price, quantity, name, reason, strategy, time)

    @app.command("s", hidden=True)
    def alias_s(
        code: str = typer.Argument(..., help="股票代码"),
        price: float = typer.Argument(..., help="成交价格"),
        quantity: int = typer.Argument(..., help="成交数量(股)"),
        name: str = typer.Option("", "--name", "-n", help="股票名称"),
        reason: str = typer.Option("", "--reason", "-r", help="交易理由"),
        strategy: str = typer.Option("", "--strategy", "-s", help="所用策略"),
        time: str = typer.Option("", "--time", help="交易时间"),
    ):
        """sell 的缩写"""
        _do_sell(code, price, quantity, name, reason, strategy, time)

    # --- trades / t ---
    @app.command("trades", help="查看交易记录 (缩写: t)")
    def quick_trades(
        code: str = typer.Option("", "--code", "-c", help="按股票代码过滤"),
        limit: int = typer.Option(20, "--limit", "-l", help="显示条数"),
    ):
        """查看交易记录"""
        cli_module.trade_list(code=code, action="", market="", limit=limit)

    @app.command("t", hidden=True)
    def alias_t(
        code: str = typer.Option("", "--code", "-c", help="按股票代码过滤"),
        limit: int = typer.Option(20, "--limit", "-l", help="显示条数"),
    ):
        """trades 的缩写"""
        cli_module.trade_list(code=code, action="", market="", limit=limit)

    # --- del-trade / dt ---
    @app.command("del-trade", help="删除交易记录 (缩写: dt)")
    def quick_del_trade(
        trade_id: int = typer.Argument(..., help="交易记录ID"),
        yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
    ):
        """删除交易记录"""
        cli_module.trade_delete(trade_id=trade_id, yes=yes)

    @app.command("dt", hidden=True)
    def alias_dt(
        trade_id: int = typer.Argument(..., help="交易记录ID"),
        yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
    ):
        """del-trade 的缩写"""
        cli_module.trade_delete(trade_id=trade_id, yes=yes)

    # ==================== 持仓管理 ====================

    @app.command("show", help="查看当前持仓 (缩写: w)")
    def quick_show():
        """查看当前持仓"""
        cli_module.portfolio_show()

    @app.command("w", hidden=True)
    def alias_w():
        """show 的缩写 (w = watch)"""
        cli_module.portfolio_show()

    @app.command("rebuild", help="重建持仓 (缩写: rb)")
    def quick_rebuild():
        """重建持仓"""
        cli_module.portfolio_rebuild()

    @app.command("rb", hidden=True)
    def alias_rb():
        """rebuild 的缩写"""
        cli_module.portfolio_rebuild()

    # ==================== 收藏列表 ====================

    @app.command("stars", help="查看自选股列表 (缩写: ss)")
    def quick_stars():
        """查看自选股列表"""
        cli_module.watchlist_list()

    @app.command("ss", hidden=True)
    def alias_ss():
        """stars 的缩写"""
        cli_module.watchlist_list()

    @app.command("star", help="添加自选股 (缩写: sa)")
    def quick_star(
        code: str = typer.Argument(..., help="股票代码 (如 600519, 支持自动识别sh/sz)"),
        note: str = typer.Option("", "--note", "-n", help="关注备注"),
    ):
        """添加自选股"""
        cli_module.watchlist_add(code=code, note=note)

    @app.command("sa", hidden=True)
    def alias_sa(
        code: str = typer.Argument(..., help="股票代码"),
        note: str = typer.Option("", "--note", "-n", help="关注备注"),
    ):
        """star 的缩写 (star-add)"""
        cli_module.watchlist_add(code=code, note=note)

    @app.command("unstar", help="取消收藏 (缩写: sd)")
    def quick_unstar(
        code: str = typer.Argument(..., help="股票代码"),
    ):
        """取消收藏"""
        cli_module.watchlist_remove(code=code)

    @app.command("sd", hidden=True)
    def alias_sd(
        code: str = typer.Argument(..., help="股票代码"),
    ):
        """unstar 的缩写 (star-delete)"""
        cli_module.watchlist_remove(code=code)

    # ==================== 行情查询 ====================

    @app.command("search", help="搜索股票 (缩写: sc)")
    def quick_search(keyword: str = typer.Argument(..., help="搜索关键词")):
        """搜索股票"""
        cli_module.market_search(keyword=keyword)

    @app.command("sc", hidden=True)
    def alias_sc(keyword: str = typer.Argument(..., help="搜索关键词")):
        """search 的缩写"""
        cli_module.market_search(keyword=keyword)

    @app.command("quote", help="查询实时行情 (缩写: q)")
    def quick_quote(codes: str = typer.Argument(..., help="股票代码(逗号分隔)")):
        """查询实时行情"""
        cli_module.market_quote(codes=codes)

    @app.command("q", hidden=True)
    def alias_q(codes: str = typer.Argument(..., help="股票代码(逗号分隔)")):
        """quote 的缩写"""
        cli_module.market_quote(codes=codes)

    @app.command("kline", help="查询K线数据 (缩写: k，加 -g 出图)")
    def quick_kline(
        code: str = typer.Argument(..., help="股票代码"),
        period: str = typer.Option("day", "--period", "-p", help="周期"),
        count: int = typer.Option(20, "--count", "-c", help="数量"),
        adjust: str = typer.Option("qfq", "--adjust", "-a", help="复权"),
        chart: bool = typer.Option(False, "--chart", "-g", help="显示K线图"),
    ):
        """查询K线数据"""
        cli_module.market_kline(code=code, period=period, count=count, adjust=adjust, chart=chart)

    @app.command("k", hidden=True)
    def alias_k(
        code: str = typer.Argument(..., help="股票代码"),
        period: str = typer.Option("day", "--period", "-p", help="周期"),
        count: int = typer.Option(20, "--count", "-c", help="数量"),
        adjust: str = typer.Option("qfq", "--adjust", "-a", help="复权"),
        chart: bool = typer.Option(False, "--chart", "-g", help="显示K线图"),
    ):
        """kline 的缩写"""
        cli_module.market_kline(code=code, period=period, count=count, adjust=adjust, chart=chart)

    @app.command("finance", help="查询财务数据 (缩写: f)")
    def quick_finance(
        code: str = typer.Argument(..., help="股票代码"),
        report_type: str = typer.Option("summary", "--type", "-t", help="报表类型"),
    ):
        """查询财务数据"""
        cli_module.market_finance(code=code, report_type=report_type)

    @app.command("f", hidden=True)
    def alias_f(
        code: str = typer.Argument(..., help="股票代码"),
        report_type: str = typer.Option("summary", "--type", "-t", help="报表类型"),
    ):
        """finance 的缩写"""
        cli_module.market_finance(code=code, report_type=report_type)

    @app.command("profile", help="查询公司简况 (缩写: pf)")
    def quick_profile(code: str = typer.Argument(..., help="股票代码")):
        """查询公司简况"""
        cli_module.market_profile(code=code)

    @app.command("pf", hidden=True)
    def alias_pf(code: str = typer.Argument(..., help="股票代码")):
        """profile 的缩写"""
        cli_module.market_profile(code=code)

    @app.command("fund", help="查询资金流向 (缩写: fd)")
    def quick_fund(
        code: str = typer.Argument(..., help="股票代码"),
        days: int = typer.Option(20, "--days", "-d", help="天数"),
    ):
        """查询资金流向"""
        cli_module.market_fund(code=code, days=days)

    @app.command("fd", hidden=True)
    def alias_fd(
        code: str = typer.Argument(..., help="股票代码"),
        days: int = typer.Option(20, "--days", "-d", help="天数"),
    ):
        """fund 的缩写"""
        cli_module.market_fund(code=code, days=days)

    @app.command("news", help="查询新闻资讯 (缩写: n)")
    def quick_news(
        code: str = typer.Argument(..., help="股票代码"),
        page: int = typer.Option(1, "--page", "-p", help="页码"),
        size: int = typer.Option(10, "--size", "-s", help="每页条数"),
    ):
        """查询新闻资讯"""
        cli_module.market_news(code=code, page=page, size=size)

    @app.command("n", hidden=True)
    def alias_n(
        code: str = typer.Argument(..., help="股票代码"),
        page: int = typer.Option(1, "--page", "-p", help="页码"),
        size: int = typer.Option(10, "--size", "-s", help="每页条数"),
    ):
        """news 的缩写"""
        cli_module.market_news(code=code, page=page, size=size)

    @app.command("chip")
    def quick_chip(code: str = typer.Argument(..., help="股票代码")):
        """查询筹码分布"""
        cli_module.market_chip(code=code)

    # ==================== 统计分析 ====================

    @app.command("summary", help="交易统计摘要 (缩写: sm)")
    def quick_summary(
        start: str = typer.Option("", "--start", help="开始日期"),
        end: str = typer.Option("", "--end", help="结束日期"),
        market: str = typer.Option("", "--market", "-m", help="市场"),
    ):
        """交易统计摘要"""
        cli_module.analysis_summary(start=start, end=end, market=market)

    @app.command("sm", hidden=True)
    def alias_sm(
        start: str = typer.Option("", "--start", help="开始日期"),
        end: str = typer.Option("", "--end", help="结束日期"),
        market: str = typer.Option("", "--market", "-m", help="市场"),
    ):
        """summary 的缩写"""
        cli_module.analysis_summary(start=start, end=end, market=market)

    @app.command("monthly", help="月度盈亏统计 (缩写: mo)")
    def quick_monthly(
        start: str = typer.Option("", "--start", help="开始日期"),
        end: str = typer.Option("", "--end", help="结束日期"),
    ):
        """月度盈亏统计"""
        cli_module.analysis_monthly(start=start, end=end)

    @app.command("mo", hidden=True)
    def alias_mo(
        start: str = typer.Option("", "--start", help="开始日期"),
        end: str = typer.Option("", "--end", help="结束日期"),
    ):
        """monthly 的缩写"""
        cli_module.analysis_monthly(start=start, end=end)

    @app.command("ranking", help="股票盈亏排名 (缩写: rk)")
    def quick_ranking():
        """股票盈亏排名"""
        cli_module.analysis_ranking()

    @app.command("rk", hidden=True)
    def alias_rk():
        """ranking 的缩写"""
        cli_module.analysis_ranking()

    @app.command("drawdown", help="最大回撤分析 (缩写: dd)")
    def quick_drawdown():
        """最大回撤分析"""
        cli_module.analysis_drawdown()

    @app.command("dd", hidden=True)
    def alias_dd():
        """drawdown 的缩写"""
        cli_module.analysis_drawdown()

    # ==================== 可视化图表 ====================

    @app.command("chart-pnl", help="绘制收益曲线 (缩写: c-pnl)")
    def quick_chart_pnl():
        """绘制收益曲线"""
        cli_module.chart_pnl()

    @app.command("c-pnl", hidden=True)
    def alias_c_pnl():
        """chart-pnl 的缩写"""
        cli_module.chart_pnl()

    @app.command("chart-kline", help="绘制K线图 (缩写: c-k)")
    def quick_chart_kline(
        code: str = typer.Argument(..., help="股票代码"),
        period: str = typer.Option("day", "--period", "-p", help="K线周期"),
        count: int = typer.Option(60, "--count", "-c", help="K线数量"),
    ):
        """绘制K线图"""
        cli_module.chart_kline(code=code, period=period, count=count)

    @app.command("c-k", hidden=True)
    def alias_c_k(
        code: str = typer.Argument(..., help="股票代码"),
        period: str = typer.Option("day", "--period", "-p", help="K线周期"),
        count: int = typer.Option(60, "--count", "-c", help="K线数量"),
    ):
        """chart-kline 的缩写"""
        cli_module.chart_kline(code=code, period=period, count=count)

    @app.command("chart-portfolio", help="绘制持仓分布图 (缩写: c-pf)")
    def quick_chart_portfolio():
        """绘制持仓分布图"""
        cli_module.chart_portfolio()

    @app.command("c-pf", hidden=True)
    def alias_c_pf():
        """chart-portfolio 的缩写"""
        cli_module.chart_portfolio()

    @app.command("chart-winloss", help="绘制胜负统计图 (缩写: c-wl)")
    def quick_chart_winloss():
        """绘制胜负统计图"""
        cli_module.chart_winloss()

    @app.command("c-wl", hidden=True)
    def alias_c_wl():
        """chart-winloss 的缩写"""
        cli_module.chart_winloss()

    @app.command("chart-monthly", help="绘制月度盈亏图 (缩写: c-mo)")
    def quick_chart_monthly():
        """绘制月度盈亏图"""
        cli_module.chart_monthly()

    @app.command("c-mo", hidden=True)
    def alias_c_mo():
        """chart-monthly 的缩写"""
        cli_module.chart_monthly()

    # ==================== AI 预测 ====================

    @app.command("predict", help="AI 预测股票走势 (缩写: p)")
    def quick_predict(
        code: str = typer.Argument(..., help="股票代码 (如 600519, 支持自动识别sh/sz)"),
        dl: bool = typer.Option(False, "--dl", help="同时使用深度学习模型"),
        llm: bool = typer.Option(False, "--llm", help="追加 LLM 分析点评"),
    ):
        """AI 预测"""
        cli_module.ai_predict(code=code, dl=dl, llm=llm)

    @app.command("p", hidden=True)
    def alias_p(
        code: str = typer.Argument(..., help="股票代码"),
        dl: bool = typer.Option(False, "--dl", help="使用 DL 模型"),
        llm: bool = typer.Option(False, "--llm", help="追加 LLM 分析点评"),
    ):
        """predict 的缩写"""
        cli_module.ai_predict(code=code, dl=dl, llm=llm)

    @app.command("analyze", help="LLM 深度分析 (缩写: a)")
    def quick_analyze(
        code: str = typer.Argument(..., help="股票代码 (如 600519, 支持自动识别sh/sz)"),
        dl: bool = typer.Option(False, "--dl", help="同时使用深度学习模型"),
    ):
        """LLM 深度分析"""
        cli_module.ai_analyze(code=code, dl=dl)

    @app.command("a", hidden=True)
    def alias_a(
        code: str = typer.Argument(..., help="股票代码"),
        dl: bool = typer.Option(False, "--dl", help="使用 DL 模型"),
    ):
        """analyze 的缩写"""
        cli_module.ai_analyze(code=code, dl=dl)

    @app.command("scan", help="扫描自选股 AI 信号")
    def quick_scan(
        dl: bool = typer.Option(False, "--dl", help="同时使用深度学习模型"),
        llm: bool = typer.Option(False, "--llm", help="对前5名追加 LLM 分析"),
    ):
        """扫描自选股信号排名"""
        cli_module.ai_scan(dl=dl, llm=llm)

    @app.command("train-ai", help="训练 AI 预测模型")
    def quick_train_ai(
        code: str = typer.Argument(..., help="股票代码"),
        dl: bool = typer.Option(False, "--dl", help="同时训练 DL 模型"),
    ):
        """训练预测模型"""
        cli_module.ai_train(code=code, dl=dl)

    @app.command("test-llm", help="测试 LLM 连接")
    def quick_test_llm():
        """测试 LLM 连接是否正常"""
        from app.ai.predictor_service import PredictorService
        from app.commands import console, Panel

        svc = PredictorService()
        with console.status("[cyan]测试 LLM 连接...[/cyan]"):
            result = svc.test_llm()

        if result["ok"]:
            console.print(Panel(
                f"[green]✅ {result['message']}[/green]\n"
                f"Provider: {result.get('provider', '?')}\n"
                f"Model: {result.get('model', '?')}",
                title="LLM 连接测试",
                border_style="green",
            ))
        else:
            console.print(Panel(
                f"[red]❌ {result['message']}[/red]",
                title="LLM 连接测试",
                border_style="red",
            ))

    # ==================== 回测引擎 ====================

    @app.command("bt", help="回测股票策略 (回测引擎)")
    def quick_bt(
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
        cli_module.backtest_run(
            code=code, strategy=strategy, days=days, capital=capital,
            stop_loss=stop_loss, take_profit=take_profit, position=position, chart=chart,
        )

    @app.command("bt-list", help="查看可用回测策略")
    def quick_bt_list():
        """查看可用回测策略"""
        cli_module.backtest_strategies()

    @app.command("bt-compare", help="多策略对比回测")
    def quick_bt_compare(
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
        cli_module.backtest_compare(code=code, days=days, capital=capital, strategies=strategies)

    # ==================== 预警监控快捷命令 ====================

    @app.command("alert-add", help="添加预警规则 (缩写: al-a)")
    def quick_alert_add(
        code: str = typer.Argument(..., help="股票代码 (如 600519, 支持自动识别sh/sz)"),
        condition: str = typer.Argument(..., help="条件类型 (price_above/rsi_below/macd_cross 等)"),
        threshold: float = typer.Option(None, "--threshold", "-t", help="阈值"),
        repeat: bool = typer.Option(False, "--repeat", "-r", help="可重复触发"),
        note: str = typer.Option("", "--note", "-n", help="备注"),
    ):
        """添加预警规则"""
        cli_module.alert_add_cmd(code=code, condition=condition, threshold=threshold, repeat=repeat, note=note)

    @app.command("al-a", hidden=True)
    def alias_al_a(
        code: str = typer.Argument(..., help="股票代码"),
        condition: str = typer.Argument(..., help="条件类型"),
        threshold: float = typer.Option(None, "--threshold", "-t", help="阈值"),
        repeat: bool = typer.Option(False, "--repeat", "-r", help="可重复触发"),
        note: str = typer.Option("", "--note", "-n", help="备注"),
    ):
        """alert-add 的缩写"""
        cli_module.alert_add_cmd(code=code, condition=condition, threshold=threshold, repeat=repeat, note=note)

    @app.command("alert-list", help="查看预警规则列表 (缩写: al-l)")
    def quick_alert_list(
        code: str = typer.Option("", "--code", "-c", help="按股票代码过滤"),
        active: bool = typer.Option(False, "--active", "-a", help="仅显示启用的"),
    ):
        """查看预警规则"""
        cli_module.alert_list_cmd(code=code, active=active)

    @app.command("al-l", hidden=True)
    def alias_al_l(
        code: str = typer.Option("", "--code", "-c", help="按股票代码过滤"),
        active: bool = typer.Option(False, "--active", "-a", help="仅显示启用的"),
    ):
        """alert-list 的缩写"""
        cli_module.alert_list_cmd(code=code, active=active)

    @app.command("alert-del", help="删除预警规则 (缩写: al-d)")
    def quick_alert_del(
        alert_id: int = typer.Argument(..., help="预警规则 ID"),
        yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
    ):
        """删除预警规则"""
        cli_module.alert_delete_cmd(alert_id=alert_id, yes=yes)

    @app.command("al-d", hidden=True)
    def alias_al_d(
        alert_id: int = typer.Argument(..., help="预警规则 ID"),
        yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
    ):
        """alert-del 的缩写"""
        cli_module.alert_delete_cmd(alert_id=alert_id, yes=yes)

    @app.command("alert-toggle", help="启用/暂停预警 (缩写: al-t)")
    def quick_alert_toggle(
        alert_id: int = typer.Argument(..., help="预警规则 ID"),
    ):
        """启用/暂停预警"""
        cli_module.alert_toggle_cmd(alert_id=alert_id)

    @app.command("al-t", hidden=True)
    def alias_al_t(
        alert_id: int = typer.Argument(..., help="预警规则 ID"),
    ):
        """alert-toggle 的缩写"""
        cli_module.alert_toggle_cmd(alert_id=alert_id)

    @app.command("alert-reset", help="重置预警 (缩写: al-r)")
    def quick_alert_reset(
        alert_id: int = typer.Argument(..., help="预警规则 ID"),
    ):
        """重置预警"""
        cli_module.alert_reset_cmd(alert_id=alert_id)

    @app.command("al-r", hidden=True)
    def alias_al_r(
        alert_id: int = typer.Argument(..., help="预警规则 ID"),
    ):
        """alert-reset 的缩写"""
        cli_module.alert_reset_cmd(alert_id=alert_id)

    @app.command("alert-check", help="立即检测预警 (缩写: al-c)")
    def quick_alert_check():
        """立即检测一次所有预警"""
        cli_module.alert_check_cmd()

    @app.command("al-c", hidden=True)
    def alias_al_c():
        """alert-check 的缩写"""
        cli_module.alert_check_cmd()

    @app.command("alert-history", help="预警触发历史 (缩写: al-h)")
    def quick_alert_history(
        code: str = typer.Option("", "--code", "-c", help="按股票代码过滤"),
        alert_id: int = typer.Option(0, "--id", help="按预警规则 ID 过滤"),
        limit: int = typer.Option(20, "--limit", "-l", help="显示条数"),
    ):
        """预警触发历史"""
        cli_module.alert_history_cmd(code=code, alert_id=alert_id, limit=limit)

    @app.command("al-h", hidden=True)
    def alias_al_h(
        code: str = typer.Option("", "--code", "-c", help="按股票代码过滤"),
        alert_id: int = typer.Option(0, "--id", help="按预警规则 ID 过滤"),
        limit: int = typer.Option(20, "--limit", "-l", help="显示条数"),
    ):
        """alert-history 的缩写"""
        cli_module.alert_history_cmd(code=code, alert_id=alert_id, limit=limit)

    @app.command("alert-types", help="查看预警条件类型 (缩写: al-tp)")
    def quick_alert_types():
        """查看支持的预警条件类型"""
        cli_module.alert_types_cmd()

    @app.command("al-tp", hidden=True)
    def alias_al_tp():
        """alert-types 的缩写"""
        cli_module.alert_types_cmd()

    # ==================== 实时看盘 ====================

    @app.command("watch", help="实时看盘模式 (缩写: wa)")
    def quick_watch(
        codes: str = typer.Option("", "--codes", "-c", help="股票代码(逗号分隔, 默认自选股)"),
        interval: int = typer.Option(30, "--interval", "-i", help="刷新间隔(秒)"),
        alert_only: bool = typer.Option(False, "--alert-only", help="仅监控预警，不显示行情"),
        sort_by: str = typer.Option("chg", "--sort", "-s", help="排序字段: chg(涨跌幅) amp(振幅) vol(成交额) vr(量比) tr(换手率)"),
    ):
        """实时看盘模式（自动刷新行情 + 预警检测）"""
        from app.commands.watch import do_watch
        do_watch(codes, interval, alert_only, sort_by)

    @app.command("wa", hidden=True)
    def alias_wa(
        codes: str = typer.Option("", "--codes", "-c", help="股票代码(逗号分隔)"),
        interval: int = typer.Option(30, "--interval", "-i", help="刷新间隔(秒)"),
        alert_only: bool = typer.Option(False, "--alert-only", help="仅监控预警"),
        sort_by: str = typer.Option("chg", "--sort", "-s", help="排序字段: chg/amp/vol/vr/tr"),
    ):
        """watch 的缩写"""
        from app.commands.watch import do_watch
        do_watch(codes, interval, alert_only, sort_by)

    # ==================== 消息推送 ====================

    @app.command("notify-test", help="发送测试通知 (缩写: nt)")
    def quick_notify_test(
        channel: str = typer.Option("", "--channel", "-c", help="指定渠道"),
    ):
        """发送测试通知到已启用的推送渠道"""
        cli_module._notify_test_impl(channel)

    @app.command("nt", hidden=True)
    def alias_nt(
        channel: str = typer.Option("", "--channel", "-c", help="指定渠道"),
    ):
        """notify-test 的缩写"""
        cli_module._notify_test_impl(channel)

    @app.command("notify-list", help="查看推送渠道配置 (缩写: nl)")
    def quick_notify_list():
        """查看推送渠道配置"""
        cli_module._notify_list_impl()

    @app.command("nl", hidden=True)
    def alias_nl():
        """notify-list 的缩写"""
        cli_module._notify_list_impl()

    # ==================== 智能日报 ====================

    @app.command("digest", help="生成自选股智能日报 (缩写: dg)")
    def quick_digest(
        dl: bool = typer.Option(False, "--dl", help="使用深度学习模型"),
        llm: bool = typer.Option(False, "--llm", help="追加 LLM 深度分析"),
        push: bool = typer.Option(False, "--push", "-p", help="生成后推送"),
        auto_alert: bool = typer.Option(False, "--auto-alert", help="自动为高风险股票配置预警"),
    ):
        """生成自选股智能日报（AI 盯盘助手）"""
        cli_module.digest_run(dl=dl, llm=llm, top=3, bottom=2, push=push, auto_alert=auto_alert)

    @app.command("dg", hidden=True)
    def alias_dg(
        dl: bool = typer.Option(False, "--dl", help="使用深度学习模型"),
        llm: bool = typer.Option(False, "--llm", help="追加 LLM 深度分析"),
        push: bool = typer.Option(False, "--push", "-p", help="生成后推送"),
        auto_alert: bool = typer.Option(False, "--auto-alert", help="自动为高风险股票配置预警"),
    ):
        """digest 的缩写"""
        cli_module.digest_run(dl=dl, llm=llm, top=3, bottom=2, push=push, auto_alert=auto_alert)

    @app.command("digest-push", help="生成并推送智能日报 (缩写: dg-p)")
    def quick_digest_push(
        dl: bool = typer.Option(False, "--dl", help="使用深度学习模型"),
        llm: bool = typer.Option(False, "--llm", help="追加 LLM 分析"),
    ):
        """生成并推送智能日报"""
        cli_module.digest_push(dl=dl, llm=llm)

    @app.command("dg-p", hidden=True)
    def alias_dg_p(
        dl: bool = typer.Option(False, "--dl", help="使用深度学习模型"),
        llm: bool = typer.Option(False, "--llm", help="追加 LLM 分析"),
    ):
        """digest-push 的缩写"""
        cli_module.digest_push(dl=dl, llm=llm)

    @app.command("digest-preview", help="快速预览智能日报 (缩写: dg-v)")
    def quick_digest_preview(
        dl: bool = typer.Option(False, "--dl", help="使用深度学习模型"),
    ):
        """快速预览智能日报（仅扫描，不 LLM 不推送）"""
        cli_module.digest_preview(dl=dl)

    @app.command("dg-v", hidden=True)
    def alias_dg_v(
        dl: bool = typer.Option(False, "--dl", help="使用深度学习模型"),
    ):
        """digest-preview 的缩写"""
        cli_module.digest_preview(dl=dl)

    # ==================== TUI Dashboard ====================

    @app.command("dashboard", help="启动 TUI 全屏 Dashboard (缩写: d)")
    def dashboard(
        interval: int = typer.Option(30, "--interval", "-i", help="自动刷新间隔(秒)"),
    ):
        """启动全屏交互式 Dashboard"""
        from app.tui.app import run_dashboard
        run_dashboard(refresh_interval=float(interval))

    @app.command("d", hidden=True)
    def alias_d(
        interval: int = typer.Option(30, "--interval", "-i", help="自动刷新间隔(秒)"),
    ):
        """dashboard 的缩写"""
        from app.tui.app import run_dashboard
        run_dashboard(refresh_interval=float(interval))

"""Stock Trader AI - CLI 命令行入口

使用 typer 实现所有命令，用 rich 美化输出。

扁平化命令结构（支持缩写）：
    stock-ai buy(b)/sell(s)/trades(t)/del-trade(dt)   交易管理
    stock-ai show(w)/rebuild(rb)                      持仓管理
    stock-ai stars(ss)/star(sa)/unstar(sd)            自选股/收藏列表
    stock-ai search(sc)/quote(q)/kline(k)/finance(f)  行情查询
    stock-ai summary(sm)/monthly(mo)/ranking(rk)      统计分析
    stock-ai chart-*(c-*)                             可视化
    stock-ai predict(p)/scan/train-ai                 AI 预测 (ML/DL)
    stock-ai analyze(a)/test-llm                      LLM 深度分析
    stock-ai alert-*(al-*)/watch(wa)                  实时监控/条件预警
    stock-ai bt/bt-list/bt-compare                    回测引擎
    stock-ai digest(dg)/digest-push(dg-p)             智能日报/AI盯盘助手
    stock-ai dashboard(d)                             TUI 全屏面板
"""

import sys
import os

# 修复 Windows 终端编码问题
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box
from datetime import datetime
from typing import Optional

from app.db.database import init_db
from app.models.stock import normalize_stock_code, normalize_stock_codes

console = Console(force_terminal=True)
app = typer.Typer(
    name="stock-ai",
    help="Stock Trader AI - AI辅助股票交易工具",
    no_args_is_help=True,
)

# 保留子命令组作为可选的分组入口（兼容 stock-ai trade list 等旧用法）
trade_app = typer.Typer(help="交易记录管理", no_args_is_help=True, hidden=True)
portfolio_app = typer.Typer(help="持仓管理", no_args_is_help=True, hidden=True)
watchlist_app = typer.Typer(help="自选股/收藏列表", no_args_is_help=True, hidden=True)
market_app = typer.Typer(help="行情数据查询", no_args_is_help=True, hidden=True)
analysis_app = typer.Typer(help="统计分析", no_args_is_help=True, hidden=True)
chart_app = typer.Typer(help="可视化图表", no_args_is_help=True, hidden=True)
ai_app = typer.Typer(help="AI 预测分析", no_args_is_help=True, hidden=True)
alert_app = typer.Typer(help="预警监控管理", no_args_is_help=True, hidden=True)
backtest_app = typer.Typer(help="回测引擎", no_args_is_help=True, hidden=True)
notify_app = typer.Typer(help="消息推送管理", no_args_is_help=True, hidden=True)
digest_app = typer.Typer(help="智能日报（AI 盯盘助手）", no_args_is_help=True, hidden=True)

app.add_typer(trade_app, name="trade")
app.add_typer(portfolio_app, name="portfolio")
app.add_typer(watchlist_app, name="watchlist")
app.add_typer(market_app, name="market")
app.add_typer(analysis_app, name="analysis")
app.add_typer(chart_app, name="chart")
app.add_typer(ai_app, name="ai")
app.add_typer(alert_app, name="alert")
app.add_typer(backtest_app, name="backtest")
app.add_typer(notify_app, name="notify")
app.add_typer(digest_app, name="digest")



# ==================== 初始化回调 ====================
@app.callback()
def main_callback():
    """初始化数据库"""
    init_db()


# ==================== 交易管理 ====================
@trade_app.command("add")
def trade_add(
    code: str = typer.Option(..., "--code", "-c", help="股票代码 (如 600519, 支持自动识别sh/sz)"),
    action: str = typer.Option(..., "--action", "-a", help="买卖方向: buy/sell"),
    price: float = typer.Option(..., "--price", "-p", help="成交价格"),
    quantity: int = typer.Option(..., "--quantity", "-q", help="成交数量(股)"),
    name: str = typer.Option("", "--name", "-n", help="股票名称"),
    commission: float = typer.Option(0.0, "--commission", help="手续费(自动计算)"),
    tax: float = typer.Option(0.0, "--tax", help="印花税(自动计算)"),
    reason: str = typer.Option("", "--reason", "-r", help="交易理由"),
    strategy: str = typer.Option("", "--strategy", "-s", help="所用策略"),
    tags: str = typer.Option("", "--tags", "-t", help="标签(逗号分隔)"),
    note: str = typer.Option("", "--note", help="备注"),
    time: str = typer.Option("", "--time", help="交易时间 (YYYY-MM-DD HH:MM:SS)"),
):
    """添加一笔交易记录"""
    from app.services.trade_service import TradeService

    trade_time = None
    if time:
        try:
            trade_time = datetime.strptime(time, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                trade_time = datetime.strptime(time, "%Y-%m-%d")
            except ValueError:
                console.print("[red]❌ 时间格式错误，请使用 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS[/red]")
                raise typer.Exit(1)

    svc = TradeService()
    trade = svc.add_trade(
        stock_code=code,
        action=action,
        price=price,
        quantity=quantity,
        stock_name=name,
        commission=commission,
        tax=tax,
        reason=reason,
        strategy=strategy,
        tags=tags,
        note=note,
        trade_time=trade_time,
    )

    action_text = "[red]买入[/red]" if action == "buy" else "[green]卖出[/green]"
    display_name = trade.stock_name or name
    console.print(
        Panel(
            f"{action_text} {code} {display_name}\n"
            f"价格: {price}  数量: {quantity}  金额: {trade.amount:,.2f}\n"
            f"手续费: {trade.commission:.2f}  印花税: {trade.tax:.2f}",
            title=f"✅ 交易记录已添加 (ID: {trade.id})",
            border_style="green",
        )
    )

    # 自动重建持仓
    from app.services.portfolio_service import PortfolioService
    PortfolioService().rebuild_portfolio()


@trade_app.command("list")
def trade_list(
    code: str = typer.Option("", "--code", "-c", help="按股票代码过滤"),
    action: str = typer.Option("", "--action", "-a", help="按买卖过滤: buy/sell"),
    market: str = typer.Option("", "--market", "-m", help="按市场过滤: A/HK/US"),
    limit: int = typer.Option(20, "--limit", "-l", help="显示条数"),
):
    """查看交易记录"""
    from app.services.trade_service import TradeService

    svc = TradeService()
    trades = svc.list_trades(stock_code=code, action=action, market=market, limit=limit)

    if not trades:
        console.print("[yellow]📭 没有交易记录[/yellow]")
        return

    table = Table(
        title="📝 交易记录",
        box=box.ROUNDED,
        show_lines=True,
        header_style="bold cyan",
    )
    table.add_column("ID", style="dim", width=5)
    table.add_column("日期", width=12)
    table.add_column("代码", width=10)
    table.add_column("名称", width=10)
    table.add_column("买卖", width=5, justify="center")
    table.add_column("价格", width=10, justify="right")
    table.add_column("数量", width=8, justify="right")
    table.add_column("金额", width=12, justify="right")
    table.add_column("盈亏", width=12, justify="right")
    table.add_column("理由", width=15)

    for t in trades:
        action_str = "[red]买入[/red]" if t.action == "buy" else "[green]卖出[/green]"
        profit_str = ""
        if t.profit is not None:
            color = "green" if t.profit >= 0 else "red"
            profit_str = f"[{color}]{t.profit:+,.2f}[/{color}]"
            if t.profit_rate is not None:
                profit_str += f"\n[{color}]({t.profit_rate:+.2f}%)[/{color}]"

        table.add_row(
            str(t.id),
            t.trade_time.strftime("%Y-%m-%d"),
            t.stock_code,
            t.stock_name or "",
            action_str,
            f"{t.price:,.4f}",
            f"{t.quantity:,}",
            f"{t.amount:,.2f}",
            profit_str,
            (t.reason or "")[:15],
        )

    console.print(table)
    console.print(f"[dim]共 {len(trades)} 条记录[/dim]")


@trade_app.command("delete")
def trade_delete(
    trade_id: int = typer.Argument(..., help="交易记录ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
):
    """删除交易记录"""
    from app.services.trade_service import TradeService

    svc = TradeService()
    trade = svc.get_trade(trade_id)
    if not trade:
        console.print(f"[red]❌ 找不到 ID={trade_id} 的交易记录[/red]")
        raise typer.Exit(1)

    if not yes:
        console.print(f"即将删除: {trade}")
        confirm = typer.confirm("确定删除？")
        if not confirm:
            return

    svc.delete_trade(trade_id)
    console.print(f"[green]✅ 已删除交易记录 ID={trade_id}[/green]")

    from app.services.portfolio_service import PortfolioService
    PortfolioService().rebuild_portfolio()


@trade_app.command("export")
def trade_export(
    filepath: str = typer.Option("./data/exports/trades.csv", "--file", "-f", help="导出文件路径"),
    code: str = typer.Option("", "--code", "-c", help="按股票代码过滤"),
):
    """导出交易记录为 CSV"""
    from app.services.trade_service import TradeService

    svc = TradeService()
    path = svc.export_csv(filepath=filepath, stock_code=code)
    console.print(f"[green][OK] 已导出到: {path}[/green]")


@trade_app.command("import")
def trade_import(
    filepath: str = typer.Argument(..., help="CSV 文件路径"),
):
    """从 CSV 文件导入交易记录"""
    from app.services.trade_service import TradeService

    svc = TradeService()
    count = svc.import_csv(filepath)
    console.print(f"[green]✅ 成功导入 {count} 条交易记录[/green]")

    from app.services.portfolio_service import PortfolioService
    PortfolioService().rebuild_portfolio()


# ==================== 持仓管理 ====================
@portfolio_app.command("show")
def portfolio_show():
    """查看当前持仓"""
    from app.services.portfolio_service import PortfolioService

    svc = PortfolioService()
    summary = svc.get_total_summary()
    holdings = summary.get("holdings", [])

    if not holdings:
        console.print("[yellow]当前没有持仓[/yellow]")
        return

    table = Table(
        title="当前持仓",
        box=box.ROUNDED,
        show_lines=True,
        header_style="bold cyan",
    )
    table.add_column("代码", width=10)
    table.add_column("名称", width=10)
    table.add_column("持仓", width=8, justify="right")
    table.add_column("成本价", width=10, justify="right")
    table.add_column("现价", width=10, justify="right")
    table.add_column("市值", width=12, justify="right")
    table.add_column("浮动盈亏", width=12, justify="right")
    table.add_column("盈亏率", width=8, justify="right")
    table.add_column("今日涨跌", width=8, justify="right")

    for h in holdings:
        pnl = h.get("unrealized_profit", 0)
        pnl_rate = h.get("unrealized_profit_rate", 0)
        chg = h.get("change_percent", 0)
        pnl_color = "green" if pnl >= 0 else "red"
        chg_color = "green" if chg >= 0 else "red"

        table.add_row(
            h["stock_code"],
            h.get("stock_name", ""),
            f"{h['quantity']:,}",
            f"{h['avg_cost']:.2f}",
            f"{h.get('current_price', 0):.2f}",
            f"{h.get('market_value', 0):,.2f}",
            f"[{pnl_color}]{pnl:+,.2f}[/{pnl_color}]",
            f"[{pnl_color}]{pnl_rate:+.2f}%[/{pnl_color}]",
            f"[{chg_color}]{chg:+.2f}%[/{chg_color}]",
        )

    console.print(table)

    # 汇总信息
    console.print(
        Panel(
            f"持仓数量: {summary['holding_count']}\n"
            f"总成本: {summary['total_cost']:,.2f}  总市值: {summary['total_market_value']:,.2f}\n"
            f"浮动盈亏: {summary['total_unrealized_profit']:+,.2f} "
            f"({summary['total_unrealized_profit_rate']:+.2f}%)\n"
            f"已实现盈亏: {summary['total_realized_profit']:+,.2f}\n"
            f"总盈亏: {summary['total_profit']:+,.2f}",
            title="📊 持仓汇总",
            border_style="blue",
        )
    )


@portfolio_app.command("rebuild")
def portfolio_rebuild():
    """重建持仓（根据交易记录重新计算）"""
    from app.services.portfolio_service import PortfolioService

    svc = PortfolioService()
    svc.rebuild_portfolio()
    console.print("[green]✅ 持仓已重建[/green]")


# ==================== 收藏列表（自选股） ====================
@watchlist_app.command("list")
def watchlist_list():
    """查看自选股列表（带实时行情）"""
    from app.services.watchlist_service import WatchlistService

    svc = WatchlistService()
    stocks = svc.list_watched_with_quote()

    if not stocks:
        console.print("[yellow]⭐ 收藏列表为空，使用 [bold]stock-ai star <代码>[/bold] 添加关注[/yellow]")
        return

    table = Table(
        title="⭐ 自选股列表",
        box=box.ROUNDED,
        show_lines=True,
        header_style="bold cyan",
    )
    table.add_column("代码", width=10)
    table.add_column("名称", width=10)
    table.add_column("现价", width=10, justify="right")
    table.add_column("涨跌幅", width=10, justify="right")
    table.add_column("涨跌额", width=10, justify="right")
    table.add_column("最高", width=10, justify="right")
    table.add_column("最低", width=10, justify="right")
    table.add_column("成交量", width=10, justify="right")
    table.add_column("市盈率", width=8, justify="right")
    table.add_column("备注", width=15)

    for s in stocks:
        chg = s.get("change_percent", 0)
        color = "green" if chg >= 0 else "red"
        vol = s.get("volume", 0)
        vol_str = f"{vol / 10000:.1f}万" if vol > 10000 else str(int(vol)) if vol else "-"

        price_str = f"{s['price']:.2f}" if s["price"] else "-"

        table.add_row(
            s["code"],
            s.get("name", ""),
            price_str,
            f"[{color}]{chg:+.2f}%[/{color}]" if s["price"] else "-",
            f"[{color}]{s.get('change', 0):+.2f}[/{color}]" if s["price"] else "-",
            f"{s.get('high', 0):.2f}" if s.get("high") else "-",
            f"{s.get('low', 0):.2f}" if s.get("low") else "-",
            vol_str,
            f"{s.get('pe_ratio', 0):.2f}" if s.get("pe_ratio") else "-",
            (s.get("note", "") or "")[:15],
        )

    console.print(table)
    console.print(f"[dim]共关注 {len(stocks)} 只股票[/dim]")


@watchlist_app.command("add")
def watchlist_add(
    code: str = typer.Argument(..., help="股票代码 (如 600519, 支持自动识别sh/sz)"),
    note: str = typer.Option("", "--note", "-n", help="关注备注/理由"),
):
    """添加自选股"""
    from app.services.watchlist_service import WatchlistService

    svc = WatchlistService()
    stock = svc.add_watch(code, note)
    console.print(Panel(
        f"[bold]{stock.code}[/bold] {stock.name or ''}\n"
        f"备注: {stock.watch_note or '无'}",
        title="⭐ 已添加到收藏列表",
        border_style="yellow",
    ))


@watchlist_app.command("remove")
def watchlist_remove(
    code: str = typer.Argument(..., help="股票代码"),
):
    """取消收藏"""
    from app.services.watchlist_service import WatchlistService

    svc = WatchlistService()
    ok = svc.remove_watch(code)
    if ok:
        console.print(f"[green]✅ 已从收藏列表移除 {code}[/green]")
    else:
        console.print(f"[red]❌ 收藏列表中没有 {code}[/red]")


@watchlist_app.command("note")
def watchlist_note(
    code: str = typer.Argument(..., help="股票代码"),
    note: str = typer.Argument(..., help="备注内容"),
):
    """更新自选股备注"""
    from app.services.watchlist_service import WatchlistService

    svc = WatchlistService()
    ok = svc.update_note(code, note)
    if ok:
        console.print(f"[green]✅ 已更新 {code} 的备注[/green]")
    else:
        console.print(f"[red]❌ 收藏列表中没有 {code}[/red]")


# ==================== 行情查询 ====================
@market_app.command("search")
def market_search(
    keyword: str = typer.Argument(..., help="搜索关键词"),
):
    """搜索股票"""
    from app.services.market_service import MarketService

    svc = MarketService()
    result = svc.search(keyword)
    console.print(result)


@market_app.command("quote")
def market_quote(
    codes: str = typer.Argument(..., help="股票代码(逗号分隔, 如 600519,00700, 自动识别前缀)"),
):
    """查询实时行情"""
    from app.services.market_service import MarketService
    import json

    svc = MarketService()
    code_list = [normalize_stock_code(c.strip()) for c in codes.split(",")]
    data = svc.get_quote(*code_list)

    if not data:
        console.print("[red]❌ 获取行情失败[/red]")
        return

    table = Table(title="📈 实时行情", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("代码", width=10)
    table.add_column("名称", width=10)
    table.add_column("现价", width=10, justify="right")
    table.add_column("涨跌幅", width=10, justify="right")
    table.add_column("涨跌额", width=10, justify="right")
    table.add_column("今开", width=10, justify="right")
    table.add_column("最高", width=10, justify="right")
    table.add_column("最低", width=10, justify="right")
    table.add_column("成交量", width=10, justify="right")
    table.add_column("市盈率", width=8, justify="right")

    for code in code_list:
        q = data.get(code, {})
        if not q:
            continue
        chg = q.get("change_percent", 0)
        color = "green" if chg >= 0 else "red"
        vol = q.get("volume", 0)
        vol_str = f"{vol / 10000:.1f}万" if vol > 10000 else str(vol)

        table.add_row(
            code,
            q.get("name", ""),
            f"{q.get('price', 0):.2f}",
            f"[{color}]{chg:+.2f}%[/{color}]",
            f"[{color}]{q.get('change', 0):+.2f}[/{color}]",
            f"{q.get('open', 0):.2f}",
            f"{q.get('high', 0):.2f}",
            f"{q.get('low', 0):.2f}",
            vol_str,
            f"{q.get('pe_ratio', 0):.2f}",
        )

    console.print(table)


@market_app.command("kline")
def market_kline(
    code: str = typer.Argument(..., help="股票代码"),
    period: str = typer.Option("day", "--period", "-p", help="周期: day/week/month/m5/m15/m30/m60"),
    count: int = typer.Option(20, "--count", "-c", help="获取数量"),
    adjust: str = typer.Option("qfq", "--adjust", "-a", help="复权: qfq/hfq/空"),
    chart: bool = typer.Option(False, "--chart", "-g", help="显示K线图(含均线+MACD)"),
):
    """查询K线数据 (加 -g 出图)"""
    from app.services.market_service import MarketService

    # 出图时自动拉取更多数据（至少60条才够画均线）
    fetch_count = max(count, 80) if chart else count

    svc = MarketService()
    df = svc.get_kline_df(code, period, fetch_count, adjust)

    if df.empty:
        console.print("[red]❌ 获取K线数据失败[/red]")
        return

    # 表格展示（只显示用户请求的条数）
    show_df = df.tail(count) if len(df) > count else df

    table = Table(title=f"📊 {code} {period}K线 (最近{count}条)", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("日期", width=12)
    table.add_column("开盘", width=10, justify="right")
    table.add_column("收盘", width=10, justify="right")
    table.add_column("最高", width=10, justify="right")
    table.add_column("最低", width=10, justify="right")
    table.add_column("涨跌幅", width=8, justify="right")
    table.add_column("成交量", width=10, justify="right")
    table.add_column("换手率", width=8, justify="right")

    for _, row in show_df.iterrows():
        chg = (row["close"] - row["open"]) / row["open"] * 100 if row["open"] > 0 else 0
        color = "green" if chg >= 0 else "red"
        vol = row["volume"]
        vol_str = f"{vol / 10000:.1f}万" if vol > 10000 else f"{vol:.0f}"

        date_str = row["date"].strftime("%Y-%m-%d") if hasattr(row["date"], "strftime") else str(row["date"])[:10]
        table.add_row(
            date_str,
            f"{row['open']:.2f}",
            f"[{color}]{row['close']:.2f}[/{color}]",
            f"{row['high']:.2f}",
            f"{row['low']:.2f}",
            f"[{color}]{chg:+.2f}%[/{color}]",
            vol_str,
            f"{row.get('turnover_rate', 0):.2f}%",
        )

    console.print(table)

    # 出图
    if chart:
        from app.visualization.charts import ChartService

        console.print("[dim]📈 正在绘制K线图...[/dim]")
        path = ChartService().plot_kline(
            df,
            title=f"{code} {period}K线",
            show_ma=True,
            show_macd=True,
        )
        if path:
            console.print(f"[green]✅ K线图已保存: {path}[/green]")


@market_app.command("finance")
def market_finance(
    code: str = typer.Argument(..., help="股票代码"),
    report_type: str = typer.Option("summary", "--type", "-t", help="报表类型: summary/lrb/zcfz/xjll"),
):
    """查询财务数据"""
    from app.services.market_service import MarketService
    import json

    svc = MarketService()
    data = svc.get_finance(code, report_type)
    console.print_json(json.dumps(data, ensure_ascii=False, indent=2))


@market_app.command("profile")
def market_profile(
    code: str = typer.Argument(..., help="股票代码"),
):
    """查询公司简况"""
    from app.services.market_service import MarketService
    import json

    svc = MarketService()
    data = svc.get_profile(code)
    console.print_json(json.dumps(data, ensure_ascii=False, indent=2))


@market_app.command("fund")
def market_fund(
    code: str = typer.Argument(..., help="股票代码"),
    days: int = typer.Option(20, "--days", "-d", help="天数"),
):
    """查询资金流向"""
    from app.services.market_service import MarketService
    import json

    svc = MarketService()
    data = svc.get_fund_flow(code, days)
    console.print_json(json.dumps(data, ensure_ascii=False, indent=2))


@market_app.command("news")
def market_news(
    code: str = typer.Argument(..., help="股票代码"),
    page: int = typer.Option(1, "--page", "-p", help="页码"),
    size: int = typer.Option(10, "--size", "-s", help="每页条数"),
):
    """查询新闻资讯"""
    from app.services.market_service import MarketService
    import json

    svc = MarketService()
    data = svc.get_news(code, page, size)
    console.print_json(json.dumps(data, ensure_ascii=False, indent=2))


@market_app.command("chip")
def market_chip(
    code: str = typer.Argument(..., help="股票代码"),
):
    """查询筹码分布"""
    from app.services.market_service import MarketService
    import json

    svc = MarketService()
    data = svc.get_chip(code)
    console.print_json(json.dumps(data, ensure_ascii=False, indent=2))


# ==================== 统计分析 ====================
@analysis_app.command("summary")
def analysis_summary(
    start: str = typer.Option("", "--start", help="开始日期 YYYY-MM-DD"),
    end: str = typer.Option("", "--end", help="结束日期 YYYY-MM-DD"),
    market: str = typer.Option("", "--market", "-m", help="市场: A/HK/US"),
):
    """交易统计摘要"""
    from app.services.analysis_service import AnalysisService

    start_date = datetime.strptime(start, "%Y-%m-%d") if start else None
    end_date = datetime.strptime(end, "%Y-%m-%d") if end else None

    svc = AnalysisService()
    s = svc.summary(start_date, end_date, market)

    if s.get("total_trades", 0) == 0:
        console.print("[yellow]没有交易记录[/yellow]")
        return

    # 核心指标面板
    win_color = "green" if s["win_rate"] >= 50 else "red"
    pnl_color = "green" if s["net_profit"] >= 0 else "red"

    console.print(
        Panel(
            f"[bold]交易概况[/bold]\n"
            f"  总交易次数: {s['total_trades']}  (买入 {s['buy_count']} / 卖出 {s['sell_count']})\n"
            f"  已平仓: {s['closed_count']}  交易股票数: {s['stocks_traded']}\n"
            f"  活跃期间: {s['active_period']}\n"
            f"\n[bold]胜率分析[/bold]\n"
            f"  胜率: [{win_color}]{s['win_rate']}%[/{win_color}]  "
            f"(盈 {s['win_count']} / 亏 {s['loss_count']} / 平 {s['even_count']})\n"
            f"  盈亏比: {s['profit_loss_ratio']}\n"
            f"\n[bold]盈亏统计[/bold]\n"
            f"  总盈利: [green]{s['total_profit']:+,.2f}[/green]  "
            f"总亏损: [red]-{s['total_loss']:,.2f}[/red]\n"
            f"  平均盈利: [green]{s['avg_profit']:+,.2f}[/green]  "
            f"平均亏损: [red]-{s['avg_loss']:,.2f}[/red]\n"
            f"  最大单笔盈利: [green]{s['max_profit']:+,.2f}[/green]  "
            f"最大单笔亏损: [red]-{s['max_loss']:,.2f}[/red]\n"
            f"\n[bold]费用 & 净利润[/bold]\n"
            f"  手续费: {s['total_commission']:,.2f}  印花税: {s['total_tax']:,.2f}\n"
            f"  净利润: [{pnl_color}]{s['net_profit']:+,.2f}[/{pnl_color}]\n"
            f"\n[bold]持仓周期[/bold]\n"
            f"  平均持仓天数: {s['avg_holding_days']}天  最长持仓: {s['max_holding_days']}天",
            title="📊 交易统计摘要",
            border_style="blue",
        )
    )


@analysis_app.command("monthly")
def analysis_monthly(
    start: str = typer.Option("", "--start", help="开始日期"),
    end: str = typer.Option("", "--end", help="结束日期"),
):
    """月度盈亏统计"""
    from app.services.analysis_service import AnalysisService

    start_date = datetime.strptime(start, "%Y-%m-%d") if start else None
    end_date = datetime.strptime(end, "%Y-%m-%d") if end else None

    svc = AnalysisService()
    df = svc.monthly_summary(start_date, end_date)

    if df.empty:
        console.print("[yellow]📭 没有交易数据[/yellow]")
        return

    table = Table(title="📅 月度盈亏", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("月份", width=10)
    table.add_column("交易次数", width=8, justify="right")
    table.add_column("盈", width=5, justify="right")
    table.add_column("亏", width=5, justify="right")
    table.add_column("胜率", width=8, justify="right")
    table.add_column("总盈亏", width=14, justify="right")
    table.add_column("平均盈亏", width=12, justify="right")

    for _, row in df.iterrows():
        color = "green" if row["total_profit"] >= 0 else "red"
        table.add_row(
            row["month"],
            str(row["trade_count"]),
            str(row["win_count"]),
            str(row["loss_count"]),
            f"{row['win_rate']:.1f}%",
            f"[{color}]{row['total_profit']:+,.2f}[/{color}]",
            f"[{color}]{row['avg_profit']:+,.2f}[/{color}]",
        )

    console.print(table)


@analysis_app.command("ranking")
def analysis_ranking():
    """按股票盈亏排名"""
    from app.services.analysis_service import AnalysisService

    svc = AnalysisService()
    df = svc.stock_pnl_ranking()

    if df.empty:
        console.print("[yellow]📭 没有交易数据[/yellow]")
        return

    table = Table(title="🏆 股票盈亏排名", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("排名", width=5, justify="center")
    table.add_column("代码", width=10)
    table.add_column("名称", width=10)
    table.add_column("交易次数", width=8, justify="right")
    table.add_column("总盈亏", width=14, justify="right")
    table.add_column("平均盈亏", width=12, justify="right")
    table.add_column("胜率", width=8, justify="right")

    for i, row in df.iterrows():
        color = "green" if row["total_profit"] >= 0 else "red"
        table.add_row(
            str(i + 1),
            row["stock_code"],
            row["stock_name"],
            str(row["trade_count"]),
            f"[{color}]{row['total_profit']:+,.2f}[/{color}]",
            f"[{color}]{row['avg_profit']:+,.2f}[/{color}]",
            f"{row['win_rate']:.1f}%",
        )

    console.print(table)


@analysis_app.command("drawdown")
def analysis_drawdown():
    """最大回撤分析"""
    from app.services.analysis_service import AnalysisService

    svc = AnalysisService()
    dd = svc.max_drawdown()

    if dd["max_drawdown"] == 0:
        console.print("[yellow]📭 无法计算回撤（无交易数据）[/yellow]")
        return

    console.print(
        Panel(
            f"最大回撤: [red]{dd['max_drawdown']:,.2f}[/red]\n"
            f"最大回撤率: [red]{dd['max_drawdown_rate']:.2f}%[/red]\n"
            f"峰值日期: {dd['peak_date']}\n"
            f"谷底日期: {dd['trough_date']}",
            title="[最大回撤分析]",
            border_style="red",
        )
    )


# ==================== 可视化图表 ====================
@chart_app.command("pnl")
def chart_pnl():
    """绘制收益曲线"""
    from app.services.analysis_service import AnalysisService
    from app.visualization.charts import ChartService

    daily = AnalysisService().daily_pnl()
    if daily.empty:
        console.print("[yellow]📭 无交易数据[/yellow]")
        return

    path = ChartService().plot_pnl_curve(daily)
    if path:
        console.print(f"[green]✅ 图表已保存: {path}[/green]")


@chart_app.command("kline")
def chart_kline(
    code: str = typer.Argument(..., help="股票代码"),
    period: str = typer.Option("day", "--period", "-p", help="K线周期"),
    count: int = typer.Option(60, "--count", "-c", help="K线数量"),
):
    """绘制K线图"""
    from app.services.market_service import MarketService
    from app.visualization.charts import ChartService

    df = MarketService().get_kline_df(code, period, count)
    if df.empty:
        console.print("[red]❌ 获取K线数据失败[/red]")
        return

    path = ChartService().plot_kline(df, title=f"{code} {period}K线")
    if path:
        console.print(f"[green]✅ 图表已保存: {path}[/green]")


@chart_app.command("portfolio")
def chart_portfolio():
    """绘制持仓分布图"""
    from app.services.portfolio_service import PortfolioService
    from app.visualization.charts import ChartService

    holdings = PortfolioService().get_portfolio_with_market_data()
    if not holdings:
        console.print("[yellow]📭 当前无持仓[/yellow]")
        return

    path = ChartService().plot_portfolio_pie(holdings)
    if path:
        console.print(f"[green]✅ 图表已保存: {path}[/green]")


@chart_app.command("winloss")
def chart_winloss():
    """绘制胜负统计图"""
    from app.services.analysis_service import AnalysisService
    from app.visualization.charts import ChartService

    s = AnalysisService().summary()
    if s.get("total_trades", 0) == 0:
        console.print("[yellow]📭 无交易数据[/yellow]")
        return

    path = ChartService().plot_win_loss_bar(s)
    if path:
        console.print(f"[green]✅ 图表已保存: {path}[/green]")


@chart_app.command("monthly")
def chart_monthly():
    """绘制月度盈亏图"""
    from app.services.analysis_service import AnalysisService
    from app.visualization.charts import ChartService

    df = AnalysisService().monthly_summary()
    if df.empty:
        console.print("[yellow]📭 无交易数据[/yellow]")
        return

    path = ChartService().plot_monthly_pnl(df)
    if path:
        console.print(f"[green]✅ 图表已保存: {path}[/green]")




# ==================== AI 预测（从 commands/ai.py 加载）====================
import app.cli as _self_module
from app.commands.ai import register_ai_commands
register_ai_commands(ai_app, _self_module)


# ==================== 回测引擎（从 commands/backtest.py 加载）====================
from app.commands.backtest import register_backtest_commands
register_backtest_commands(backtest_app, _self_module)


# ==================== 预警监控（从 commands/alert.py 加载）====================
from app.commands.alert import register_alert_commands
register_alert_commands(alert_app, _self_module)


# ==================== 智能日报（从 commands/digest.py 加载）====================
from app.commands.digest import register_digest_commands
register_digest_commands(digest_app, _self_module)


# ==================== 消息推送命令 ====================

def _notify_test_impl(channel: str):
    """通知测试内部实现"""
    from app.services.notification import NotificationManager, NotificationLevel

    mgr = NotificationManager()
    if not mgr.is_enabled:
        console.print("[yellow]⚠️ 消息推送未启用或无已配置的渠道[/yellow]")
        console.print("[dim]请在 config.yaml 的 notification.channels 中启用至少一个渠道[/dim]")
        return

    target = channel if channel else "所有已启用渠道"
    console.print(f"[cyan]📤 向 {target} 发送测试消息...[/cyan]")
    results = mgr.notify(
        title="测试消息 — Stock Trader AI",
        content="这是一条测试消息，如果你收到了说明推送配置正确！🎉",
        level=NotificationLevel.INFO,
        stock_code="sh000001", stock_name="上证指数",
        price=3200.00, change_percent=0.88,
        channel=channel if channel else None,
    )
    if not results:
        console.print("[yellow]⚠️ 没有发送结果（可能无已启用的渠道）[/yellow]")
        return
    for ch_name, success, err in results:
        if success:
            console.print(f"  [green]✅ {ch_name} — 发送成功[/green]")
        else:
            console.print(f"  [red]❌ {ch_name} — 发送失败: {err}[/red]")


def _notify_list_impl():
    """通知渠道列表内部实现"""
    from app.services.notification import NotificationManager
    mgr = NotificationManager()
    status = mgr.get_status()

    table = Table(title="📬 消息推送渠道配置", box=box.ROUNDED, show_lines=True, header_style="bold cyan")
    table.add_column("渠道", width=12)
    table.add_column("配置", width=8, justify="center")
    table.add_column("连接", width=8, justify="center")
    table.add_column("说明", width=35)

    ch_info = {
        "serverchan": ("Server酱", "免费微信推送 (5条/天) — sct.ftqq.com"),
        "pushplus": ("PushPlus", "免费微信推送 (200条/天) — pushplus.plus"),
        "dingtalk": ("钉钉", "钉钉群机器人 Webhook — 无限制"),
        "feishu": ("飞书", "飞书群机器人 Webhook — 无限制"),
        "telegram": ("Telegram", "Telegram Bot 推送 — 无限制"),
        "email": ("邮件", "SMTP 邮件推送 — 无限制"),
        "wecom": ("企业微信", "企业微信群机器人 Webhook — 无限制"),
    }
    for ch_name, ch_st in status["channels"].items():
        info = ch_info.get(ch_name, (ch_name, ""))
        enabled = "[green]✅ 已启用[/green]" if ch_st["enabled"] else "[dim]未启用[/dim]"
        connected = "[green]✅[/green]" if ch_st["connected"] else "[dim]—[/dim]"
        table.add_row(info[0], enabled, connected, info[1])
    console.print(table)

    global_st = "[green]已启用[/green]" if status["enabled"] else "[red]已禁用[/red]"
    alert_st = "[green]是[/green]" if status["on_alert"] else "[dim]否[/dim]"
    trade_st = "[green]是[/green]" if status["on_trade"] else "[dim]否[/dim]"
    console.print(f"\n全局推送: {global_st} | 预警推送: {alert_st} | 交易推送: {trade_st}")
    if mgr.enabled_channels:
        console.print(f"[green]活跃渠道: {', '.join(mgr.enabled_channels)}[/green]")
    else:
        console.print("[yellow]⚠️ 当前没有活跃的推送渠道，请在 config.yaml 中配置[/yellow]")
    console.print("\n[dim]配置方法: 编辑 config.yaml → notification.channels, 设置 enabled: true 并填 key/token/webhook[/dim]")


@notify_app.command("test")
def notify_test_cmd(
    channel: str = typer.Option("", "--channel", "-c", help="指定渠道"),
):
    """发送测试通知"""
    _notify_test_impl(channel)


@notify_app.command("list")
def notify_list_cmd():
    """查看推送渠道配置"""
    _notify_list_impl()


# ==================== 辅助函数 ====================
def _parse_time(time_str: str):
    """解析时间字符串"""
    if not time_str:
        return None
    try:
        return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            return datetime.strptime(time_str, "%Y-%m-%d")
        except ValueError:
            console.print("[red][ERROR] 时间格式错误，请使用 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS[/red]")
            raise typer.Exit(1)


# ==================== init 命令 ====================
@app.command("init")
def init():
    """初始化项目（创建数据库和目录）"""
    import os
    from app.config import get_config

    config = get_config()
    dirs = [
        config["cache"]["dir"],
        config["visualization"]["save_dir"],
        config["ai"]["model"]["save_dir"],
        os.path.dirname(config["database"]["path"]),
        os.path.join("data", "exports"),
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)

    init_db()
    console.print("[green][OK] Stock Trader AI 初始化完成![/green]")
    console.print("  数据库已创建")
    console.print("  数据目录已就绪")
    console.print("\n使用 [bold]stock-ai --help[/bold] 查看所有命令")


# ==================== 注册快捷命令（从 commands/shortcuts.py 加载）====================
from app.commands.shortcuts import register_shortcuts
register_shortcuts(app, _self_module)


if __name__ == "__main__":
    app()

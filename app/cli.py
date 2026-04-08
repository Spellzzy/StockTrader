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

app.add_typer(trade_app, name="trade")
app.add_typer(portfolio_app, name="portfolio")
app.add_typer(watchlist_app, name="watchlist")
app.add_typer(market_app, name="market")
app.add_typer(analysis_app, name="analysis")
app.add_typer(chart_app, name="chart")
app.add_typer(ai_app, name="ai")
app.add_typer(alert_app, name="alert")


# ==================== 初始化回调 ====================
@app.callback()
def main_callback():
    """初始化数据库"""
    init_db()


# ==================== 交易管理 ====================
@trade_app.command("add")
def trade_add(
    code: str = typer.Option(..., "--code", "-c", help="股票代码 (如 sh600519)"),
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
    code: str = typer.Argument(..., help="股票代码 (如 sh600519)"),
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
    codes: str = typer.Argument(..., help="股票代码(逗号分隔, 如 sh600519,hk00700)"),
):
    """查询实时行情"""
    from app.services.market_service import MarketService
    import json

    svc = MarketService()
    code_list = [c.strip() for c in codes.split(",")]
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
):
    """查询K线数据"""
    from app.services.market_service import MarketService

    svc = MarketService()
    df = svc.get_kline_df(code, period, count, adjust)

    if df.empty:
        console.print("[red]❌ 获取K线数据失败[/red]")
        return

    table = Table(title=f"📊 {code} {period}K线 (最近{count}条)", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("日期", width=12)
    table.add_column("开盘", width=10, justify="right")
    table.add_column("收盘", width=10, justify="right")
    table.add_column("最高", width=10, justify="right")
    table.add_column("最低", width=10, justify="right")
    table.add_column("涨跌幅", width=8, justify="right")
    table.add_column("成交量", width=10, justify="right")
    table.add_column("换手率", width=8, justify="right")

    for _, row in df.iterrows():
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


# ==================== AI 预测 ====================
@ai_app.command("predict")
def ai_predict(
    code: str = typer.Argument(..., help="股票代码 (如 sh600519)"),
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
    code: str = typer.Argument(..., help="股票代码 (如 sh600519)"),
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


# ==================== 顶级快捷命令（扁平化入口） ====================

# --- 交易管理 ---
@app.command("buy", help="快速买入 (缩写: b)")
def quick_buy(
    code: str = typer.Argument(..., help="股票代码 (如 sh600519)"),
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


def _do_buy(code, price, quantity, name, reason, strategy, time):
    from app.services.trade_service import TradeService
    from app.services.portfolio_service import PortfolioService

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


@app.command("sell", help="快速卖出 (缩写: s)")
def quick_sell(
    code: str = typer.Argument(..., help="股票代码 (如 sh600519)"),
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


def _do_sell(code, price, quantity, name, reason, strategy, time):
    from app.services.trade_service import TradeService
    from app.services.portfolio_service import PortfolioService

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


@app.command("trades", help="查看交易记录 (缩写: t)")
def quick_trades(
    code: str = typer.Option("", "--code", "-c", help="按股票代码过滤"),
    limit: int = typer.Option(20, "--limit", "-l", help="显示条数"),
):
    """查看交易记录"""
    trade_list(code=code, action="", market="", limit=limit)


@app.command("t", hidden=True)
def alias_t(
    code: str = typer.Option("", "--code", "-c", help="按股票代码过滤"),
    limit: int = typer.Option(20, "--limit", "-l", help="显示条数"),
):
    """trades 的缩写"""
    trade_list(code=code, action="", market="", limit=limit)


@app.command("del-trade", help="删除交易记录 (缩写: dt)")
def quick_del_trade(
    trade_id: int = typer.Argument(..., help="交易记录ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
):
    """删除交易记录"""
    trade_delete(trade_id=trade_id, yes=yes)


@app.command("dt", hidden=True)
def alias_dt(
    trade_id: int = typer.Argument(..., help="交易记录ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
):
    """del-trade 的缩写"""
    trade_delete(trade_id=trade_id, yes=yes)


# --- 持仓管理 ---
@app.command("show", help="查看当前持仓 (缩写: w)")
def quick_show():
    """查看当前持仓"""
    portfolio_show()


@app.command("w", hidden=True)
def alias_w():
    """show 的缩写 (w = watch)"""
    portfolio_show()


@app.command("rebuild", help="重建持仓 (缩写: rb)")
def quick_rebuild():
    """重建持仓"""
    portfolio_rebuild()


@app.command("rb", hidden=True)
def alias_rb():
    """rebuild 的缩写"""
    portfolio_rebuild()


# --- 收藏列表 ---
@app.command("stars", help="查看自选股列表 (缩写: ss)")
def quick_stars():
    """查看自选股列表"""
    watchlist_list()


@app.command("ss", hidden=True)
def alias_ss():
    """stars 的缩写"""
    watchlist_list()


@app.command("star", help="添加自选股 (缩写: sa)")
def quick_star(
    code: str = typer.Argument(..., help="股票代码 (如 sh600519)"),
    note: str = typer.Option("", "--note", "-n", help="关注备注"),
):
    """添加自选股"""
    watchlist_add(code=code, note=note)


@app.command("sa", hidden=True)
def alias_sa(
    code: str = typer.Argument(..., help="股票代码"),
    note: str = typer.Option("", "--note", "-n", help="关注备注"),
):
    """star 的缩写 (star-add)"""
    watchlist_add(code=code, note=note)


@app.command("unstar", help="取消收藏 (缩写: sd)")
def quick_unstar(
    code: str = typer.Argument(..., help="股票代码"),
):
    """取消收藏"""
    watchlist_remove(code=code)


@app.command("sd", hidden=True)
def alias_sd(
    code: str = typer.Argument(..., help="股票代码"),
):
    """unstar 的缩写 (star-delete)"""
    watchlist_remove(code=code)


# --- 行情查询 ---
@app.command("search", help="搜索股票 (缩写: sc)")
def quick_search(keyword: str = typer.Argument(..., help="搜索关键词")):
    """搜索股票"""
    market_search(keyword=keyword)


@app.command("sc", hidden=True)
def alias_sc(keyword: str = typer.Argument(..., help="搜索关键词")):
    """search 的缩写"""
    market_search(keyword=keyword)


@app.command("quote", help="查询实时行情 (缩写: q)")
def quick_quote(codes: str = typer.Argument(..., help="股票代码(逗号分隔)")):
    """查询实时行情"""
    market_quote(codes=codes)


@app.command("q", hidden=True)
def alias_q(codes: str = typer.Argument(..., help="股票代码(逗号分隔)")):
    """quote 的缩写"""
    market_quote(codes=codes)


@app.command("kline", help="查询K线数据 (缩写: k)")
def quick_kline(
    code: str = typer.Argument(..., help="股票代码"),
    period: str = typer.Option("day", "--period", "-p", help="周期"),
    count: int = typer.Option(20, "--count", "-c", help="数量"),
    adjust: str = typer.Option("qfq", "--adjust", "-a", help="复权"),
):
    """查询K线数据"""
    market_kline(code=code, period=period, count=count, adjust=adjust)


@app.command("k", hidden=True)
def alias_k(
    code: str = typer.Argument(..., help="股票代码"),
    period: str = typer.Option("day", "--period", "-p", help="周期"),
    count: int = typer.Option(20, "--count", "-c", help="数量"),
    adjust: str = typer.Option("qfq", "--adjust", "-a", help="复权"),
):
    """kline 的缩写"""
    market_kline(code=code, period=period, count=count, adjust=adjust)


@app.command("finance", help="查询财务数据 (缩写: f)")
def quick_finance(
    code: str = typer.Argument(..., help="股票代码"),
    report_type: str = typer.Option("summary", "--type", "-t", help="报表类型"),
):
    """查询财务数据"""
    market_finance(code=code, report_type=report_type)


@app.command("f", hidden=True)
def alias_f(
    code: str = typer.Argument(..., help="股票代码"),
    report_type: str = typer.Option("summary", "--type", "-t", help="报表类型"),
):
    """finance 的缩写"""
    market_finance(code=code, report_type=report_type)


@app.command("profile", help="查询公司简况 (缩写: pf)")
def quick_profile(code: str = typer.Argument(..., help="股票代码")):
    """查询公司简况"""
    market_profile(code=code)


@app.command("pf", hidden=True)
def alias_pf(code: str = typer.Argument(..., help="股票代码")):
    """profile 的缩写"""
    market_profile(code=code)


@app.command("fund", help="查询资金流向 (缩写: fd)")
def quick_fund(
    code: str = typer.Argument(..., help="股票代码"),
    days: int = typer.Option(20, "--days", "-d", help="天数"),
):
    """查询资金流向"""
    market_fund(code=code, days=days)


@app.command("fd", hidden=True)
def alias_fd(
    code: str = typer.Argument(..., help="股票代码"),
    days: int = typer.Option(20, "--days", "-d", help="天数"),
):
    """fund 的缩写"""
    market_fund(code=code, days=days)


@app.command("news", help="查询新闻资讯 (缩写: n)")
def quick_news(
    code: str = typer.Argument(..., help="股票代码"),
    page: int = typer.Option(1, "--page", "-p", help="页码"),
    size: int = typer.Option(10, "--size", "-s", help="每页条数"),
):
    """查询新闻资讯"""
    market_news(code=code, page=page, size=size)


@app.command("n", hidden=True)
def alias_n(
    code: str = typer.Argument(..., help="股票代码"),
    page: int = typer.Option(1, "--page", "-p", help="页码"),
    size: int = typer.Option(10, "--size", "-s", help="每页条数"),
):
    """news 的缩写"""
    market_news(code=code, page=page, size=size)


@app.command("chip")
def quick_chip(code: str = typer.Argument(..., help="股票代码")):
    """查询筹码分布"""
    market_chip(code=code)


# --- 统计分析 ---
@app.command("summary", help="交易统计摘要 (缩写: sm)")
def quick_summary(
    start: str = typer.Option("", "--start", help="开始日期"),
    end: str = typer.Option("", "--end", help="结束日期"),
    market: str = typer.Option("", "--market", "-m", help="市场"),
):
    """交易统计摘要"""
    analysis_summary(start=start, end=end, market=market)


@app.command("sm", hidden=True)
def alias_sm(
    start: str = typer.Option("", "--start", help="开始日期"),
    end: str = typer.Option("", "--end", help="结束日期"),
    market: str = typer.Option("", "--market", "-m", help="市场"),
):
    """summary 的缩写"""
    analysis_summary(start=start, end=end, market=market)


@app.command("monthly", help="月度盈亏统计 (缩写: mo)")
def quick_monthly(
    start: str = typer.Option("", "--start", help="开始日期"),
    end: str = typer.Option("", "--end", help="结束日期"),
):
    """月度盈亏统计"""
    analysis_monthly(start=start, end=end)


@app.command("mo", hidden=True)
def alias_mo(
    start: str = typer.Option("", "--start", help="开始日期"),
    end: str = typer.Option("", "--end", help="结束日期"),
):
    """monthly 的缩写"""
    analysis_monthly(start=start, end=end)


@app.command("ranking", help="股票盈亏排名 (缩写: rk)")
def quick_ranking():
    """股票盈亏排名"""
    analysis_ranking()


@app.command("rk", hidden=True)
def alias_rk():
    """ranking 的缩写"""
    analysis_ranking()


@app.command("drawdown", help="最大回撤分析 (缩写: dd)")
def quick_drawdown():
    """最大回撤分析"""
    analysis_drawdown()


@app.command("dd", hidden=True)
def alias_dd():
    """drawdown 的缩写"""
    analysis_drawdown()


# --- 可视化图表 ---
@app.command("chart-pnl", help="绘制收益曲线 (缩写: c-pnl)")
def quick_chart_pnl():
    """绘制收益曲线"""
    chart_pnl()


@app.command("c-pnl", hidden=True)
def alias_c_pnl():
    """chart-pnl 的缩写"""
    chart_pnl()


@app.command("chart-kline", help="绘制K线图 (缩写: c-k)")
def quick_chart_kline(
    code: str = typer.Argument(..., help="股票代码"),
    period: str = typer.Option("day", "--period", "-p", help="K线周期"),
    count: int = typer.Option(60, "--count", "-c", help="K线数量"),
):
    """绘制K线图"""
    chart_kline(code=code, period=period, count=count)


@app.command("c-k", hidden=True)
def alias_c_k(
    code: str = typer.Argument(..., help="股票代码"),
    period: str = typer.Option("day", "--period", "-p", help="K线周期"),
    count: int = typer.Option(60, "--count", "-c", help="K线数量"),
):
    """chart-kline 的缩写"""
    chart_kline(code=code, period=period, count=count)


@app.command("chart-portfolio", help="绘制持仓分布图 (缩写: c-pf)")
def quick_chart_portfolio():
    """绘制持仓分布图"""
    chart_portfolio()


@app.command("c-pf", hidden=True)
def alias_c_pf():
    """chart-portfolio 的缩写"""
    chart_portfolio()


@app.command("chart-winloss", help="绘制胜负统计图 (缩写: c-wl)")
def quick_chart_winloss():
    """绘制胜负统计图"""
    chart_winloss()


@app.command("c-wl", hidden=True)
def alias_c_wl():
    """chart-winloss 的缩写"""
    chart_winloss()


@app.command("chart-monthly", help="绘制月度盈亏图 (缩写: c-mo)")
def quick_chart_monthly():
    """绘制月度盈亏图"""
    chart_monthly()


@app.command("c-mo", hidden=True)
def alias_c_mo():
    """chart-monthly 的缩写"""
    chart_monthly()


# --- AI 预测 ---
@app.command("predict", help="AI 预测股票走势 (缩写: p)")
def quick_predict(
    code: str = typer.Argument(..., help="股票代码 (如 sh600519)"),
    dl: bool = typer.Option(False, "--dl", help="同时使用深度学习模型"),
    llm: bool = typer.Option(False, "--llm", help="追加 LLM 分析点评"),
):
    """AI 预测"""
    ai_predict(code=code, dl=dl, llm=llm)


@app.command("p", hidden=True)
def alias_p(
    code: str = typer.Argument(..., help="股票代码"),
    dl: bool = typer.Option(False, "--dl", help="使用 DL 模型"),
    llm: bool = typer.Option(False, "--llm", help="追加 LLM 分析点评"),
):
    """predict 的缩写"""
    ai_predict(code=code, dl=dl, llm=llm)


@app.command("analyze", help="LLM 深度分析 (缩写: a)")
def quick_analyze(
    code: str = typer.Argument(..., help="股票代码 (如 sh600519)"),
    dl: bool = typer.Option(False, "--dl", help="同时使用深度学习模型"),
):
    """LLM 深度分析"""
    ai_analyze(code=code, dl=dl)


@app.command("a", hidden=True)
def alias_a(
    code: str = typer.Argument(..., help="股票代码"),
    dl: bool = typer.Option(False, "--dl", help="使用 DL 模型"),
):
    """analyze 的缩写"""
    ai_analyze(code=code, dl=dl)


@app.command("scan", help="扫描自选股 AI 信号")
def quick_scan(
    dl: bool = typer.Option(False, "--dl", help="同时使用深度学习模型"),
    llm: bool = typer.Option(False, "--llm", help="对前5名追加 LLM 分析"),
):
    """扫描自选股信号排名"""
    ai_scan(dl=dl, llm=llm)


@app.command("train-ai", help="训练 AI 预测模型")
def quick_train_ai(
    code: str = typer.Argument(..., help="股票代码"),
    dl: bool = typer.Option(False, "--dl", help="同时训练 DL 模型"),
):
    """训练预测模型"""
    ai_train(code=code, dl=dl)


@app.command("test-llm", help="测试 LLM 连接")
def quick_test_llm():
    """测试 LLM 连接是否正常"""
    from app.ai.predictor_service import PredictorService

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


# ==================== 预警监控子命令组 ====================
@alert_app.command("add")
def alert_add_cmd(
    code: str = typer.Argument(..., help="股票代码 (如 sh600519)"),
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


# ==================== 实时看盘模式 ====================


def _fmt_delta(val: float, suffix: str = "", precision: int = 2) -> str:
    """格式化差异值：正数绿色↑  负数红色↓  零灰色"""
    if abs(val) < 1e-6:
        return f"[dim]—{suffix}[/dim]"
    fmt = f"{val:+.{precision}f}{suffix}"
    if val > 0:
        return f"[green]{fmt} ↑[/green]"
    else:
        return f"[red]{fmt} ↓[/red]"


def _fmt_vol_delta(cur: float, prev: float) -> str:
    """格式化成交量增量"""
    delta = cur - prev
    if abs(delta) < 1:
        return "[dim]—[/dim]"
    if delta > 0:
        d_str = f"{delta / 10000:.1f}万" if delta > 10000 else str(int(delta))
        return f"[green]+{d_str} ↑[/green]"
    else:
        d_str = f"{abs(delta) / 10000:.1f}万" if abs(delta) > 10000 else str(int(abs(delta)))
        return f"[red]-{d_str} ↓[/red]"


def _speed_label(price_delta: float, seconds: int) -> str:
    """价格变动速度标签"""
    if abs(price_delta) < 0.001:
        return ""
    speed = abs(price_delta) / (seconds / 60) if seconds > 0 else 0
    if speed >= 1.0:
        tag = "⚡快速" if price_delta > 0 else "⚡急跌"
        return f" [{('green' if price_delta > 0 else 'red')}]{tag}[/{('green' if price_delta > 0 else 'red')}]"
    elif speed >= 0.3:
        tag = "🔥活跃"
        return f" [yellow]{tag}[/yellow]"
    return ""


def _do_watch(codes_str: str, interval: int, alert_only: bool):
    """看盘模式内部实现（含轮次间差异对比）"""
    from app.services.alert_service import AlertService
    from app.services.watchlist_service import WatchlistService
    from app.services.market_service import MarketService

    # 解析股票代码
    codes = []
    if codes_str:
        codes = [c.strip() for c in codes_str.split(",") if c.strip()]
    else:
        watched = WatchlistService().list_watched()
        codes = [s.code for s in watched]

    if not codes:
        console.print("[yellow]请指定股票代码或先添加自选股 (stock-ai star <代码>)[/yellow]")
        return

    svc = AlertService()
    market = MarketService()
    round_count = 0
    prev_quotes: dict = {}  # 上一轮行情数据
    first_quotes: dict = {}  # 首轮行情数据 (用于累计变动)

    console.print(f"[cyan]👀 实时看盘模式 — 监控 {len(codes)} 只股票 (每{interval}秒刷新, Ctrl+C 退出)[/cyan]\n")

    try:
        import time as time_mod

        while True:
            round_count += 1
            now_str = datetime.now().strftime("%H:%M:%S")
            has_prev = bool(prev_quotes)

            try:
                # 获取行情
                quotes_data = market.get_quote(*codes)

                # 首轮记录基准数据
                if not first_quotes:
                    first_quotes = {
                        code: {
                            "price": quotes_data.get(code, {}).get("price", 0),
                            "volume": quotes_data.get(code, {}).get("volume", 0),
                            "change_percent": quotes_data.get(code, {}).get("change_percent", 0),
                        }
                        for code in codes
                        if quotes_data.get(code)
                    }

                if not alert_only:
                    # ====== 主行情表 ======
                    table = Table(
                        title=f"👀 实时行情 [{now_str}] (第{round_count}轮)",
                        box=box.ROUNDED,
                        header_style="bold cyan",
                    )
                    table.add_column("代码", width=10)
                    table.add_column("名称", width=8)
                    table.add_column("现价", width=9, justify="right")
                    table.add_column("涨跌幅", width=9, justify="right")
                    table.add_column("涨跌额", width=9, justify="right")
                    table.add_column("最高", width=9, justify="right")
                    table.add_column("最低", width=9, justify="right")
                    table.add_column("成交量", width=10, justify="right")
                    table.add_column("换手率", width=8, justify="right")

                    for code in codes:
                        q = quotes_data.get(code, {})
                        if not q:
                            continue
                        chg = q.get("change_percent", 0)
                        color = "green" if chg >= 0 else "red"
                        vol = q.get("volume", 0)
                        vol_str = f"{vol / 10000:.1f}万" if vol > 10000 else str(int(vol)) if vol else "-"

                        table.add_row(
                            code,
                            q.get("name", ""),
                            f"{q.get('price', 0):.2f}",
                            f"[{color}]{chg:+.2f}%[/{color}]",
                            f"[{color}]{q.get('change', 0):+.2f}[/{color}]",
                            f"{q.get('high', 0):.2f}",
                            f"{q.get('low', 0):.2f}",
                            vol_str,
                            f"{q.get('turnover_rate', 0):.2f}%",
                        )

                    console.print(table)

                    # ====== 差异对比表 (第2轮起显示) ======
                    if has_prev:
                        diff_table = Table(
                            title=f"📊 变动追踪 (对比上轮 Δ{interval}s)",
                            box=box.SIMPLE_HEAVY,
                            header_style="bold yellow",
                            show_lines=True,
                        )
                        diff_table.add_column("代码", width=10)
                        diff_table.add_column("名称", width=8)
                        diff_table.add_column("价格变动", width=12, justify="right")
                        diff_table.add_column("涨跌幅Δ", width=10, justify="right")
                        diff_table.add_column("成交量增量", width=12, justify="right")
                        diff_table.add_column("累计变动", width=12, justify="right")
                        diff_table.add_column("动向", width=10, justify="center")

                        for code in codes:
                            q = quotes_data.get(code, {})
                            pq = prev_quotes.get(code, {})
                            fq = first_quotes.get(code, {})
                            if not q or not pq:
                                continue

                            cur_price = q.get("price", 0)
                            prev_price = pq.get("price", 0)
                            price_delta = cur_price - prev_price

                            cur_chg = q.get("change_percent", 0)
                            prev_chg = pq.get("change_percent", 0)
                            chg_delta = cur_chg - prev_chg

                            cur_vol = q.get("volume", 0)
                            prev_vol = pq.get("volume", 0)

                            # 累计变动（相对首轮）
                            first_price = fq.get("price", cur_price)
                            cum_delta = cur_price - first_price
                            cum_pct = (cum_delta / first_price * 100) if first_price else 0

                            # 动向判定
                            speed = _speed_label(price_delta, interval)
                            if abs(price_delta) < 0.001:
                                direction = "[dim]横盘[/dim]"
                            elif price_delta > 0:
                                direction = "[green]📈 上行[/green]"
                            else:
                                direction = "[red]📉 下行[/red]"
                            direction += speed

                            diff_table.add_row(
                                code,
                                q.get("name", ""),
                                _fmt_delta(price_delta, "元"),
                                _fmt_delta(chg_delta, "%"),
                                _fmt_vol_delta(cur_vol, prev_vol),
                                _fmt_delta(cum_delta, f"({cum_pct:+.2f}%)", precision=2),
                                direction,
                            )

                        console.print(diff_table)

                        # ====== 异动提醒 ======
                        movers = []
                        for code in codes:
                            q = quotes_data.get(code, {})
                            pq = prev_quotes.get(code, {})
                            if not q or not pq:
                                continue
                            name = q.get("name", code)
                            cur_price = q.get("price", 0)
                            prev_price = pq.get("price", 0)
                            price_delta = cur_price - prev_price
                            pct_move = (price_delta / prev_price * 100) if prev_price else 0

                            cur_vol = q.get("volume", 0)
                            prev_vol = pq.get("volume", 0)
                            vol_delta = cur_vol - prev_vol

                            # 价格快速异动（单轮涨跌超0.5%）
                            if abs(pct_move) >= 0.5:
                                tag = "🚀 快速拉升" if pct_move > 0 else "💥 快速下跌"
                                color = "green" if pct_move > 0 else "red"
                                movers.append(
                                    f"  [{color}]{tag}[/{color}] "
                                    f"[bold]{name}({code})[/bold] "
                                    f"单轮变动 {pct_move:+.2f}% ({price_delta:+.2f}元)"
                                )

                            # 放量异动（成交量增量超前一轮总量的20%）
                            if prev_vol > 0 and vol_delta > 0:
                                vol_ratio = vol_delta / prev_vol
                                if vol_ratio >= 0.2:
                                    vol_d_str = f"{vol_delta / 10000:.1f}万" if vol_delta > 10000 else str(int(vol_delta))
                                    movers.append(
                                        f"  [yellow]📦 放量[/yellow] "
                                        f"[bold]{name}({code})[/bold] "
                                        f"成交增量 +{vol_d_str} (较上轮+{vol_ratio * 100:.0f}%)"
                                    )

                        if movers:
                            console.print(Panel(
                                "\n".join(movers),
                                title="⚡ 异动捕捉",
                                border_style="yellow",
                                expand=False,
                            ))

                # 检测预警
                triggered = svc.check_alerts(verbose=True)
                if triggered:
                    console.print(f"\n[bold red]🚨 {len(triggered)} 条预警触发！[/bold red]")
                    for t in triggered:
                        alert = t["alert"]
                        console.print(
                            f"  [red]🚨[/red] [bold]{alert.stock_code}[/bold] "
                            f"{alert.stock_name or ''} — {t['message']}"
                        )
                    console.print()

                if not alert_only:
                    if round_count == 1:
                        console.print("[dim]💡 首轮采集基准数据，下轮起显示变动追踪[/dim]")
                    console.print(f"[dim]下次刷新: {interval}秒后 (Ctrl+C 退出)[/dim]\n")

                # 保存当前轮数据作为下一轮的对比基准
                prev_quotes = {
                    code: {
                        "price": quotes_data.get(code, {}).get("price", 0),
                        "volume": quotes_data.get(code, {}).get("volume", 0),
                        "change_percent": quotes_data.get(code, {}).get("change_percent", 0),
                        "name": quotes_data.get(code, {}).get("name", ""),
                    }
                    for code in codes
                    if quotes_data.get(code)
                }

            except Exception as e:
                console.print(f"[yellow]⚠️ 数据获取异常: {e}[/yellow]")

            time_mod.sleep(interval)

    except KeyboardInterrupt:
        console.print(f"\n[cyan]👋 已退出看盘模式 (共刷新 {round_count} 轮)[/cyan]")


# ==================== 预警监控快捷命令 ====================

@app.command("alert-add", help="添加预警规则 (缩写: al-a)")
def quick_alert_add(
    code: str = typer.Argument(..., help="股票代码 (如 sh600519)"),
    condition: str = typer.Argument(..., help="条件类型 (price_above/rsi_below/macd_cross 等)"),
    threshold: float = typer.Option(None, "--threshold", "-t", help="阈值"),
    repeat: bool = typer.Option(False, "--repeat", "-r", help="可重复触发"),
    note: str = typer.Option("", "--note", "-n", help="备注"),
):
    """添加预警规则"""
    alert_add_cmd(code=code, condition=condition, threshold=threshold, repeat=repeat, note=note)


@app.command("al-a", hidden=True)
def alias_al_a(
    code: str = typer.Argument(..., help="股票代码"),
    condition: str = typer.Argument(..., help="条件类型"),
    threshold: float = typer.Option(None, "--threshold", "-t", help="阈值"),
    repeat: bool = typer.Option(False, "--repeat", "-r", help="可重复触发"),
    note: str = typer.Option("", "--note", "-n", help="备注"),
):
    """alert-add 的缩写"""
    alert_add_cmd(code=code, condition=condition, threshold=threshold, repeat=repeat, note=note)


@app.command("alert-list", help="查看预警规则列表 (缩写: al-l)")
def quick_alert_list(
    code: str = typer.Option("", "--code", "-c", help="按股票代码过滤"),
    active: bool = typer.Option(False, "--active", "-a", help="仅显示启用的"),
):
    """查看预警规则"""
    alert_list_cmd(code=code, active=active)


@app.command("al-l", hidden=True)
def alias_al_l(
    code: str = typer.Option("", "--code", "-c", help="按股票代码过滤"),
    active: bool = typer.Option(False, "--active", "-a", help="仅显示启用的"),
):
    """alert-list 的缩写"""
    alert_list_cmd(code=code, active=active)


@app.command("alert-del", help="删除预警规则 (缩写: al-d)")
def quick_alert_del(
    alert_id: int = typer.Argument(..., help="预警规则 ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
):
    """删除预警规则"""
    alert_delete_cmd(alert_id=alert_id, yes=yes)


@app.command("al-d", hidden=True)
def alias_al_d(
    alert_id: int = typer.Argument(..., help="预警规则 ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
):
    """alert-del 的缩写"""
    alert_delete_cmd(alert_id=alert_id, yes=yes)


@app.command("alert-toggle", help="启用/暂停预警 (缩写: al-t)")
def quick_alert_toggle(
    alert_id: int = typer.Argument(..., help="预警规则 ID"),
):
    """启用/暂停预警"""
    alert_toggle_cmd(alert_id=alert_id)


@app.command("al-t", hidden=True)
def alias_al_t(
    alert_id: int = typer.Argument(..., help="预警规则 ID"),
):
    """alert-toggle 的缩写"""
    alert_toggle_cmd(alert_id=alert_id)


@app.command("alert-reset", help="重置预警 (缩写: al-r)")
def quick_alert_reset(
    alert_id: int = typer.Argument(..., help="预警规则 ID"),
):
    """重置预警"""
    alert_reset_cmd(alert_id=alert_id)


@app.command("al-r", hidden=True)
def alias_al_r(
    alert_id: int = typer.Argument(..., help="预警规则 ID"),
):
    """alert-reset 的缩写"""
    alert_reset_cmd(alert_id=alert_id)


@app.command("alert-check", help="立即检测预警 (缩写: al-c)")
def quick_alert_check():
    """立即检测一次所有预警"""
    alert_check_cmd()


@app.command("al-c", hidden=True)
def alias_al_c():
    """alert-check 的缩写"""
    alert_check_cmd()


@app.command("alert-history", help="预警触发历史 (缩写: al-h)")
def quick_alert_history(
    code: str = typer.Option("", "--code", "-c", help="按股票代码过滤"),
    alert_id: int = typer.Option(0, "--id", help="按预警规则 ID 过滤"),
    limit: int = typer.Option(20, "--limit", "-l", help="显示条数"),
):
    """预警触发历史"""
    alert_history_cmd(code=code, alert_id=alert_id, limit=limit)


@app.command("al-h", hidden=True)
def alias_al_h(
    code: str = typer.Option("", "--code", "-c", help="按股票代码过滤"),
    alert_id: int = typer.Option(0, "--id", help="按预警规则 ID 过滤"),
    limit: int = typer.Option(20, "--limit", "-l", help="显示条数"),
):
    """alert-history 的缩写"""
    alert_history_cmd(code=code, alert_id=alert_id, limit=limit)


@app.command("alert-types", help="查看预警条件类型 (缩写: al-tp)")
def quick_alert_types():
    """查看支持的预警条件类型"""
    alert_types_cmd()


@app.command("al-tp", hidden=True)
def alias_al_tp():
    """alert-types 的缩写"""
    alert_types_cmd()


@app.command("watch", help="实时看盘模式 (缩写: wa)")
def quick_watch(
    codes: str = typer.Option("", "--codes", "-c", help="股票代码(逗号分隔, 默认自选股)"),
    interval: int = typer.Option(30, "--interval", "-i", help="刷新间隔(秒)"),
    alert_only: bool = typer.Option(False, "--alert-only", help="仅监控预警，不显示行情"),
):
    """实时看盘模式（自动刷新行情 + 预警检测）"""
    from app.services.market_service import MarketService as _MS
    _do_watch(codes, interval, alert_only)


@app.command("wa", hidden=True)
def alias_wa(
    codes: str = typer.Option("", "--codes", "-c", help="股票代码(逗号分隔)"),
    interval: int = typer.Option(30, "--interval", "-i", help="刷新间隔(秒)"),
    alert_only: bool = typer.Option(False, "--alert-only", help="仅监控预警"),
):
    """watch 的缩写"""
    from app.services.market_service import MarketService as _MS
    _do_watch(codes, interval, alert_only)


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


# ==================== 快捷命令 ====================
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


if __name__ == "__main__":
    app()

"""HTML 可视化报告

把终端里的散点信息聚合成一个可以双击打开、也可以发给别人的单文件 HTML：

    stock-ai report            # 生成 data/reports/report_YYYYMMDD.html
    stock-ai report --with-bt  # 额外跑一遍多策略回测对比
    stock-ai report --no-chart # 只要表格，不出图（快）

设计约束：
    - 不新增依赖：图表复用 matplotlib，转成 base64 内嵌，HTML 自带样式
    - 任何一块数据缺失（没交易 / 没持仓 / 没模型）都跳过该区块，不报错
"""

from __future__ import annotations

import base64
import html
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = "./data/reports"

_CSS = """
:root { --bg:#0f1216; --card:#171b21; --line:#242a33; --fg:#e6e9ef; --dim:#8b95a5;
        --up:#e5484d; --down:#30a46c; --accent:#5b9dff; }
* { box-sizing: border-box; }
body { margin:0; padding:24px; background:var(--bg); color:var(--fg);
       font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif; }
h1 { font-size:22px; margin:0 0 4px; }
h2 { font-size:16px; margin:28px 0 12px; padding-left:8px; border-left:3px solid var(--accent); }
.meta { color:var(--dim); font-size:12px; margin-bottom:20px; }
.cards { display:flex; flex-wrap:wrap; gap:12px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:8px;
        padding:12px 16px; min-width:140px; flex:1; }
.card .k { color:var(--dim); font-size:12px; }
.card .v { font-size:20px; font-weight:600; margin-top:4px; }
.grid { display:flex; flex-wrap:wrap; gap:16px; }
figure { margin:0; background:var(--card); border:1px solid var(--line);
         border-radius:8px; padding:12px; flex:1 1 460px; }
figure img { width:100%; height:auto; display:block; }
figcaption { color:var(--dim); font-size:12px; margin-top:8px; }
table { width:100%; border-collapse:collapse; background:var(--card);
        border:1px solid var(--line); border-radius:8px; overflow:hidden; font-size:13px; }
th,td { padding:8px 10px; text-align:right; border-bottom:1px solid var(--line); }
th:first-child,td:first-child { text-align:left; }
th { color:var(--dim); font-weight:500; background:#14181e; }
tbody tr:last-child td { border-bottom:none; }
.up { color:var(--up); } .down { color:var(--down); } .dim { color:var(--dim); }
.empty { color:var(--dim); font-size:13px; padding:12px; background:var(--card);
         border:1px dashed var(--line); border-radius:8px; }
"""


def _fmt(value, digits: int = 2, default: str = "-") -> str:
    """数字格式化，None/NaN/inf 显示占位符"""
    if value is None:
        return default
    try:
        if value != value:  # NaN
            return default
        value = float(value)
        if value in (float("inf"), float("-inf")):
            return default
        return f"{value:,.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _cls(value) -> str:
    """涨跌配色"""
    try:
        return "up" if float(value) > 0 else ("down" if float(value) < 0 else "dim")
    except (TypeError, ValueError):
        return "dim"


def _img_base64(path: Optional[str]) -> Optional[str]:
    """图片转 base64，失败返回 None（不中断整份报告）"""
    if not path:
        return None
    try:
        data = Path(path).read_bytes()
    except OSError as e:
        logger.warning(f"图表读取失败: {path} ({e})")
        return None
    return base64.b64encode(data).decode("ascii")


class HTMLReport:
    """可视化报告生成器"""

    def __init__(self, output_dir: str = DEFAULT_OUTPUT_DIR):
        self.output_dir = Path(output_dir)

    # ==================== 区块 ====================

    def _section_stats(self, summary: dict, total: dict, drawdown: dict) -> str:
        cards = [
            ("总盈亏", _fmt(total.get("total_profit")), _cls(total.get("total_profit"))),
            ("浮动盈亏", _fmt(total.get("total_unrealized_profit")), _cls(total.get("total_unrealized_profit"))),
            ("已实现盈亏", _fmt(total.get("total_realized_profit")), _cls(total.get("total_realized_profit"))),
            ("持仓市值", _fmt(total.get("total_market_value")), ""),
            ("胜率", f"{_fmt(summary.get('win_rate'), 1)}%", ""),
            ("盈亏比", _fmt(summary.get("profit_loss_ratio")), ""),
            ("交易笔数", str(summary.get("total_trades", 0)), ""),
            ("最大回撤", f"{_fmt(drawdown.get('max_drawdown_rate'), 1)}%", "down"),
        ]
        items = "".join(
            f'<div class="card"><div class="k">{html.escape(k)}</div>'
            f'<div class="v {c}">{html.escape(v)}</div></div>'
            for k, v, c in cards
        )
        return f"<h2>账户概览</h2><div class='cards'>{items}</div>"

    def _section_holdings(self, holdings: list) -> str:
        if not holdings:
            return "<h2>当前持仓</h2><div class='empty'>当前无持仓</div>"

        rows = "".join(
            "<tr>"
            f"<td>{html.escape(str(h.get('stock_code', '')))}</td>"
            f"<td>{html.escape(str(h.get('stock_name', '') or ''))}</td>"
            f"<td>{_fmt(h.get('quantity'), 0)}</td>"
            f"<td>{_fmt(h.get('avg_cost'))}</td>"
            f"<td>{_fmt(h.get('current_price'))}</td>"
            f"<td>{_fmt(h.get('market_value'))}</td>"
            f"<td class='{_cls(h.get('unrealized_profit'))}'>{_fmt(h.get('unrealized_profit'))}</td>"
            f"<td class='{_cls(h.get('unrealized_profit_rate'))}'>"
            f"{_fmt(h.get('unrealized_profit_rate'))}%</td>"
            "</tr>"
            for h in holdings
        )
        return (
            "<h2>当前持仓</h2><table><thead><tr>"
            "<th>代码</th><th>名称</th><th>持仓</th><th>成本</th><th>现价</th>"
            "<th>市值</th><th>盈亏</th><th>盈亏%</th>"
            f"</tr></thead><tbody>{rows}</tbody></table>"
        )

    def _section_ranking(self, ranking) -> str:
        if ranking is None or getattr(ranking, "empty", True):
            return ""

        rows = ""
        for _, row in ranking.head(20).iterrows():
            rows += (
                "<tr>"
                f"<td>{html.escape(str(row.get('stock_code', '')))}</td>"
                f"<td>{html.escape(str(row.get('stock_name', '') or ''))}</td>"
                f"<td>{_fmt(row.get('trades'), 0)}</td>"
                f"<td class='{_cls(row.get('profit'))}'>{_fmt(row.get('profit'))}</td>"
                f"<td class='{_cls(row.get('win_rate'))}'>{_fmt(row.get('win_rate'), 1)}%</td>"
                "</tr>"
            )
        return (
            "<h2>个股盈亏排名</h2><table><thead><tr>"
            "<th>代码</th><th>名称</th><th>笔数</th><th>盈亏</th><th>胜率</th>"
            f"</tr></thead><tbody>{rows}</tbody></table>"
        )

    def _section_recent_trades(self, trades_df) -> str:
        if trades_df is None or getattr(trades_df, "empty", True):
            return ""

        rows = ""
        for _, row in trades_df.tail(20).iloc[::-1].iterrows():
            action = "买入" if row.get("action") == "buy" else "卖出"
            rows += (
                "<tr>"
                f"<td>{html.escape(str(row.get('trade_time', ''))[:16])}</td>"
                f"<td>{html.escape(str(row.get('stock_code', '')))}</td>"
                f"<td>{html.escape(str(row.get('stock_name', '') or ''))}</td>"
                f"<td>{action}</td>"
                f"<td>{_fmt(row.get('price'))}</td>"
                f"<td>{_fmt(row.get('quantity'), 0)}</td>"
                f"<td class='{_cls(row.get('profit'))}'>{_fmt(row.get('profit'))}</td>"
                f"<td>{html.escape(str(row.get('strategy', '') or ''))}</td>"
                "</tr>"
            )
        return (
            "<h2>最近交易（20 笔）</h2><table><thead><tr>"
            "<th>时间</th><th>代码</th><th>名称</th><th>方向</th><th>价格</th>"
            "<th>数量</th><th>盈亏</th><th>策略</th>"
            f"</tr></thead><tbody>{rows}</tbody></table>"
        )

    def _section_charts(self, charts: list) -> str:
        if not charts:
            return ""

        figures = "".join(
            f'<figure><img src="data:image/png;base64,{data}" alt="{html.escape(title)}">'
            f"<figcaption>{html.escape(title)}</figcaption></figure>"
            for title, data in charts
        )
        return f"<h2>图表</h2><div class='grid'>{figures}</div>"

    def _section_backtest(self, results: list) -> str:
        if not results:
            return ""

        rows = ""
        for r in results:
            rows += (
                "<tr>"
                f"<td>{html.escape(str(r.strategy_name))}</td>"
                f"<td class='{_cls(r.total_return)}'>{_fmt(r.total_return)}%</td>"
                f"<td class='{_cls(r.excess_return)}'>{_fmt(r.excess_return)}%</td>"
                f"<td>{_fmt(r.max_drawdown)}%</td>"
                f"<td>{_fmt(r.sharpe_ratio)}</td>"
                f"<td>{_fmt(r.win_rate, 1)}%</td>"
                f"<td>{r.total_trades}</td>"
                "</tr>"
            )
        return (
            "<h2>策略回测对比（次日开盘成交口径）</h2><table><thead><tr>"
            "<th>策略</th><th>总收益</th><th>超额</th><th>最大回撤</th><th>夏普</th>"
            "<th>胜率</th><th>交易</th>"
            f"</tr></thead><tbody>{rows}</tbody></table>"
        )

    # ==================== 组装 ====================

    def build(
        self,
        with_backtest: bool = False,
        backtest_code: str = "",
        days: int = 180,
        with_chart: bool = True,
        filename: str | None = None,
    ) -> str:
        """生成报告，返回 HTML 文件路径

        Args:
            filename: 自定义文件名（定时任务用它跟手动报告区分开）
        """
        from app.services.analysis_service import AnalysisService
        from app.services.portfolio_service import PortfolioService

        analysis = AnalysisService()
        portfolio = PortfolioService()

        summary = self._safe(analysis.summary) or {}
        total = self._safe(portfolio.get_total_summary) or {}
        holdings = total.get("holdings") or self._safe(portfolio.get_portfolio_with_market_data) or []
        drawdown = self._safe(analysis.max_drawdown) or {}

        parts = [
            self._section_stats(summary, total, drawdown),
            self._section_holdings(holdings),
        ]

        if with_chart:
            charts = self._build_charts(analysis, holdings)
            parts.append(self._section_charts(charts))

        parts.append(self._section_ranking(self._safe(analysis.stock_pnl_ranking)))
        parts.append(self._section_recent_trades(self._safe(analysis.get_trades_df)))

        if with_backtest and backtest_code:
            parts.append(self._section_backtest(self._run_backtests(backtest_code, days)))

        body = "".join(p for p in parts if p)
        now = datetime.now()
        doc = (
            "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>Stock Trader AI 报告 {now:%Y-%m-%d}</title>"
            f"<style>{_CSS}</style></head><body>"
            f"<h1>Stock Trader AI 投资报告</h1>"
            f"<div class='meta'>生成时间 {now:%Y-%m-%d %H:%M:%S} · "
            f"共 {summary.get('total_trades', 0)} 笔交易 · "
            f"{len(holdings)} 只持仓</div>"
            f"{body}</body></html>"
        )

        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / (filename or f"report_{now:%Y%m%d}.html")
        path.write_text(doc, encoding="utf-8")
        logger.info(f"HTML 报告已生成: {path}")
        return str(path)

    # ==================== 内部 ====================

    @staticmethod
    def _safe(func, *args, **kwargs):
        """任一块数据出错都不影响整份报告"""
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.warning(f"报告区块生成失败，已跳过: {e}")
            return None

    def _build_charts(self, analysis, holdings: list) -> list:
        from app.visualization.charts import ChartService

        cs = ChartService()
        charts = []

        # 先取数据，空数据直接跳过（画图函数会对空 DataFrame 抛 KeyError）
        candidates = [
            ("累计收益曲线", lambda: analysis.daily_pnl(), cs.plot_pnl_curve),
            ("月度盈亏", lambda: analysis.monthly_summary(), cs.plot_monthly_pnl),
            ("胜负统计", lambda: analysis.summary(), cs.plot_win_loss_bar),
            ("持仓分布", lambda: holdings, cs.plot_portfolio_pie),
        ]
        for title, get_data, draw in candidates:
            data = self._safe(get_data)
            if data is None or (hasattr(data, "empty") and data.empty):
                continue
            path = self._safe(draw, data)
            encoded = _img_base64(path)
            if encoded:
                charts.append((title, encoded))
        return charts

    @staticmethod
    def _run_backtests(code: str, days: int) -> list:
        from app.services.backtest_service import BacktestService
        from app.services.strategy import list_strategy_names

        service = BacktestService()
        results = []
        for name in list_strategy_names():
            try:
                results.append(service.run(code, strategy=name, days=days))
            except Exception as e:
                logger.warning(f"回测 {name} 失败: {e}")
        return BacktestService.rank_results(results)

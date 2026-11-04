"""HTML 可视化报告"""

import pandas as pd

from app.visualization.report import HTMLReport, _cls, _fmt


def _holdings():
    return [
        {
            "stock_code": "sz002555",
            "stock_name": "三七互娱",
            "quantity": 4600,
            "avg_cost": 22.8,
            "current_price": 14.47,
            "market_value": 66562.0,
            "unrealized_profit": -38318.0,
            "unrealized_profit_rate": -36.54,
        }
    ]


def _trades_df():
    return pd.DataFrame(
        {
            "trade_time": [pd.Timestamp("2026-01-05"), pd.Timestamp("2026-02-10")],
            "stock_code": ["sz002555", "sh600879"],
            "stock_name": ["三七互娱", "航天电子"],
            "action": ["buy", "sell"],
            "price": [22.8, 13.5],
            "quantity": [4600, 2000],
            "profit": [None, 1200.0],
            "strategy": ["macd_cross", ""],
        }
    )


def _patch(monkeypatch, tmp_path, trades=_trades_df(), holdings=_holdings()):
    monkeypatch.setattr(
        "app.services.portfolio_service.PortfolioService.get_total_summary",
        lambda self: {
            "holding_count": len(holdings),
            "total_cost": 104880.0,
            "total_market_value": 66562.0,
            "total_unrealized_profit": -38318.0,
            "total_realized_profit": 1200.0,
            "total_profit": -37118.0,
            "holdings": holdings,
        },
    )
    monkeypatch.setattr(
        "app.services.portfolio_service.PortfolioService.get_portfolio_with_market_data",
        lambda self: holdings,
    )
    monkeypatch.setattr(
        "app.services.analysis_service.AnalysisService.summary",
        lambda self, *a, **kw: {
            "total_trades": len(trades),
            "win_rate": 50.0,
            "profit_loss_ratio": 1.8,
        },
    )
    monkeypatch.setattr(
        "app.services.analysis_service.AnalysisService.max_drawdown",
        lambda self, *a, **kw: {"max_drawdown_rate": 36.5},
    )
    monkeypatch.setattr(
        "app.services.analysis_service.AnalysisService.get_trades_df",
        lambda self, *a, **kw: trades,
    )
    monkeypatch.setattr(
        "app.services.analysis_service.AnalysisService.stock_pnl_ranking",
        lambda self, *a, **kw: pd.DataFrame(
            {"stock_code": ["sz002555"], "stock_name": ["三七互娱"],
             "trades": [1], "profit": [-38318.0], "win_rate": [0.0]}
        ),
    )
    return HTMLReport(output_dir=str(tmp_path))


def test_report_is_single_file_html(monkeypatch, tmp_path):
    report = _patch(monkeypatch, tmp_path)
    path = report.build(with_chart=False)

    content = open(path, encoding="utf-8").read()
    assert content.startswith("<!DOCTYPE html>")
    assert "Stock Trader AI 投资报告" in content
    assert "账户概览" in content
    assert "当前持仓" in content
    assert "sz002555" in content


def test_custom_filename(monkeypatch, tmp_path):
    report = _patch(monkeypatch, tmp_path)
    path = report.build(with_chart=False, filename="daily_20261104.html")

    assert path.endswith("daily_20261104.html")
    assert (tmp_path / "daily_20261104.html").exists()


def test_no_chart_mode_has_no_image(monkeypatch, tmp_path):
    report = _patch(monkeypatch, tmp_path)
    path = report.build(with_chart=False)

    assert "base64" not in open(path, encoding="utf-8").read()


def test_empty_data_still_generates_report(monkeypatch, tmp_path):
    empty = pd.DataFrame()
    report = _patch(monkeypatch, tmp_path, trades=empty, holdings=[])
    path = report.build(with_chart=False)

    content = open(path, encoding="utf-8").read()
    assert "当前无持仓" in content


def test_failing_section_does_not_break_report(monkeypatch, tmp_path):
    """某一块数据抛异常时只跳过该块，整份报告仍要出"""
    report = _patch(monkeypatch, tmp_path)

    def boom(*a, **kw):
        raise RuntimeError("行情挂了")

    monkeypatch.setattr(
        "app.services.analysis_service.AnalysisService.stock_pnl_ranking", boom
    )
    path = report.build(with_chart=False)

    assert "账户概览" in open(path, encoding="utf-8").read()


def test_backtest_section_uses_strategy_names(monkeypatch):
    """回归：list_strategies() 返回 dict，这里必须用 list_strategy_names()"""
    import app.services.backtest_service as bt_module
    from app.services.backtest_service import BacktestResult
    from app.visualization.report import HTMLReport

    def fake_run(self, code, strategy, days):
        result = BacktestResult(code=code, strategy_name=strategy)
        result.total_return = 1.0
        return result

    monkeypatch.setattr(bt_module.BacktestService, "run", fake_run)

    results = HTMLReport._run_backtests("sz000001", 180)

    assert len(results) == 7
    assert all(isinstance(r.strategy_name, str) for r in results)


def test_format_helpers():
    assert _fmt(None) == "-"
    assert _fmt(1234.5678) == "1,234.57"
    assert _cls(5) == "up"
    assert _cls(-5) == "down"
    assert _cls(None) == "dim"

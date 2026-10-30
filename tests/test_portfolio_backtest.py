"""多标的组合回测聚合"""

import pandas as pd
import pytest

from app.services.backtest_service import BacktestResult, BacktestService


def _make_result(code: str, equity_values) -> BacktestResult:
    result = BacktestResult(code=code, initial_capital=50_000.0)
    result.equity_curve = pd.DataFrame(
        {
            "date": pd.bdate_range("2024-01-01", periods=len(equity_values)),
            "equity": equity_values,
        }
    )
    result.final_capital = float(equity_values[-1])
    return result


@pytest.fixture
def patched_run(monkeypatch):
    """打桩单标的回测，避免真实行情请求"""
    calls = []

    def fake_run(self, code, **kwargs):
        calls.append(code)
        equity = {
            "sh600519": [50_000, 52_000, 54_000],
            "sz000001": [50_000, 49_000, 51_000],
        }[code]
        return _make_result(code, equity)

    monkeypatch.setattr(BacktestService, "run", fake_run)
    return calls


def test_equity_is_sum_of_members(patched_run):
    portfolio = BacktestService().run_portfolio(
        ["sh600519", "sz000001"], initial_capital=100_000.0
    )

    curve = portfolio["equity_curve"]
    assert curve["equity"].tolist() == pytest.approx([100_000, 101_000, 105_000])


def test_capital_is_split_evenly(patched_run, monkeypatch):
    seen = {}

    def fake_run(self, code, **kwargs):
        seen[code] = kwargs["initial_capital"]
        return _make_result(code, [50_000, 51_000])

    monkeypatch.setattr(BacktestService, "run", fake_run)
    BacktestService().run_portfolio(["sh600519", "sz000001"], initial_capital=100_000.0)

    assert seen == {"sh600519": 50_000.0, "sz000001": 50_000.0}


def test_total_return_and_drawdown(patched_run):
    portfolio = BacktestService().run_portfolio(
        ["sh600519", "sz000001"], initial_capital=100_000.0
    )

    assert portfolio["total_return"] == pytest.approx(5.0)
    assert portfolio["max_drawdown"] >= 0
    assert portfolio["final_capital"] == pytest.approx(105_000.0)


def test_codes_are_deduplicated(patched_run):
    BacktestService().run_portfolio(["sh600519", "sh600519", "sz000001"])
    assert patched_run == ["sh600519", "sz000001"]


def test_empty_codes_returns_empty():
    assert BacktestService().run_portfolio([]) == {}


def test_curve_metrics_on_flat_equity():
    metrics = BacktestService.curve_metrics([100.0, 100.0, 100.0], 100.0)
    assert metrics["max_drawdown"] == 0.0
    assert metrics["sharpe_ratio"] == 0.0

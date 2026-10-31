"""多策略排序：0 成交的策略不能靠 0% 收益排到前面"""

from app.services.backtest_service import BacktestResult, BacktestService


def _result(name: str, total_return: float, trades: int = 5) -> BacktestResult:
    r = BacktestResult(code="sz000001", strategy_name=name)
    r.total_return = total_return
    r.total_trades = trades
    return r


def test_zero_trade_results_go_last():
    results = [
        _result("no_signal", 0.0, trades=0),
        _result("bad", -21.03),
        _result("good", -12.25),
    ]

    ranked = BacktestService.rank_results(results)
    assert [r.strategy_name for r in ranked] == ["good", "bad", "no_signal"]


def test_sorts_by_return_among_traded():
    results = [_result("a", 5.0), _result("b", 20.0), _result("c", -3.0)]

    ranked = BacktestService.rank_results(results)
    assert [r.strategy_name for r in ranked] == ["b", "a", "c"]


def test_all_zero_trade_keeps_stable_order():
    results = [_result("x", 0.0, trades=0), _result("y", 0.0, trades=0)]

    ranked = BacktestService.rank_results(results)
    assert [r.strategy_name for r in ranked] == ["x", "y"]

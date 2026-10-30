"""回测撮合与绩效指标

注意：本文件固化的是「改造前」的行为，其中
test_buy_fills_at_signal_bar_close 记录的是存在前视偏差的撮合方式，
P1 改为次日开盘成交后该断言会被替换。
"""

import pandas as pd
import pytest

from app.services.backtest_service import BacktestResult, BacktestService


def _df(signals, closes, start="2024-01-01"):
    return pd.DataFrame(
        {
            "date": pd.bdate_range(start=start, periods=len(closes)),
            "close": closes,
            "signal": signals,
        }
    )


def _run(df, **kwargs) -> BacktestResult:
    result = BacktestResult(commission_rate=0.0003, tax_rate=0.001, **kwargs)
    BacktestService()._simulate_trades(df, result, 1.0)
    return result


def test_buy_fills_at_signal_bar_close():
    """当前行为：买入信号当日即按收盘价成交"""
    df = _df([0, 1, 0, -1, 0], [10.5, 10.5, 11.0, 12.0, 12.0])
    result = _run(df)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_date == "2024-01-02"
    assert trade.entry_price == pytest.approx(10.5)
    assert trade.exit_date == "2024-01-04"
    assert trade.exit_price == pytest.approx(12.0)
    assert trade.exit_reason == "signal"


def test_quantity_rounded_to_lot_of_100():
    df = _df([0, 1, 0, -1, 0], [10.5, 10.5, 11.0, 12.0, 12.0])
    result = _run(df)
    assert result.trades[0].quantity % 100 == 0
    assert result.trades[0].quantity == 9500


def test_commission_has_five_yuan_floor():
    """小额成交按最低 5 元收取佣金"""
    df = _df([0, 1, 0, 0, 0], [10.5, 10.5, 11.0, 11.0, 11.0])
    result = _run(df, initial_capital=2000.0)

    assert result.trades[0].quantity == 100
    buy_commission = max(100 * 10.5 * 0.0003, 5.0)
    assert buy_commission == 5.0
    assert result.total_commission > 5.0  # 含末尾强制平仓的卖出佣金


def test_stamp_tax_charged_on_sell_only():
    df = _df([0, 1, 0, -1, 0], [10.5, 10.5, 11.0, 12.0, 12.0])
    result = _run(df)

    sell_revenue = 9500 * 12.0
    assert result.total_tax == pytest.approx(sell_revenue * 0.001)


def test_metrics_are_computed():
    df = _df([0, 1, 0, -1, 0], [10.5, 10.5, 11.0, 12.0, 12.0])
    result = _run(df)
    BacktestService()._calculate_metrics(df, result)

    assert result.total_trades == 1
    assert result.win_rate == 100.0
    assert result.total_return == pytest.approx(14.07, abs=0.01)
    assert result.benchmark_return == pytest.approx((12.0 - 10.5) / 10.5 * 100, abs=0.01)
    assert result.excess_return == pytest.approx(
        result.total_return - result.benchmark_return, abs=0.01
    )


def test_equity_curve_covers_every_bar():
    df = _df([0, 1, 0, -1, 0], [10.5, 10.5, 11.0, 12.0, 12.0])
    result = _run(df)
    assert result.equity_curve is not None
    assert len(result.equity_curve) == len(df)


def test_open_position_is_closed_at_end():
    df = _df([0, 1, 0, 0, 0], [10.5, 10.5, 11.0, 11.0, 11.0])
    result = _run(df)

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == "end"
    assert result.trades[0].exit_price == pytest.approx(11.0)

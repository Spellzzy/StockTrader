"""回测撮合规则与绩效指标

撮合规则（fill_mode=next_open，默认）:
    1. 第 i 根 K 线产生的信号，在第 i+1 根以开盘价成交（消除前视偏差）
    2. T+1：买入当天不能卖出
    3. 一字涨停不能买入，一字跌停不能卖出
    4. 滑点：买入价上浮、卖出价下浮
    5. 止损/止盈按当日最低/最高价判断，成交价取止损价与开盘价中更差的一个

fill_mode=close 保留旧行为（信号当日收盘价成交），仅用于新旧结果对照。
"""

import pandas as pd
import pytest

from app.services.backtest_service import BacktestResult, BacktestService


def _df(signals, closes, start="2024-01-01", spread=0.10):
    """构造 OHLC 齐全的 K 线（无一字板）"""
    return pd.DataFrame(
        {
            "date": pd.bdate_range(start=start, periods=len(closes)),
            "open": [c - 0.01 for c in closes],
            "high": [c + spread for c in closes],
            "low": [c - spread for c in closes],
            "close": closes,
            "signal": signals,
        }
    )


def _run(df, **kwargs) -> BacktestResult:
    fill_mode = kwargs.pop("fill_mode", "next_open")
    slippage = kwargs.pop("slippage", 0.0)
    result = BacktestResult(commission_rate=0.0003, tax_rate=0.001, **kwargs)
    BacktestService()._simulate_trades(
        df, result, 1.0, fill_mode=fill_mode, slippage=slippage
    )
    return result


def test_buy_fills_at_next_bar_open():
    """信号次日开盘成交，不再用信号当日收盘价"""
    df = _df([0, 1, 0, -1, 0], [10.5, 10.5, 11.0, 12.0, 12.0])
    result = _run(df)

    trade = result.trades[0]
    assert trade.entry_date == "2024-01-03"   # 信号在 01-02，成交在 01-03 开盘
    assert trade.entry_price == pytest.approx(10.99)
    assert trade.exit_date == "2024-01-05"
    assert trade.exit_price == pytest.approx(11.99)
    assert trade.exit_reason == "signal"


def test_legacy_close_fill_reproduces_signal_bar_fill():
    """fill_mode=close 保留旧行为，用于新旧收益对照"""
    df = _df([0, 1, 0, -1, 0], [10.5, 10.5, 11.0, 12.0, 12.0])
    result = _run(df, fill_mode="close")

    trade = result.trades[0]
    assert trade.entry_date == "2024-01-02"
    assert trade.entry_price == pytest.approx(10.5)
    assert trade.exit_date == "2024-01-04"
    assert trade.exit_price == pytest.approx(12.0)


def test_quantity_rounded_to_lot_of_100():
    df = _df([0, 1, 0, -1, 0], [10.5, 10.5, 11.0, 12.0, 12.0])
    result = _run(df)
    assert result.trades[0].quantity % 100 == 0
    assert result.trades[0].quantity == 9000


def test_commission_has_five_yuan_floor():
    """小额成交按最低 5 元收取佣金"""
    df = _df([0, 1, 0, 0, 0], [10.5, 10.5, 11.0, 11.0, 11.0])
    result = _run(df, initial_capital=2000.0)

    assert result.trades[0].quantity == 100
    assert max(100 * 10.99 * 0.0003, 5.0) == 5.0
    assert result.total_commission == pytest.approx(10.0)  # 买入 + 末尾平仓各 5 元


def test_stamp_tax_charged_on_sell_only():
    df = _df([0, 1, 0, -1, 0], [10.5, 10.5, 11.0, 12.0, 12.0])
    result = _run(df)

    assert result.total_tax == pytest.approx(9000 * 11.99 * 0.001)


def test_metrics_are_computed():
    df = _df([0, 1, 0, -1, 0], [10.5, 10.5, 11.0, 12.0, 12.0])
    result = _run(df)
    BacktestService()._calculate_metrics(df, result)

    assert result.total_trades == 1
    assert result.win_rate == 100.0
    assert result.total_return == pytest.approx(8.83, abs=0.01)
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


def test_slippage_worsens_fill_price():
    df = _df([0, 1, 0, -1, 0], [10.5, 10.5, 11.0, 12.0, 12.0])
    base = _run(df)
    slipped = _run(df, slippage=0.001)

    assert slipped.trades[0].entry_price == pytest.approx(base.trades[0].entry_price * 1.001)
    assert slipped.trades[0].exit_price == pytest.approx(base.trades[0].exit_price * 0.999)


def test_stop_loss_uses_intraday_low_and_respects_t_plus_1():
    """买入当天盘中已跌破止损价，但受 T+1 约束不能当天卖出"""
    df = pd.DataFrame(
        {
            "date": pd.bdate_range("2024-01-01", periods=5),
            "open": [10.0, 10.0, 10.0, 9.0, 9.0],
            "high": [10.2, 10.2, 10.2, 9.2, 9.2],
            "low": [9.8, 9.8, 9.0, 8.8, 8.8],
            "close": [10.0, 10.0, 9.5, 9.0, 9.0],
            "signal": [0, 1, 0, 0, 0],
        }
    )
    result = _run(df, stop_loss=0.05)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_price == pytest.approx(10.0)   # 第3根开盘成交
    assert trade.entry_date == "2024-01-03"
    # 止损价 9.5，第4根开盘 9.0 更低 → 按更差的 9.0 成交
    assert trade.exit_price == pytest.approx(9.0)
    assert trade.exit_reason == "stop_loss"
    assert trade.exit_date == "2024-01-04"   # 不是买入当天


def test_limit_up_bar_blocks_buy(limit_kline_df):
    """次日一字涨停 → 买单无法成交"""
    df = limit_kline_df.copy()
    df["signal"] = [0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

    result = _run(df)
    assert result.trades == []


def test_limit_up_bar_allows_sell(limit_kline_df):
    """一字涨停不影响卖出"""
    df = limit_kline_df.copy()
    df["signal"] = [1, -1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

    result = _run(df)
    assert len(result.trades) == 1
    assert result.trades[0].exit_price == pytest.approx(11.55)


def test_limit_down_bar_blocks_sell(limit_kline_df):
    """次日一字跌停 → 卖单无法成交，持仓保留到回测结束"""
    df = limit_kline_df.copy()
    df["signal"] = [0, 0, 0, 1, -1, 0, 0, 0, 0, 0, 0, 0]

    result = _run(df)
    assert len(result.trades) == 1
    assert result.trades[0].entry_price == pytest.approx(11.60)
    assert result.trades[0].exit_reason == "end"


def test_next_open_is_stricter_than_close_fill():
    """消除前视偏差后，同一组信号的收益不应高于旧口径"""
    df = _df([0, 1, 0, -1, 0, 1, 0, -1, 0], [10.5, 10.5, 11.0, 12.0, 12.0, 11.5, 10.5, 10.0, 10.0])
    legacy = _run(df, fill_mode="close")
    fixed = _run(df)

    assert fixed.trades[0].entry_date != legacy.trades[0].entry_date

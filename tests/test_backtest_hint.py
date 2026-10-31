"""回测无成交时的原因提示"""

import pandas as pd

from app.services.backtest_service import BacktestService


def _patch_market(monkeypatch, closes):
    """用固定 K 线打桩行情，避免真实请求"""
    df = pd.DataFrame(
        {
            "date": pd.bdate_range("2024-01-01", periods=len(closes)),
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": [1_000_000] * len(closes),
        }
    )
    monkeypatch.setattr(
        "app.services.market_service.MarketService.get_kline_df", lambda *a, **kw: df
    )
    return df


def test_hint_when_capital_cannot_afford_one_lot(monkeypatch):
    """资金买不起 1 手时，要明确提示，而不是静默 0 收益"""
    _patch_market(monkeypatch, [1400.0 + i for i in range(60)])

    result = BacktestService().run("sh600519", initial_capital=100_000.0)

    assert result.total_trades == 0
    assert "资金不足" in result.hint
    assert "1 手需" in result.hint


def test_hint_says_no_signal_when_capital_is_enough(monkeypatch):
    """资金够但没有信号时，提示应该说明是没信号"""
    # 缓慢单边上行：RSI 一直在高位，不会触发超卖买入
    rising = [10.0 + i * 0.02 for i in range(60)]
    _patch_market(monkeypatch, rising)

    result = BacktestService().run("sz000001", strategy="rsi", initial_capital=100_000.0)

    assert result.total_trades == 0
    assert result.hint == "该区间内策略未产生任何买卖信号"


def test_no_hint_when_there_are_trades(monkeypatch):
    closes = [10.0] * 20 + [10 + i * 0.5 for i in range(20)] + [20 - i * 0.5 for i in range(20)]
    _patch_market(monkeypatch, closes)

    result = BacktestService().run("sz000001", strategy="macd_cross", initial_capital=100_000.0)

    if result.total_trades > 0:
        assert result.hint == ""

"""量比：与 watch CLI 同一套源字段与盘中回退。"""

from datetime import datetime

import pandas as pd
import pytest

from app.domain.volume_ratio import (
    prior_avg_volume,
    resolve_volume_ratio,
    trading_elapsed_minutes,
)


def _at(hour, minute, second=0):
    return datetime(2026, 11, 6, hour, minute, second)


def test_trading_elapsed_minutes_matches_watch_sessions():
    assert trading_elapsed_minutes(_at(9, 0)) == 0
    assert trading_elapsed_minutes(_at(9, 29)) == 0
    assert trading_elapsed_minutes(_at(9, 30)) == 0
    assert trading_elapsed_minutes(_at(10, 30)) == 60
    assert trading_elapsed_minutes(_at(11, 30)) == 120
    assert trading_elapsed_minutes(_at(12, 15)) == 120  # 午休按上午已满 120
    assert trading_elapsed_minutes(_at(13, 0)) == 120
    assert trading_elapsed_minutes(_at(14, 0)) == 180
    assert trading_elapsed_minutes(_at(15, 0)) == 240
    assert trading_elapsed_minutes(_at(15, 30)) == 240


def test_prior_avg_volume_drops_today_and_caps_at_five_days():
    # 7 根：丢掉最后一根（当天）后只取最近 5 日，不把更早的 1 算进去
    df = pd.DataFrame({"volume": [1, 2, 3, 4, 5, 6, 999]})
    assert prior_avg_volume(df) == pytest.approx(4.0)  # (2+3+4+5+6) / 5

    short = pd.DataFrame({"volume": [10, 20, 30, 40, 50, 999]})
    assert prior_avg_volume(short) == pytest.approx(30.0)

    assert prior_avg_volume(pd.DataFrame({"volume": [100]})) is None
    assert prior_avg_volume(pd.DataFrame({"volume": []})) is None
    assert prior_avg_volume(None) is None


def test_resolve_prefers_volume_ratio_then_vol_ratio():
    now = _at(10, 30)
    kline = pd.DataFrame({"volume": [100, 100, 100, 100, 100, 1]})
    # 若误走回退：均量 100、已过 60 分钟、现量 50 → 2.0，不能盖过源字段
    assert resolve_volume_ratio(
        {"volume_ratio": 2.5, "vol_ratio": 9.9, "volume": 50},
        kline_df=kline, now=now,
    ) == pytest.approx(2.5)
    assert resolve_volume_ratio(
        {"volume_ratio": 0, "vol_ratio": 1.25, "volume": 50},
        kline_df=kline, now=now,
    ) == pytest.approx(1.25)
    assert resolve_volume_ratio(
        {"vol_ratio": "1.80", "volume": 50},
        kline_df=kline, now=now,
    ) == pytest.approx(1.8)


def test_resolve_falls_back_to_intraday_ratio():
    now = _at(10, 30)  # 60 / 240
    kline = pd.DataFrame({"volume": [100, 100, 100, 100, 100, 9999]})
    # expected = 100 * (60/240) = 25；量比 = 50/25 = 2
    ratio = resolve_volume_ratio({"volume": 50}, kline_df=kline, now=now)
    assert ratio == pytest.approx(2.0)

    # 预计算的 5 日均量（watch 缓存）与 K 线等价
    assert resolve_volume_ratio(
        {"volume": 50}, avg_volume=100, now=now,
    ) == pytest.approx(2.0)


def test_resolve_returns_none_when_unusable():
    kline = pd.DataFrame({"volume": [100, 100, 100, 100, 100, 9999]})
    assert resolve_volume_ratio({"volume": 50}, kline_df=kline, now=_at(9, 0)) is None
    assert resolve_volume_ratio({"volume": 50}, kline_df=kline, now=_at(9, 30)) is None
    assert resolve_volume_ratio({}, kline_df=kline, now=_at(10, 30)) is None
    assert resolve_volume_ratio({"volume": 0}, kline_df=kline, now=_at(10, 30)) is None
    assert resolve_volume_ratio(
        {"volume": 50}, kline_df=pd.DataFrame({"volume": [0, 0, 0, 0, 0, 0]}), now=_at(10, 30),
    ) is None
    assert resolve_volume_ratio({"volume_ratio": 0, "vol_ratio": 0, "volume": 50}) is None

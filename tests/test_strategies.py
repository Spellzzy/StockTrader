"""回测策略：信号合法性 + 防未来函数"""

import pytest

from app.ai.feature_engine import FeatureEngine
from app.services.strategy import BUILTIN_STRATEGIES, get_strategy, list_strategies

ALL_STRATEGIES = sorted(BUILTIN_STRATEGIES)


def _signals(name: str, df):
    return get_strategy(name).generate_signals(df)


@pytest.mark.parametrize("name", ALL_STRATEGIES)
def test_signal_is_ternary(name, kline_df):
    out = _signals(name, FeatureEngine().build_features(kline_df))
    assert "signal" in out.columns
    assert set(out["signal"].unique()) <= {-1, 0, 1}


@pytest.mark.parametrize("name", ALL_STRATEGIES)
def test_signals_do_not_use_future_data(name, kline_df):
    """截断末尾 K 线后，重合区间的信号必须逐根一致（策略只能用到历史数据）"""
    engine = FeatureEngine()
    full = _signals(name, engine.build_features(kline_df))

    for k in (1, 5, 20):
        partial = _signals(name, engine.build_features(kline_df.iloc[:-k]))
        assert len(partial) > 0
        assert partial["signal"].tolist() == full["signal"].iloc[: len(partial)].tolist()


def test_unknown_strategy_raises():
    with pytest.raises(ValueError):
        get_strategy("no_such_strategy")


def test_list_strategies_covers_registry():
    assert {s["name"] for s in list_strategies()} == set(BUILTIN_STRATEGIES)

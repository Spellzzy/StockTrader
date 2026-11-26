"""回测策略：信号合法性 + 防未来函数"""

import pandas as pd
import pytest

from app.ai.feature_engine import FeatureEngine
from app.services.strategy import (
    BUILTIN_STRATEGIES,
    get_custom_param_grids,
    get_strategy,
    list_strategies,
    list_strategy_names,
)
from app.services.strategy_lab import generate_param_grid

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


def test_boll_accepts_zone_params():
    strategy = get_strategy("boll", low_zone=20, high_zone=80)
    assert strategy.low_zone == 20
    assert strategy.high_zone == 80
    assert "P20" in strategy.description and "P80" in strategy.description


def test_boll_zone_params_change_signals():
    df = pd.DataFrame({"boll_pct": [0.10, 0.25, 0.85, 0.70]})
    default = get_strategy("boll", low_zone=20, high_zone=80).generate_signals(df)
    strict = get_strategy("boll", low_zone=60, high_zone=80).generate_signals(df)
    assert default["signal"].tolist() == [0, 1, 0, -1]
    assert strict["signal"].tolist() == [0, 0, 1, -1]


def test_boll_default_keeps_legacy_cross_logic(kline_df):
    """默认 0/100 必须等价于旧版「穿越上下轨」信号"""
    featured = FeatureEngine().build_features(kline_df)
    legacy = featured.copy()
    legacy["signal"] = 0
    legacy.loc[
        (featured["close"] > featured["boll_lower"])
        & (featured["close"].shift(1) <= featured["boll_lower"].shift(1)),
        "signal",
    ] = 1
    legacy.loc[
        (featured["close"] < featured["boll_upper"])
        & (featured["close"].shift(1) >= featured["boll_upper"].shift(1)),
        "signal",
    ] = -1
    assert get_strategy("boll").generate_signals(featured)["signal"].tolist() == (
        legacy["signal"].tolist()
    )


CUSTOM_SOURCE = '''
from app.services.strategy import BaseStrategy

PARAM_GRIDS = {"my_custom": {"threshold": [5, 10]}}

class MyCustom(BaseStrategy):
    name = "my_custom"
    description = "收盘价超过阈值买入"

    def __init__(self, threshold=5):
        self.threshold = threshold
        self.description = f"close > {threshold}"

    def generate_signals(self, df):
        df = df.copy()
        df["signal"] = 0
        df.loc[df["close"] > self.threshold, "signal"] = 1
        return df
'''


def test_custom_strategy_is_autodiscovered(tmp_path, isolate_config):
    (tmp_path / "my_custom.py").write_text(CUSTOM_SOURCE, encoding="utf-8")
    isolate_config["strategies"] = {"enabled": True, "dir": str(tmp_path)}

    assert "my_custom" in list_strategy_names()
    strategy = get_strategy("my_custom", threshold=8)
    out = strategy.generate_signals(pd.DataFrame({"close": [7, 9, 6, 10]}))
    assert out["signal"].tolist() == [0, 1, 0, 1]
    assert any(s["name"] == "my_custom" for s in list_strategies())


def test_custom_param_grid_is_used_by_optimize(tmp_path, isolate_config):
    (tmp_path / "my_custom.py").write_text(CUSTOM_SOURCE, encoding="utf-8")
    isolate_config["strategies"] = {"enabled": True, "dir": str(tmp_path)}

    assert get_custom_param_grids()["my_custom"] == {"threshold": [5, 10]}
    assert generate_param_grid("my_custom") == [{"threshold": 5}, {"threshold": 10}]


def test_custom_strategy_disabled_or_broken_is_skipped(tmp_path, isolate_config):
    (tmp_path / "broken.py").write_text("raise RuntimeError('boom')\n", encoding="utf-8")
    (tmp_path / "clash.py").write_text(
        CUSTOM_SOURCE.replace('"my_custom"', '"rsi"'), encoding="utf-8"
    )
    isolate_config["strategies"] = {"enabled": True, "dir": str(tmp_path)}

    # 坏文件和内置重名策略都被跳过，内置 rsi 不受影响
    assert get_strategy("rsi").__class__.__name__ == "RSIOversoldStrategy"
    assert "my_custom" not in list_strategy_names()

    isolate_config["strategies"]["enabled"] = False
    from app.services.strategy import reset_custom_strategies

    reset_custom_strategies()
    assert "my_custom" not in list_strategy_names()

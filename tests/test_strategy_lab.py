"""策略实验室：信号质量 / 参数网格 / 滚动窗口（全部离线纯逻辑）"""

import pandas as pd

from app.services.strategy import list_strategy_names
from app.services.strategy_lab import (
    generate_param_grid,
    pair_signals,
    signal_quality_metrics,
    walk_forward_eval,
    walk_forward_folds,
)


def _df(closes, signals, start="2024-01-01"):
    return pd.DataFrame({
        "date": pd.bdate_range(start, periods=len(closes)),
        "close": closes,
        "signal": signals,
    })


def test_perfect_direction_signals():
    """每 5 根涨一次，每次都给买入信号 → 命中率 100%"""
    n = 60
    closes = [10.0]
    signals = [0]
    for i in range(1, n):
        closes.append(closes[-1] + (0.2 if (i - 1) % 5 < 4 else 0.2))
        signals.append(1 if i % 5 == 0 else 0)

    metrics = signal_quality_metrics(_df(closes, signals), horizon=5)

    assert metrics["total_signals"] > 0
    assert metrics["hit_rate"] == 100.0
    assert metrics["buy_signals"] == metrics["total_signals"]
    assert metrics["decay"] == 0.0


def test_mixed_signals_hit_rate_between_zero_and_hundred():
    closes = [10.0 + i * 0.1 for i in range(80)]
    signals = [1 if i % 7 == 0 else (-1 if i % 11 == 0 else 0) for i in range(80)]

    metrics = signal_quality_metrics(_df(closes, signals), horizon=5)

    assert 0 < metrics["hit_rate"] <= 100
    assert metrics["buy_signals"] > 0 and metrics["sell_signals"] > 0
    assert metrics["in_sample_signals"] + metrics["out_of_sample_signals"] == metrics["total_signals"]


def test_empty_or_no_signal_data():
    assert signal_quality_metrics(pd.DataFrame())["total_signals"] == 0
    flat = _df([10.0] * 30, [0] * 30)
    assert signal_quality_metrics(flat)["total_signals"] == 0


def test_pair_signals():
    closes = [10, 11, 12, 9, 8, 13, 14]
    signals = [1, 0, -1, 1, 0, -1, 0]
    trades = pair_signals(_df(closes, signals))

    assert len(trades) == 2
    assert trades[0]["pnl_pct"] > 0
    assert trades[1]["pnl_pct"] > 0
    assert all(t["holding_days"] >= 1 for t in trades)


def test_param_grid_filters_invalid_combinations():
    grid = generate_param_grid("ma_cross")

    assert grid
    assert all(p["short"] < p["long"] for p in grid)
    assert all(p["short"] in (5, 10, 20) and p["long"] in (10, 20, 60) for p in grid)


def test_param_grid_respects_max_combos_and_unknown_strategy():
    assert len(generate_param_grid("rsi", max_combos=3)) == 3
    assert generate_param_grid("macd_cross") == [{}]


def test_walk_forward_folds_are_expanding_and_have_gap():
    folds = walk_forward_folds(100, n_splits=3, gap=5)

    assert len(folds) == 3
    for f in folds:
        assert f["train"][0] == 0
        assert f["test"][0] >= f["train"][1] + 5
        assert f["test"][0] < f["test"][1] <= 100
    assert folds[-1]["test"][1] == 100


def test_walk_forward_eval_flags_insufficient_samples():
    """信号极稀疏时不能报出一个看似可信的衰减值"""
    closes = [10.0 + 0.01 * i for i in range(120)]
    signals = [1 if i == 10 else (-1 if i == 40 else 0) for i in range(120)]

    result = walk_forward_eval(_df(closes, signals), "macd_cross", n_splits=3)

    assert result["total_folds"] == 3
    assert result["reliable_folds"] == 0
    assert result["mean_test_hit_rate"] is None
    assert result["decay"] is None
    assert "样本外信号不足" in result["conclusion"]


def test_list_strategy_names_returns_strings():
    """回归：list_strategies() 返回 dict，遍历策略名必须用这个函数"""
    names = list_strategy_names()

    assert len(names) == 7
    assert all(isinstance(n, str) for n in names)
    assert "macd_cross" in names

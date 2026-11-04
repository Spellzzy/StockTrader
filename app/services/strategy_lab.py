"""策略实验室：信号质量评估 + 参数寻优 + rolling walk-forward

目的不是"多跑几个策略"，而是先回答两个问题：
    1. 这个策略的信号到底有没有预测力？（命中率、样本内外衰减）
    2. 参数是不是在样本内挑出来的？（滚动窗口，训练段选参数，测试段验证）

所有评估逻辑都是纯函数，可以用固定 K 线离线复现；只有取行情的部分触网。
"""

from __future__ import annotations

import itertools
import logging
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# 参数网格限定在 FeatureEngine 实际会算出的指标列范围内
# （MA 只有 5/10/20/60，RSI 只有 6/12/24），否则策略会取到不存在的列
PARAM_GRIDS: dict[str, dict[str, list]] = {
    "ma_cross": {"short": [5, 10, 20], "long": [10, 20, 60]},
    "rsi": {"period": [6, 12, 24], "oversold": [20, 30], "overbought": [70, 80]},
    "boll": {"low_zone": [20, 30], "high_zone": [70, 80]},
    "turtle": {"entry_period": [10, 20], "exit_period": [5, 10]},
}


# ==================== 纯逻辑：信号质量 ====================

def pair_signals(df: pd.DataFrame) -> list[dict]:
    """把买卖信号配成交易，返回每笔的收益与持仓天数"""
    trades = []
    entry = None
    for i, row in df.iterrows():
        sig = int(row.get("signal", 0))
        price = float(row["close"])
        if sig > 0 and entry is None:
            entry = (i, price, str(row.get("date", "")))
        elif sig < 0 and entry is not None:
            entry_price = entry[1]
            trades.append({
                "entry_date": entry[2],
                "exit_date": str(row.get("date", "")),
                "pnl_pct": (price - entry_price) / entry_price * 100,
                "holding_days": max(1, len(df.loc[entry[0]:i]) - 1),
            })
            entry = None
    return trades


def signal_quality_metrics(
    df: pd.DataFrame,
    horizon: int = 5,
    split_ratio: float = 0.7,
) -> dict:
    """评估信号质量（纯函数）

    命中 = 信号方向与未来 horizon 日实际涨跌方向一致。
    样本内 / 样本外按时间顺序切分（不随机切），衰减过大说明参数可能过拟合。
    """
    if df.empty or "signal" not in df.columns or "close" not in df.columns:
        return {"total_signals": 0, "hit_rate": 0.0, "decay": 0.0}

    based = df.reset_index(drop=True).copy()
    work = based.copy()
    work["fwd_return"] = work["close"].shift(-horizon) / work["close"] - 1
    work = work[work["signal"] != 0].copy()
    work = work[work["fwd_return"].notna()]

    if work.empty:
        return {"total_signals": 0, "hit_rate": 0.0, "decay": 0.0}

    work["hit"] = (
        (work["signal"] > 0) & (work["fwd_return"] > 0)
    ) | ((work["signal"] < 0) & (work["fwd_return"] < 0))
    work["directional_return"] = work["signal"] * work["fwd_return"]

    split = max(1, int(len(work) * split_ratio))
    in_sample = work.iloc[:split]
    out_sample = work.iloc[split:]

    in_hit = float(in_sample["hit"].mean() * 100) if len(in_sample) else 0.0
    out_hit = float(out_sample["hit"].mean() * 100) if len(out_sample) else 0.0
    trades = pair_signals(based)
    wins = [t for t in trades if t["pnl_pct"] > 0]

    benchmark = 0.0
    if len(based) > 1:
        benchmark = (
            float(based["close"].iloc[-1]) / float(based["close"].iloc[0]) - 1
        ) * 100

    return {
        "total_signals": int(len(work)),
        "buy_signals": int((work["signal"] > 0).sum()),
        "sell_signals": int((work["signal"] < 0).sum()),
        "hit_rate": round(float(work["hit"].mean() * 100), 2),
        "in_sample_hit_rate": round(in_hit, 2),
        "out_of_sample_hit_rate": round(out_hit, 2),
        "decay": round(in_hit - out_hit, 2),
        "avg_directional_return": round(float(work["directional_return"].mean() * 100), 3),
        "in_sample_signals": len(in_sample),
        "out_of_sample_signals": len(out_sample),
        "paired_trades": len(trades),
        "win_rate": round(len(wins) / len(trades) * 100, 2) if trades else 0.0,
        "avg_holding_days": round(
            sum(t["holding_days"] for t in trades) / len(trades), 1
        ) if trades else 0.0,
        "benchmark_return": round(benchmark, 2),
    }


# ==================== 纯逻辑：参数网格与滚动窗口 ====================

def generate_param_grid(strategy: str, max_combos: int = 12) -> list[dict]:
    """生成参数组合，过滤掉明显非法的组合"""
    grid = PARAM_GRIDS.get(strategy)
    if not grid:
        return [{}]

    keys = list(grid)
    combos = []
    for values in itertools.product(*(grid[k] for k in keys)):
        params = dict(zip(keys, values))
        if strategy == "ma_cross" and params["short"] >= params["long"]:
            continue
        if strategy == "turtle" and params["exit_period"] >= params["entry_period"]:
            continue
        combos.append(params)

    return combos[:max_combos]


def walk_forward_folds(
    n: int,
    n_splits: int = 3,
    min_train_ratio: float = 0.4,
    gap: int = 5,
) -> list[dict]:
    """扩张窗口切分（纯函数），返回每折的训练/测试区间

    gap: 训练段与测试段之间留出的样本数，避免未来 horizon 的标签跨过边界造成泄漏。
    """
    if n < 20 or n_splits < 1:
        return []

    train_start = 0
    first_train_end = int(n * min_train_ratio)
    fold_size = max(1, (n - first_train_end) // n_splits)

    folds = []
    for k in range(n_splits):
        train_end = first_train_end + k * fold_size
        test_start = min(n - 1, train_end + gap)
        test_end = min(n, test_start + fold_size)
        if test_start >= test_end:
            break
        folds.append({
            "fold": k + 1,
            "train": (train_start, train_end),
            "test": (test_start, test_end),
        })
    return folds


def walk_forward_eval(
    df: pd.DataFrame,
    strategy: str,
    param_grid: Optional[list[dict]] = None,
    n_splits: int = 3,
    horizon: int = 5,
    min_signals: int = 5,
) -> dict:
    """滚动窗口：每折用训练段挑参数，在测试段验证（纯函数，不触网）"""
    from app.services.strategy import get_strategy

    if param_grid is None:
        param_grid = generate_param_grid(strategy)

    folds = walk_forward_folds(len(df), n_splits=n_splits)
    results = []

    for fold in folds:
        train_df = df.iloc[fold["train"][0]:fold["train"][1]].reset_index(drop=True)
        test_df = df.iloc[fold["test"][0]:fold["test"][1]].reset_index(drop=True)

        best_params, best_score, best_train_signals = {}, -1.0, 0
        for params in param_grid:
            try:
                signaled = get_strategy(strategy, **params).generate_signals(train_df)
                metrics = signal_quality_metrics(signaled, horizon=horizon)
                score = metrics["hit_rate"]
                # 信号太少时命中率没有统计意义，不参与选参
                if metrics["total_signals"] < min_signals:
                    continue
            except Exception as e:
                logger.debug(f"参数 {params} 在训练段失败: {e}")
                continue
            if score > best_score:
                best_params, best_score = params, score
                best_train_signals = metrics["total_signals"]

        try:
            test_signaled = get_strategy(strategy, **best_params).generate_signals(test_df)
            test_metrics = signal_quality_metrics(test_signaled, horizon=horizon)
        except Exception as e:
            logger.debug(f"测试段评估失败: {e}")
            test_metrics = {"hit_rate": 0.0, "total_signals": 0}

        test_signals = test_metrics.get("total_signals", 0)
        results.append({
            "fold": fold["fold"],
            "best_params": best_params,
            "train_hit_rate": round(best_score, 2) if best_score >= 0 else 0.0,
            "train_signals": best_train_signals,
            "test_hit_rate": test_metrics.get("hit_rate", 0.0),
            "test_signals": test_signals,
            "reliable": test_signals >= min_signals and best_train_signals >= min_signals,
        })

    train_mean = sum(r["train_hit_rate"] for r in results) / len(results) if results else 0
    reliable = [r for r in results if r["reliable"]]
    test_mean = (
        sum(r["test_hit_rate"] for r in reliable) / len(reliable)
        if reliable else None
    )

    return {
        "strategy": strategy,
        "folds": results,
        "mean_train_hit_rate": round(train_mean, 2),
        "mean_test_hit_rate": round(test_mean, 2) if test_mean is not None else None,
        "decay": round(train_mean - test_mean, 2) if test_mean is not None else None,
        "reliable_folds": len(reliable),
        "total_folds": len(results),
        "min_signals": min_signals,
        "conclusion": (
            "样本外信号不足，无法判断是否存在过拟合，请拉长回测区间"
            if not reliable else "样本外信号充足，衰减值可参考"
        ),
    }


# ==================== 需要行情的部分 ====================

def load_featured(code: str, days: int = 250) -> pd.DataFrame:
    """取 K 线并算指标"""
    from app.domain.indicators import FeatureEngine
    from app.services.market_service import MarketService

    df = MarketService().get_kline_df(code, period="day", count=days + 80, adjust="qfq")
    if df.empty:
        return df
    featured = FeatureEngine().build_features(df, dropna=True)
    return featured.tail(days).reset_index(drop=True) if len(featured) > days else featured


class StrategyLab:
    """策略实验室服务"""

    def analyze(self, code: str, strategy: str, days: int = 250, horizon: int = 5) -> dict:
        """单个策略的信号质量"""
        from app.services.strategy import get_strategy

        df = load_featured(code, days)
        if df.empty:
            return {"code": code, "strategy": strategy, "error": "行情数据不足"}
        try:
            signaled = get_strategy(strategy).generate_signals(df)
        except Exception as e:
            return {"code": code, "strategy": strategy, "error": str(e)}

        return {
            "code": code,
            "strategy": strategy,
            **signal_quality_metrics(signaled, horizon=horizon),
        }

    def analyze_all(self, code: str, days: int = 250, horizon: int = 5) -> list[dict]:
        """7 个策略逐个评估"""
        from app.services.strategy import list_strategy_names

        df = load_featured(code, days)
        if df.empty:
            return []

        results = []
        for name in list_strategy_names():
            try:
                from app.services.strategy import get_strategy

                signaled = get_strategy(name).generate_signals(df)
                results.append({
                    "code": code,
                    "strategy": name,
                    **signal_quality_metrics(signaled, horizon=horizon),
                })
            except Exception as e:
                logger.warning(f"策略 {name} 评估失败: {e}")
        return results

    def grid_search(
        self,
        code: str,
        strategy: str,
        days: int = 180,
        max_combos: int = 10,
    ) -> dict:
        """参数网格搜索：每组参数跑一次完整回测（次日开盘成交口径）"""
        from app.services.backtest_service import BacktestService

        combos = generate_param_grid(strategy, max_combos=max_combos)
        service = BacktestService()
        rows = []

        for params in combos:
            try:
                result = service.run(code, strategy=strategy, days=days, **params)
                rows.append({
                    "params": params,
                    "total_return": result.total_return,
                    "max_drawdown": result.max_drawdown,
                    "sharpe_ratio": result.sharpe_ratio,
                    "total_trades": result.total_trades,
                })
            except Exception as e:
                logger.warning(f"参数 {params} 回测失败: {e}")

        rows.sort(key=lambda r: r["total_return"], reverse=True)
        return {
            "code": code,
            "strategy": strategy,
            "combos": len(combos),
            "rows": rows,
            "best": rows[0] if rows else None,
        }

    def walk_forward(
        self,
        code: str,
        strategy: str,
        days: int = 250,
        n_splits: int = 3,
        max_combos: int = 8,
    ) -> dict:
        """滚动窗口验证：真实行情 + 纯逻辑评估，输出样本外衰减"""
        df = load_featured(code, days)
        if df.empty:
            return {"code": code, "strategy": strategy, "error": "行情数据不足"}
        return {
            "code": code,
            **walk_forward_eval(
                df, strategy, generate_param_grid(strategy, max_combos),
                n_splits=n_splits,
            ),
        }

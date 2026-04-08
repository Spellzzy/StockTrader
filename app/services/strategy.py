"""回测策略模块 — 内置经典交易策略

每个策略实现 generate_signals() 方法，输入含技术指标的 DataFrame，
输出带 signal 列的 DataFrame:
    signal = 1  → 买入
    signal = -1 → 卖出
    signal = 0  → 持有/空仓
"""

from abc import ABC, abstractmethod
from typing import Optional

import pandas as pd
import numpy as np


class BaseStrategy(ABC):
    """策略基类"""

    name: str = "base"
    description: str = "基础策略"

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """生成交易信号

        Args:
            df: 含技术指标的 DataFrame (由 FeatureEngine.build_features 产出)

        Returns:
            添加了 signal 列的 DataFrame
        """
        ...

    def __repr__(self) -> str:
        return f"<Strategy({self.name}: {self.description})>"


class MACDCrossStrategy(BaseStrategy):
    """MACD 金叉死叉策略

    - 金叉 (DIF 上穿 DEA): 买入
    - 死叉 (DIF 下穿 DEA): 卖出
    """

    name = "macd_cross"
    description = "MACD金叉买入/死叉卖出"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["signal"] = 0
        df.loc[df["macd_cross"] == 1, "signal"] = 1   # 金叉买入
        df.loc[df["macd_cross"] == -1, "signal"] = -1  # 死叉卖出
        return df


class MACrossStrategy(BaseStrategy):
    """均线突破策略

    - 短期均线上穿长期均线: 买入
    - 短期均线下穿长期均线: 卖出
    """

    name = "ma_cross"
    description = "均线金叉买入/死叉卖出"

    def __init__(self, short: int = 5, long: int = 20):
        self.short = short
        self.long = long
        self.description = f"MA{short}/MA{long} 均线交叉"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        short_col = f"ma{self.short}"
        long_col = f"ma{self.long}"

        if short_col not in df.columns or long_col not in df.columns:
            # 自行计算
            df[short_col] = df["close"].rolling(self.short).mean()
            df[long_col] = df["close"].rolling(self.long).mean()

        df["signal"] = 0
        # 金叉：短均线从下方穿越长均线
        cross_up = (df[short_col] > df[long_col]) & (df[short_col].shift(1) <= df[long_col].shift(1))
        cross_down = (df[short_col] < df[long_col]) & (df[short_col].shift(1) >= df[long_col].shift(1))
        df.loc[cross_up, "signal"] = 1
        df.loc[cross_down, "signal"] = -1
        return df


class RSIOversoldStrategy(BaseStrategy):
    """RSI 超买超卖策略

    - RSI < oversold (默认 30): 买入
    - RSI > overbought (默认 70): 卖出
    """

    name = "rsi"
    description = "RSI超卖买入/超买卖出"

    def __init__(self, period: int = 6, oversold: float = 30.0, overbought: float = 70.0):
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self.description = f"RSI{period} <{oversold}买入 >{overbought}卖出"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        rsi_col = f"rsi{self.period}"
        if rsi_col not in df.columns:
            rsi_col = "rsi6"  # 回退到默认的 rsi6

        df["signal"] = 0
        # 从超卖区回升时买入（前一根在超卖区，当前穿越上来）
        df.loc[
            (df[rsi_col] > self.oversold) & (df[rsi_col].shift(1) <= self.oversold),
            "signal",
        ] = 1
        # 从超买区回落时卖出
        df.loc[
            (df[rsi_col] < self.overbought) & (df[rsi_col].shift(1) >= self.overbought),
            "signal",
        ] = -1
        return df


class BollBandStrategy(BaseStrategy):
    """布林带突破策略

    - 价格跌破下轨后回升: 买入
    - 价格突破上轨后回落: 卖出
    """

    name = "boll"
    description = "布林带下轨买入/上轨卖出"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["signal"] = 0

        if "boll_upper" not in df.columns:
            return df

        # 跌破下轨后反弹回轨内 → 买入
        bounce_up = (df["close"] > df["boll_lower"]) & (df["close"].shift(1) <= df["boll_lower"].shift(1))
        # 突破上轨后回落到轨内 → 卖出
        drop_down = (df["close"] < df["boll_upper"]) & (df["close"].shift(1) >= df["boll_upper"].shift(1))

        df.loc[bounce_up, "signal"] = 1
        df.loc[drop_down, "signal"] = -1
        return df


class KDJCrossStrategy(BaseStrategy):
    """KDJ 金叉死叉策略

    - K线上穿D线 (在低位更佳): 买入
    - K线下穿D线 (在高位更佳): 卖出
    """

    name = "kdj"
    description = "KDJ金叉买入/死叉卖出"

    def __init__(self, low_zone: float = 30.0, high_zone: float = 70.0):
        self.low_zone = low_zone
        self.high_zone = high_zone

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["signal"] = 0

        if "kdj_k" not in df.columns or "kdj_d" not in df.columns:
            return df

        # 金叉: K 上穿 D
        cross_up = (df["kdj_k"] > df["kdj_d"]) & (df["kdj_k"].shift(1) <= df["kdj_d"].shift(1))
        # 死叉: K 下穿 D
        cross_down = (df["kdj_k"] < df["kdj_d"]) & (df["kdj_k"].shift(1) >= df["kdj_d"].shift(1))

        # 低位金叉更可靠
        df.loc[cross_up & (df["kdj_k"] < self.low_zone), "signal"] = 1
        # 高位死叉更可靠
        df.loc[cross_down & (df["kdj_k"] > self.high_zone), "signal"] = -1
        return df


class DualMACDStrategy(BaseStrategy):
    """双均线 + MACD 共振策略

    同时满足:
    - 均线多头排列 + MACD 金叉 → 买入
    - 均线跌破 + MACD 死叉 → 卖出
    """

    name = "dual_macd"
    description = "均线+MACD双重确认"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["signal"] = 0

        # 买入: 均线多头 + MACD 金叉
        buy_cond = (df.get("ma_bull", pd.Series(0, index=df.index)) == 1) & (df["macd_cross"] == 1)
        # 卖出: 均线空头 + MACD 死叉
        sell_cond = (df.get("ma_bull", pd.Series(0, index=df.index)) == 0) & (df["macd_cross"] == -1)

        if "ma_bull" in df.columns:
            buy_cond = (df["ma_bull"] == 1) & (df["macd_cross"] == 1)
            sell_cond = (df["ma_bull"] == 0) & (df["macd_cross"] == -1)

        df.loc[buy_cond, "signal"] = 1
        df.loc[sell_cond, "signal"] = -1
        return df


class TurtleBreakoutStrategy(BaseStrategy):
    """海龟突破策略 (简化版)

    - 价格突破 N 日最高价: 买入
    - 价格跌破 N 日最低价: 卖出
    """

    name = "turtle"
    description = "海龟突破策略"

    def __init__(self, entry_period: int = 20, exit_period: int = 10):
        self.entry_period = entry_period
        self.exit_period = exit_period
        self.description = f"突破{entry_period}日高点买入/{exit_period}日低点卖出"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["signal"] = 0

        # N日最高价/最低价 (不含当天)
        df["high_n"] = df["high"].shift(1).rolling(self.entry_period).max()
        df["low_n"] = df["low"].shift(1).rolling(self.exit_period).min()

        # 突破买入
        df.loc[df["close"] > df["high_n"], "signal"] = 1
        # 跌破卖出
        df.loc[df["close"] < df["low_n"], "signal"] = -1

        # 清理临时列
        df.drop(columns=["high_n", "low_n"], inplace=True)
        return df


# ==================== 策略注册表 ====================

BUILTIN_STRATEGIES = {
    "macd_cross": MACDCrossStrategy,
    "ma_cross": MACrossStrategy,
    "rsi": RSIOversoldStrategy,
    "boll": BollBandStrategy,
    "kdj": KDJCrossStrategy,
    "dual_macd": DualMACDStrategy,
    "turtle": TurtleBreakoutStrategy,
}


def get_strategy(name: str, **kwargs) -> BaseStrategy:
    """根据名称获取策略实例

    Args:
        name: 策略名称 (macd_cross / ma_cross / rsi / boll / kdj / dual_macd / turtle)
        **kwargs: 策略参数

    Returns:
        策略实例

    Raises:
        ValueError: 未知策略名称
    """
    cls = BUILTIN_STRATEGIES.get(name)
    if cls is None:
        valid = ", ".join(BUILTIN_STRATEGIES.keys())
        raise ValueError(f"未知策略: {name}\n可用策略: {valid}")
    return cls(**kwargs)


def list_strategies() -> list:
    """列出所有内置策略"""
    result = []
    for name, cls in BUILTIN_STRATEGIES.items():
        instance = cls()
        result.append({
            "name": name,
            "description": instance.description,
            "class": cls.__name__,
        })
    return result

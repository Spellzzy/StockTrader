"""特征工程 — 技术指标计算

将 K线 DataFrame 转化为包含丰富技术指标的特征矩阵，
供 ML / DL 预测模型使用。

输入: pd.DataFrame with columns [date, open, close, high, low, volume, amount, turnover]
输出: pd.DataFrame with 原始列 + 40+ 技术指标列
"""

import numpy as np
import pandas as pd
from typing import Optional


class FeatureEngine:
    """技术指标特征工程"""

    def build_features(self, df: pd.DataFrame, dropna: bool = True) -> pd.DataFrame:
        """一次性计算所有特征

        Args:
            df: K线数据 (需含 open, close, high, low, volume 列)
            dropna: 是否丢弃含 NaN 的行（前 N 根 K 线因窗口期会有 NaN）

        Returns:
            含技术指标列的 DataFrame
        """
        df = df.copy()

        # ── 趋势类 ──
        self._add_ma(df)
        self._add_ema(df)
        self._add_macd(df)

        # ── 动量类 ──
        self._add_rsi(df)
        self._add_kdj(df)
        self._add_roc(df)
        self._add_wr(df)

        # ── 波动类 ──
        self._add_boll(df)
        self._add_atr(df)

        # ── 成交量类 ──
        self._add_volume_features(df)

        # ── 价格衍生 ──
        self._add_price_features(df)

        # ── 涨跌幅 / 动量 ──
        self._add_returns(df)

        if dropna:
            df = df.dropna().reset_index(drop=True)

        return df

    # ==================== 趋势类 ====================

    @staticmethod
    def _add_ma(df: pd.DataFrame):
        """简单移动均线 MA5 / MA10 / MA20 / MA60"""
        for w in [5, 10, 20, 60]:
            df[f"ma{w}"] = df["close"].rolling(w).mean()
        # 均线多头排列信号: MA5 > MA10 > MA20
        df["ma_bull"] = ((df["ma5"] > df["ma10"]) & (df["ma10"] > df["ma20"])).astype(int)

    @staticmethod
    def _add_ema(df: pd.DataFrame):
        """指数移动均线 EMA12 / EMA26"""
        df["ema12"] = df["close"].ewm(span=12, adjust=False).mean()
        df["ema26"] = df["close"].ewm(span=26, adjust=False).mean()

    @staticmethod
    def _add_macd(df: pd.DataFrame):
        """MACD (DIF, DEA, MACD柱)"""
        ema12 = df["close"].ewm(span=12, adjust=False).mean()
        ema26 = df["close"].ewm(span=26, adjust=False).mean()
        df["macd_dif"] = ema12 - ema26
        df["macd_dea"] = df["macd_dif"].ewm(span=9, adjust=False).mean()
        df["macd_hist"] = 2 * (df["macd_dif"] - df["macd_dea"])
        # 金叉信号
        df["macd_cross"] = 0
        df.loc[(df["macd_dif"] > df["macd_dea"]) &
               (df["macd_dif"].shift(1) <= df["macd_dea"].shift(1)), "macd_cross"] = 1
        df.loc[(df["macd_dif"] < df["macd_dea"]) &
               (df["macd_dif"].shift(1) >= df["macd_dea"].shift(1)), "macd_cross"] = -1

    # ==================== 动量类 ====================

    @staticmethod
    def _add_rsi(df: pd.DataFrame, periods: tuple = (6, 12, 24)):
        """RSI 相对强弱指标"""
        for p in periods:
            delta = df["close"].diff()
            gain = delta.clip(lower=0)
            loss = (-delta).clip(lower=0)
            avg_gain = gain.rolling(p).mean()
            avg_loss = loss.rolling(p).mean()
            rs = avg_gain / (avg_loss + 1e-10)
            df[f"rsi{p}"] = 100 - (100 / (1 + rs))

    @staticmethod
    def _add_kdj(df: pd.DataFrame, n: int = 9):
        """KDJ 随机指标"""
        low_n = df["low"].rolling(n).min()
        high_n = df["high"].rolling(n).max()
        rsv = (df["close"] - low_n) / (high_n - low_n + 1e-10) * 100

        k = pd.Series(np.nan, index=df.index)
        d = pd.Series(np.nan, index=df.index)

        k.iloc[n - 1] = 50.0
        d.iloc[n - 1] = 50.0

        for i in range(n, len(df)):
            k.iloc[i] = 2 / 3 * k.iloc[i - 1] + 1 / 3 * rsv.iloc[i]
            d.iloc[i] = 2 / 3 * d.iloc[i - 1] + 1 / 3 * k.iloc[i]

        df["kdj_k"] = k
        df["kdj_d"] = d
        df["kdj_j"] = 3 * k - 2 * d

    @staticmethod
    def _add_roc(df: pd.DataFrame):
        """ROC 变动速率"""
        df["roc6"] = df["close"].pct_change(6) * 100
        df["roc12"] = df["close"].pct_change(12) * 100

    @staticmethod
    def _add_wr(df: pd.DataFrame, n: int = 14):
        """WR 威廉指标"""
        high_n = df["high"].rolling(n).max()
        low_n = df["low"].rolling(n).min()
        df[f"wr{n}"] = (high_n - df["close"]) / (high_n - low_n + 1e-10) * 100

    # ==================== 波动类 ====================

    @staticmethod
    def _add_boll(df: pd.DataFrame, n: int = 20, k: float = 2.0):
        """布林带"""
        ma = df["close"].rolling(n).mean()
        std = df["close"].rolling(n).std()
        df["boll_upper"] = ma + k * std
        df["boll_mid"] = ma
        df["boll_lower"] = ma - k * std
        # 价格在布林带中的位置 (0~1)
        df["boll_pct"] = (df["close"] - df["boll_lower"]) / (df["boll_upper"] - df["boll_lower"] + 1e-10)

    @staticmethod
    def _add_atr(df: pd.DataFrame, n: int = 14):
        """ATR 平均真实波幅"""
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift(1)).abs()
        low_close = (df["low"] - df["close"].shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr"] = tr.rolling(n).mean()
        # ATR 比率（相对于价格的波动率）
        df["atr_pct"] = df["atr"] / (df["close"] + 1e-10) * 100

    # ==================== 成交量类 ====================

    @staticmethod
    def _add_volume_features(df: pd.DataFrame):
        """成交量衍生特征"""
        # 量比 (当日量 / 5日均量)
        vol_ma5 = df["volume"].rolling(5).mean()
        df["vol_ratio"] = df["volume"] / (vol_ma5 + 1e-10)

        # OBV 能量潮
        sign = np.sign(df["close"].diff())
        df["obv"] = (sign * df["volume"]).cumsum()
        # OBV 变化率
        df["obv_change"] = df["obv"].pct_change(5)

        # 量均线
        df["vol_ma5"] = vol_ma5
        df["vol_ma20"] = df["volume"].rolling(20).mean()

    # ==================== 价格衍生 ====================

    @staticmethod
    def _add_price_features(df: pd.DataFrame):
        """价格衍生特征"""
        # 实体大小
        df["body"] = (df["close"] - df["open"]) / (df["open"] + 1e-10) * 100
        # 上下影线
        df["upper_shadow"] = (df["high"] - df[["open", "close"]].max(axis=1)) / (df["open"] + 1e-10) * 100
        df["lower_shadow"] = (df[["open", "close"]].min(axis=1) - df["low"]) / (df["open"] + 1e-10) * 100
        # 振幅
        df["amplitude"] = (df["high"] - df["low"]) / (df["close"].shift(1) + 1e-10) * 100
        # 价格距离均线的偏离度 (BIAS)
        for w in [5, 10, 20]:
            ma = df["close"].rolling(w).mean()
            df[f"bias{w}"] = (df["close"] - ma) / (ma + 1e-10) * 100

    # ==================== 涨跌幅 ====================

    @staticmethod
    def _add_returns(df: pd.DataFrame):
        """收益率 / 动量"""
        df["return_1d"] = df["close"].pct_change(1) * 100
        df["return_3d"] = df["close"].pct_change(3) * 100
        df["return_5d"] = df["close"].pct_change(5) * 100
        df["return_10d"] = df["close"].pct_change(10) * 100

    # ==================== 标签构造 ====================

    @staticmethod
    def add_label_classification(
        df: pd.DataFrame,
        horizon: int = 5,
        threshold: float = 2.0,
    ) -> pd.DataFrame:
        """添加分类标签: 未来 N 日涨跌方向

        Args:
            df: 特征 DataFrame
            horizon: 预测未来天数
            threshold: 涨跌阈值(%)。涨幅>threshold → 1(涨), 跌幅>threshold → -1(跌), 其余 → 0(震荡)

        Returns:
            添加了 label 列的 DataFrame
        """
        df = df.copy()
        future_return = df["close"].shift(-horizon) / df["close"] * 100 - 100
        df["label"] = 0
        df.loc[future_return > threshold, "label"] = 1   # 看涨
        df.loc[future_return < -threshold, "label"] = -1  # 看跌
        # 删掉末尾没有 label 的行
        df = df.iloc[:-horizon].copy()
        return df

    @staticmethod
    def add_label_regression(df: pd.DataFrame, horizon: int = 5) -> pd.DataFrame:
        """添加回归标签: 未来 N 日涨跌幅(%)"""
        df = df.copy()
        df["label"] = df["close"].shift(-horizon) / df["close"] * 100 - 100
        df = df.iloc[:-horizon].copy()
        return df

    def get_feature_columns(self, df: pd.DataFrame) -> list:
        """获取所有特征列名 (排除日期、label 等非特征列)"""
        exclude = {"date", "label", "open", "close", "high", "low", "volume", "amount", "turnover"}
        return [c for c in df.columns if c not in exclude]

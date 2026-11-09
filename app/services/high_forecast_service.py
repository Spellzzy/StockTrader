"""今日目标最高价 —— 统计分位数口径（不训练模型）

口径
----
- **盘前**：用历史「当日最高价相对昨收涨幅」的 P50/P75/P90 分位数，
  给出全天目标高点区间与经验触及频率。
- **盘中**：已知当日已实现最高价，剩余空间按交易时间进度衰减
  ``decay = (1 - progress) ** alpha``，区间随时间收敛，最终不低于已实现高点。
- **收盘/非当日行情**：不再预测，展示当日实际最高价。

质量评估
--------
用同一套逻辑做 walk-forward 回测：每天只用之前 lookback 根算分位数，
与实际当日最高价比较，给出触及率、MAE、区间覆盖率，并与「昨日高点」
朴素基线比较。不优于基线会明确标注，沿用项目的质量闸门调性。

边界：涨跌停 clamp、指数拒绝、样本不足报错、港股/美股不设涨跌停。
**统计区间不是承诺价格，不构成投资建议。**
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import numpy as np

from app.config import get_config
from app.models.stock import is_index_code, normalize_stock_code
from app.services.market_service import MarketService

logger = logging.getLogger(__name__)

DEFAULT_LOOKBACK = 120
DEFAULT_LEVELS = (50, 75, 90)
DEFAULT_BACKTEST_DAYS = 60
DEFAULT_DECAY_ALPHA = 0.7
DEFAULT_STOP_LOSS_PCT = 5.0
MIN_SAMPLES = 30


def _cfg() -> dict:
    return ((get_config().get("forecast") or {}).get("high", {}) or {})


def trading_progress(now: Optional[datetime] = None) -> tuple[str, float]:
    """按 A 股交易时钟返回 (premarket/intraday/closed, 进度 0~1)"""
    now = now or datetime.now()
    minutes = now.hour * 60 + now.minute
    if minutes < 9 * 60 + 30:
        return "premarket", 0.0
    if minutes <= 11 * 60 + 30:
        return "intraday", (minutes - 570) / 240
    if minutes < 13 * 60:
        return "intraday", 0.5
    if minutes < 15 * 60:
        return "intraday", (120 + minutes - 780) / 240
    return "closed", 1.0


def limit_up_pct(code: str, name: str = "") -> Optional[float]:
    """涨停幅度（%）；非 A 股返回 None 表示不做 clamp"""
    if name and "ST" in name.upper():
        return 5.0
    c = code.lower()
    if c.startswith("bj"):
        return 30.0
    if c.startswith(("sh688", "sh689", "sz300", "sz301")):
        return 20.0
    if c.startswith(("sh", "sz")):
        return 10.0
    return None


class HighForecastService:
    """今日目标最高价（纯只读，不落库、不训练）"""

    def __init__(self, market=None, config: Optional[dict] = None):
        self.market = market or MarketService()
        self.cfg = dict(config if config is not None else _cfg())

    def forecast(
        self,
        code: str,
        now: Optional[datetime] = None,
        quote: Optional[dict] = None,
    ) -> dict:
        """估算今日区间与目标高点

        Args:
            quote: 可选。外部已批量取好的单只行情，传入后不再单独请求
                   （日报批量生成时用它把 N 次子进程合并为 1 次）。
        """
        norm = normalize_stock_code((code or "").strip())
        if is_index_code(norm):
            raise ValueError("指数不适用个股目标高点预测")

        now = now or datetime.now()
        lookback = int(self.cfg.get("lookback", DEFAULT_LOOKBACK))
        levels = tuple(int(x) for x in self.cfg.get("levels", DEFAULT_LEVELS))
        alpha = float(self.cfg.get("decay_alpha", DEFAULT_DECAY_ALPHA))
        backtest_days = int(self.cfg.get("backtest_days", DEFAULT_BACKTEST_DAYS))

        # 要同时满足「主预测回看」与「walk-forward 回测」，取数必须覆盖两段
        fetch_count = lookback + backtest_days + 10
        df = self.market.get_kline_df(norm, count=fetch_count)
        if df is None or len(df) < MIN_SAMPLES:
            raise ValueError("历史 K 线不足，无法估计目标高点")

        if quote is None:
            try:
                quote = (self.market.get_quote(norm) or {}).get(norm) or {}
            except Exception as e:
                logger.warning(f"实时行情获取失败 {norm}: {e}")
                quote = {}
        quote = quote or {}

        qtime = str(quote.get("time") or "")
        quote_day = ""
        if len(qtime) >= 8 and qtime[:8].isdigit():
            quote_day = f"{qtime[:4]}-{qtime[4:6]}-{qtime[6:8]}"
        today = now.strftime("%Y-%m-%d")

        # 剔除当日 K 线：历史样本只能包含预测时点之前的数据，避免前视偏差
        date_str = df["date"].astype(str).str[:10]
        exclude_day = quote_day or today
        hist = df[date_str != exclude_day].copy()
        if len(hist) < MIN_SAMPLES:
            hist = df.copy()

        prev_series = hist["close"].shift(1)
        up_all = (hist["high"] - prev_series) / prev_series * 100
        dn_all = (hist["low"] - prev_series) / prev_series * 100
        rng_all = (hist["high"] - hist["low"]) / prev_series * 100
        # 分位数严格只用最近 lookback 根，但 prev_close 用完整序列算，避免首根失真
        up = up_all.tail(lookback)
        dn = dn_all.tail(lookback).replace([np.inf, -np.inf], np.nan).dropna()
        rng = rng_all.tail(lookback)
        up_valid = up.replace([np.inf, -np.inf], np.nan).dropna()
        if len(up_valid) < MIN_SAMPLES:
            raise ValueError("有效历史样本不足（需要至少 30 个交易日）")

        quantiles = {lv: float(np.percentile(up_valid, lv)) for lv in levels}
        # 低点侧：P25 是较深的回调（区间下沿），P50 是中位低点
        down_p25 = float(np.percentile(dn, 25)) if len(dn) >= MIN_SAMPLES else None
        down_p50 = float(np.percentile(dn, 50)) if len(dn) >= MIN_SAMPLES else None
        amp_p75 = float(np.nanpercentile(rng.dropna(), 75))

        prev_close = float(quote.get("prev_close") or 0) or float(hist["close"].iloc[-1])
        price = float(quote.get("price") or 0)
        day_high = float(quote.get("high") or 0)
        day_low = float(quote.get("low") or 0)
        open_price = float(quote.get("open") or 0)
        name = str(quote.get("name") or "")
        has_today = price > 0 and prev_close > 0

        phase, progress = trading_progress(now)
        if not has_today:
            phase, progress = "premarket", 0.0
        elif quote_day and quote_day != today:
            # 行情不是当天的（周末/节假日访问），按收盘展示，不做盘中预测
            phase, progress = "closed", 1.0

        decay = (
            (1.0 - progress) ** alpha if phase == "intraday"
            else (0.0 if phase == "closed" else 1.0)
        )

        limit_pct = limit_up_pct(norm, name)
        cap = prev_close * (1 + limit_pct / 100) if limit_pct else None
        realized = max(day_high, price) if has_today else 0.0

        targets = {}
        for lv in levels:
            full = prev_close * (1 + quantiles[lv] / 100)
            if phase == "intraday":
                remaining = max(0.0, full - realized) * decay
                value = realized + remaining
            elif phase == "closed":
                value = realized
            else:
                value = full
            if cap is not None:
                value = min(value, cap)
            if phase == "intraday":
                value = max(value, realized)  # 不能低于当天已经出现过的高点
            targets[f"p{lv}"] = round(value, 3)

        probabilities = {}
        for lv in levels:
            empirical = (100 - lv) / 100
            probabilities[f"p{lv}"] = round(
                empirical * (decay if phase == "intraday" else (0.0 if phase == "closed" else 1.0)), 3
            )

        ref = price if price > 0 else prev_close
        upside = {k: round((v - ref) / ref * 100, 2) for k, v in targets.items()}

        center_key = "p75" if "p75" in targets else f"p{levels[len(levels) // 2]}"
        low_key = f"p{levels[0]}"
        high_key = f"p{levels[-1]}"

        # ---- 今日参考区间与买卖参考价 ----
        # 下沿：盘前用历史「最低价相对昨收」P25（较深回调），盘中改用当日已实现最低价；
        # 上沿：目标高点中枢。买卖参考价取区间 25% / 75% 分位，口径统一可解释。
        limit_down = prev_close * (1 - limit_pct / 100) if limit_pct else None
        theoretical_low = prev_close * (
            1 + (down_p25 if down_p25 is not None else 0) / 100
        )
        if phase == "closed":
            range_low = day_low if day_low > 0 else theoretical_low
            range_high = realized
        elif phase == "intraday":
            range_low = day_low if day_low > 0 else theoretical_low
            range_high = max(targets[center_key], realized)
        else:
            range_low = theoretical_low
            range_high = targets[center_key]

        if limit_down is not None:
            range_low = max(range_low, limit_down)
        if cap is not None:
            range_high = min(range_high, cap)
        range_high = max(range_high, range_low)
        span = range_high - range_low
        buy_ref = round(range_low + span * 0.25, 3)
        sell_ref = round(range_low + span * 0.75, 3)
        if phase == "intraday" and price > 0:
            # 盘中现价可能已冲到区间上部：参考价面向剩余时段，
            # 卖出不低于现价、买入不高于现价，避免出现「低于现价的卖出价」。
            buy_ref = round(min(buy_ref, price), 3)
            sell_ref = round(max(sell_ref, price), 3)
        day_range = {"low": round(range_low, 3), "high": round(range_high, 3)}

        # 止损参考：买入参考价下方 stop_loss_pct，且不低于跌停价。
        # clamp 后实际亏损比例会变小（甚至为 0），如实返回，避免虚标 -5%。
        stop_loss_target = float(self.cfg.get("stop_loss_pct", DEFAULT_STOP_LOSS_PCT))
        stop_loss_target = max(0.0, min(stop_loss_target, 50.0))
        stop_loss_ref = buy_ref * (1 - stop_loss_target / 100)
        if limit_down is not None:
            stop_loss_ref = max(stop_loss_ref, limit_down)
        stop_loss_ref = round(stop_loss_ref, 3)
        actual_stop_pct = (
            round((buy_ref - stop_loss_ref) / buy_ref * 100, 2) if buy_ref > 0 else 0.0
        )

        # 若数据源给的根数不足，自动缩短回测窗口，保证至少能评估出样本
        bt_lookback = min(lookback, max(MIN_SAMPLES, len(hist) - backtest_days - 1))
        quality = self._backtest(hist, bt_lookback, backtest_days)

        note = "统计区间与参考价，非承诺价格、非投资建议，不构成买卖依据。"
        if phase == "closed":
            note = "已收盘或行情非当日，下方展示当日实际最高价，不再预测。" + note
        elif phase == "intraday":
            note = "盘中口径：剩余空间按交易时间进度衰减（经验模型）。" + note
        if quality.get("samples") and not quality.get("better_than_baseline", True):
            note += " 回测显示该区间不优于「昨日高点」朴素基线，请谨慎参考。"

        return {
            "code": norm,
            "name": name,
            "as_of": qtime or now.isoformat(timespec="seconds"),
            "phase": phase,
            "progress": round(progress, 3),
            "price": price,
            "prev_close": round(prev_close, 3),
            "open": open_price,
            "day_high": day_high,
            "day_low": day_low,
            "realized_high": round(realized, 3),
            "targets": targets,
            "center": targets[center_key],
            "band": {"low": targets[low_key], "high": targets[high_key]},
            "day_range": day_range,
            "low_ref": day_range["low"],
            "buy_ref": buy_ref,
            "sell_ref": sell_ref,
            "stop_loss_ref": stop_loss_ref,
            "stop_loss_pct": actual_stop_pct,
            "probabilities": probabilities,
            "upside_pct": upside,
            "basis": {
                "sample_days": int(len(up_valid)),
                "lookback": lookback,
                "backtest_lookback": bt_lookback,
                "up_quantiles_pct": {f"p{lv}": round(quantiles[lv], 2) for lv in levels},
                "down_p25_pct": round(down_p25, 2) if down_p25 is not None else None,
                "down_p50_pct": round(down_p50, 2) if down_p50 is not None else None,
                "amplitude_p75_pct": round(amp_p75, 2),
                "decay": round(decay, 3),
                "decay_alpha": alpha,
                "stop_loss_target_pct": stop_loss_target,
                "limit_pct": limit_pct,
                "limit_price": round(cap, 3) if cap else None,
                "limit_down": round(limit_down, 3) if limit_down else None,
            },
            "quality": quality,
            "method": "historical-quantile + intraday-time-decay (no ML model)",
            "note": note,
        }

    @staticmethod
    def _backtest(df, lookback: int, max_days: int) -> dict:
        """walk-forward：每天只用之前 lookback 根算分位数，与当日实际高点比较"""
        prev = df["close"].shift(1)
        up = ((df["high"] - prev) / prev * 100).to_numpy(dtype=float)
        dn = ((df["low"] - prev) / prev * 100).to_numpy(dtype=float)
        highs = df["high"].to_numpy(dtype=float)
        lows = df["low"].to_numpy(dtype=float)
        closes = df["close"].to_numpy(dtype=float)
        n = len(df)
        start = max(lookback, n - max_days)
        records = []

        for t in range(start, n):
            window = up[t - lookback:t]
            window = window[np.isfinite(window)]
            if len(window) < MIN_SAMPLES:
                continue
            window_dn = dn[t - lookback:t]
            window_dn = window_dn[np.isfinite(window_dn)]
            if len(window_dn) < MIN_SAMPLES:
                continue
            q50, q75, q90 = np.percentile(window, [50, 75, 90])
            q25_dn = np.percentile(window_dn, 25)
            pc = closes[t - 1]
            if not pc or not np.isfinite(pc):
                continue
            records.append({
                "p50": pc * (1 + q50 / 100),
                "p75": pc * (1 + q75 / 100),
                "p90": pc * (1 + q90 / 100),
                "pred_low": pc * (1 + q25_dn / 100),
                "actual": highs[t],
                "actual_low": lows[t],
                "baseline": highs[t - 1],
            })

        if not records:
            return {"samples": 0, "note": "回测样本不足，无法评估命中质量"}

        actual = np.array([r["actual"] for r in records], dtype=float)
        valid = actual > 0
        mae = float(np.mean([
            abs(r["p75"] - r["actual"]) / r["actual"] * 100 for r in records
        ]))
        baseline_mae = float(np.mean([
            abs(r["baseline"] - r["actual"]) / r["actual"] * 100 for r in records
        ]))
        p50 = np.array([r["p50"] for r in records])
        p90 = np.array([r["p90"] for r in records])
        p75 = np.array([r["p75"] for r in records])
        actual_low = np.array([r["actual_low"] for r in records], dtype=float)
        pred_low = np.array([r["pred_low"] for r in records], dtype=float)
        # 区间覆盖率：当日实际 [low, high] 是否落在「P25 低点 ~ P75 高点」区间内
        range_coverage = float(np.mean((actual_low >= pred_low) & (actual <= p75)))

        return {
            "samples": len(records),
            "touch_p50": round(float(np.mean(actual[valid] >= p50[valid])), 3),
            "touch_p75": round(float(np.mean(actual[valid] >= p75[valid])), 3),
            "touch_p90": round(float(np.mean(actual[valid] >= p90[valid])), 3),
            "mae_pct": round(mae, 2),
            "baseline_mae_pct": round(baseline_mae, 2),
            "coverage": round(float(np.mean((actual >= p50) & (actual <= p90))), 3),
            "range_coverage": round(range_coverage, 3),
            "better_than_baseline": mae < baseline_mae,
            "note": "walk-forward：每日仅用之前 lookback 根数据，预测当日最高价的 P75 中枢",
        }

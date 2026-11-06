"""盘中量比：与 watch CLI 同一套口径。

源字段优先 ``quote.volume_ratio``，缺则 ``vol_ratio``（0 / 空视为缺）。
两者都没有时，用「排除当天的最多 5 日均量」按已过交易分钟折算：

    expected = avg5 * (elapsed_min / 240)
    量比 = 当日累计量 / expected

交易分钟与 ``app/commands/watch.py`` 里预计算量比的分段一致：
9:30 前为 0，上午 9:30–11:30，午休按已满 120，下午 13:00–15:00，收盘后 240。
算不出正的量比时返回 None，由展示层写成「—」，而不是 0.00。
"""

from __future__ import annotations

from datetime import datetime

TRADING_DAY_MINUTES = 240


def trading_elapsed_minutes(now: datetime) -> float:
    """当日已过的连续竞价分钟数。9:30 前为 0，15:00 及之后为 240。"""
    morning_start = now.replace(hour=9, minute=30, second=0)
    morning_end = now.replace(hour=11, minute=30, second=0)
    afternoon_start = now.replace(hour=13, minute=0, second=0)
    afternoon_end = now.replace(hour=15, minute=0, second=0)
    if now >= afternoon_end:
        return float(TRADING_DAY_MINUTES)
    if now >= afternoon_start:
        return 120 + (now - afternoon_start).total_seconds() / 60
    if now >= morning_end:
        return 120.0
    if now >= morning_start:
        return (now - morning_start).total_seconds() / 60
    return 0.0


def prior_avg_volume(kdf, days: int = 5) -> float | None:
    """排除最后一根（当天），对剩余 ``volume`` 取最多 ``days`` 日均值。

    行数不足（无法丢掉当天后仍有样本）时返回 None，调用方可以下轮再取。
    """
    if kdf is None or getattr(kdf, "empty", True) or len(kdf) < 2:
        return None
    hist = kdf.iloc[:-1]
    if len(hist) == 0:
        return None
    return float(hist["volume"].tail(days).mean())


def quote_volume_ratio(quote: dict | None) -> float | None:
    """``volume_ratio`` 优先，缺（0 / 空）则 ``vol_ratio``。非正数视为没有源值。"""
    if not isinstance(quote, dict):
        return None
    raw = quote.get("volume_ratio", 0) or quote.get("vol_ratio", 0)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value != value or value <= 0:  # NaN 或非正
        return None
    return value


def intraday_volume_ratio(cur_vol, avg5, elapsed_min) -> float | None:
    """cur_vol / (avg5 * elapsed/240)。任一条件不成立则没有可用量比。"""
    try:
        elapsed = float(elapsed_min)
        avg = float(avg5)
        cur = float(0 if cur_vol is None else cur_vol)
    except (TypeError, ValueError):
        return None
    if elapsed != elapsed or avg != avg or cur != cur:
        return None
    if not (elapsed > 0 and avg > 0):
        return None
    expected = avg * (elapsed / TRADING_DAY_MINUTES)
    if not expected > 0:
        return None
    ratio = cur / expected
    if not ratio > 0:
        return None
    return ratio


def resolve_volume_ratio(
    quote: dict | None,
    kline_df=None,
    now: datetime | None = None,
    avg_volume: float | None = None,
) -> float | None:
    """解析一只股票此刻的量比。

    ``avg_volume`` 传入时视为已经算好的 5 日均量（watch 的缓存）；
    否则在给了 ``kline_df`` 时现场从日 K 计算。两者都没有则只认源字段。
    """
    src = quote_volume_ratio(quote)
    if src is not None:
        return src
    if kline_df is None and avg_volume is None:
        return None
    if now is None:
        now = datetime.now()
    avg = prior_avg_volume(kline_df) if avg_volume is None else avg_volume
    cur = (quote or {}).get("volume", 0) if isinstance(quote, dict) else 0
    return intraday_volume_ratio(cur, 0 if avg is None else avg, trading_elapsed_minutes(now))

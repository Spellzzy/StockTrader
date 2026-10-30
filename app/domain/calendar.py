"""交易日历

离线实现：周末 + 可配置的节假日/调休表。
不引入第三方日历库，避免为了拿节假日数据而联网。

节假日需要人工维护（法定节假日每年不同），写在 config.yaml 的 market 段:

    market:
      holidays: ["2026-01-01", "2026-02-16", ...]   # 休市日
      workdays: ["2026-02-14", ...]                 # 周末调休上班（可选）

数据源建议：每年初从交易所公告一次性填好。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable, Optional


def _to_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


class TradingCalendar:
    """交易日历"""

    def __init__(
        self,
        holidays: Iterable = (),
        workdays: Iterable = (),
    ):
        self.holidays = {_to_date(d) for d in holidays or ()}
        self.workdays = {_to_date(d) for d in workdays or ()}

    @classmethod
    def from_config(cls, cfg: Optional[dict] = None) -> "TradingCalendar":
        """从配置构造（market 段）"""
        if cfg is None:
            from app.config import get_config

            cfg = get_config()
        market_cfg = (cfg or {}).get("market", {}) or {}
        return cls(
            holidays=market_cfg.get("holidays") or (),
            workdays=market_cfg.get("workdays") or (),
        )

    def is_weekend(self, day: date) -> bool:
        return day.weekday() >= 5

    def is_trading_day(self, day=None) -> bool:
        """是否交易日

        Args:
            day: date/datetime/字符串，默认今天
        """
        day = _to_date(day) if day is not None else date.today()
        if day in self.workdays:
            return True
        if day in self.holidays:
            return False
        return not self.is_weekend(day)

    def next_trading_day(self, day=None) -> date:
        """下一个交易日（含当天）"""
        day = _to_date(day) if day is not None else date.today()
        for _ in range(15):  # 最长假期也不会超过两周
            if self.is_trading_day(day):
                return day
            day += timedelta(days=1)
        return day

    def previous_trading_day(self, day=None) -> date:
        """上一个交易日（含当天）"""
        day = _to_date(day) if day is not None else date.today()
        for _ in range(15):
            if self.is_trading_day(day):
                return day
            day -= timedelta(days=1)
        return day


_default_calendar: Optional[TradingCalendar] = None


def get_calendar() -> TradingCalendar:
    """获取全局交易日历（懒加载单例）"""
    global _default_calendar
    if _default_calendar is None:
        _default_calendar = TradingCalendar.from_config()
    return _default_calendar


def reset_calendar() -> None:
    """重置日历单例（测试用）"""
    global _default_calendar
    _default_calendar = None

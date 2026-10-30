"""交易日历"""

from datetime import date

from app.domain.calendar import TradingCalendar


def test_weekend_is_not_trading_day():
    cal = TradingCalendar()
    assert cal.is_trading_day(date(2026, 10, 31)) is False  # 周六
    assert cal.is_trading_day(date(2026, 11, 1)) is False   # 周日


def test_weekday_is_trading_day():
    assert TradingCalendar().is_trading_day(date(2026, 10, 30)) is True  # 周五


def test_holiday_overrides_weekday():
    cal = TradingCalendar(holidays=["2026-10-30"])
    assert cal.is_trading_day(date(2026, 10, 30)) is False


def test_workday_overrides_weekend():
    """调休上班的周末按交易日处理"""
    cal = TradingCalendar(workdays=["2026-10-31"])
    assert cal.is_trading_day(date(2026, 10, 31)) is True


def test_next_trading_day_skips_weekend():
    # 2026-10-30 是周五
    assert TradingCalendar().next_trading_day(date(2026, 10, 30)) == date(2026, 10, 30)
    assert TradingCalendar().next_trading_day(date(2026, 10, 31)) == date(2026, 11, 2)


def test_previous_trading_day():
    assert TradingCalendar().previous_trading_day(date(2026, 11, 1)) == date(2026, 10, 30)


def test_next_trading_day_skips_holiday_run():
    cal = TradingCalendar(holidays=["2026-10-30", "2026-11-02"])
    assert cal.next_trading_day(date(2026, 10, 30)) == date(2026, 11, 3)


def test_from_config_reads_market_section():
    cal = TradingCalendar.from_config({"market": {"holidays": ["2026-01-01"]}})
    assert cal.is_trading_day(date(2026, 1, 1)) is False

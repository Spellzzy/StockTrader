"""交易录入：费率自动计算走统一 FeeModel"""

import pytest

from app.services.trade_service import TradeService


def test_buy_has_commission_and_no_stamp_tax(db_session):
    trade = TradeService(session=db_session).add_trade(
        "600519", "buy", 10.0, 10_000, stock_name="测试股份"
    )

    assert trade.stock_code == "sh600519"   # 代码自动补全前缀
    assert trade.market == "A"
    assert trade.amount == pytest.approx(100_000.0)
    assert trade.commission == pytest.approx(30.0)   # 100000 * 万3
    assert trade.tax == 0.0                          # 买入不收印花税


def test_sell_has_stamp_tax(db_session):
    trade = TradeService(session=db_session).add_trade(
        "sh600519", "sell", 12.0, 10_000, stock_name="测试股份"
    )

    assert trade.commission == pytest.approx(36.0)   # 120000 * 万3
    assert trade.tax == pytest.approx(120.0)         # 120000 * 千1


def test_commission_floor_applies(db_session):
    """小额成交按最低 5 元收取"""
    trade = TradeService(session=db_session).add_trade(
        "sh600519", "buy", 1.0, 100, stock_name="测试股份"
    )
    assert trade.commission == pytest.approx(5.0)


def test_manual_fees_are_not_overwritten(db_session):
    trade = TradeService(session=db_session).add_trade(
        "sh600519", "buy", 10.0, 10_000, stock_name="测试股份", commission=1.0
    )
    assert trade.commission == pytest.approx(1.0)

"""持仓重算（由交易记录全量推导）"""

from datetime import datetime

import pytest
from sqlalchemy import select

from app.models.portfolio import PortfolioRecord
from app.models.trade import Trade
from app.services.portfolio_service import PortfolioService


def _trade(code, action, price, quantity, when, commission=0.0, tax=0.0) -> Trade:
    return Trade(
        stock_code=code,
        stock_name="测试股份",
        market="A",
        action=action,
        price=price,
        quantity=quantity,
        amount=price * quantity,
        commission=commission,
        tax=tax,
        trade_time=when,
    )


def _holding(db_session, code="sh600519") -> PortfolioRecord:
    return db_session.execute(
        select(PortfolioRecord).where(PortfolioRecord.stock_code == code)
    ).scalar_one()


def test_weighted_average_cost(db_session):
    db_session.add(_trade("sh600519", "buy", 10.0, 100, datetime(2024, 1, 1)))
    db_session.add(_trade("sh600519", "buy", 12.0, 100, datetime(2024, 1, 2)))
    db_session.commit()

    PortfolioService(session=db_session).rebuild_portfolio()

    holding = _holding(db_session)
    assert holding.quantity == 200
    assert holding.avg_cost == pytest.approx(11.0)
    assert holding.total_cost == pytest.approx(2200.0)
    assert holding.buy_count == 2


def test_realized_profit_on_sell(db_session):
    db_session.add(_trade("sh600519", "buy", 10.0, 100, datetime(2024, 1, 1)))
    db_session.add(_trade("sh600519", "buy", 12.0, 100, datetime(2024, 1, 2)))
    db_session.add(
        _trade("sh600519", "sell", 15.0, 100, datetime(2024, 1, 10), commission=5.0, tax=15.0)
    )
    db_session.commit()

    PortfolioService(session=db_session).rebuild_portfolio()

    holding = _holding(db_session)
    assert holding.quantity == 100
    assert holding.avg_cost == pytest.approx(11.0)
    assert holding.total_cost == pytest.approx(1100.0)
    # (15 - 11) * 100 - 佣金 5 - 印花税 15
    assert holding.realized_profit == pytest.approx(380.0)
    assert holding.sell_count == 1


def test_rebuild_is_idempotent_and_clears_stale(db_session):
    db_session.add(_trade("sh600519", "buy", 10.0, 100, datetime(2024, 1, 1)))
    db_session.commit()

    service = PortfolioService(session=db_session)
    service.rebuild_portfolio()
    service.rebuild_portfolio()
    assert _holding(db_session).quantity == 100

    db_session.query(Trade).delete()
    db_session.commit()
    service.rebuild_portfolio()
    assert service.get_portfolio(include_cleared=True) == []


def test_cost_basis_kept_after_partial_sell(db_session):
    """部分卖出后，剩余持仓的成本价保持不变"""
    db_session.add(_trade("sh600519", "buy", 10.0, 200, datetime(2024, 1, 1)))
    db_session.add(_trade("sh600519", "sell", 12.0, 100, datetime(2024, 1, 5)))
    db_session.commit()

    PortfolioService(session=db_session).rebuild_portfolio()

    holding = _holding(db_session)
    assert holding.quantity == 100
    assert holding.avg_cost == pytest.approx(10.0)
    assert holding.total_cost == pytest.approx(1000.0)
    assert holding.realized_profit == pytest.approx(200.0)

"""持仓手工校正：锁定行不被重建覆盖，解锁后恢复派生值"""

from datetime import datetime

import pytest

from app.services.portfolio_service import PortfolioService


def add_trade(session, code, action, price, quantity, day=1):
    from app.models.trade import Trade

    trade = Trade(
        stock_code=code, stock_name="测试股票", market="A",
        action=action, price=price, quantity=quantity, amount=price * quantity,
        commission=0.0, tax=0.0,
        trade_time=datetime(2026, 1, day, 10, 0),
    )
    session.add(trade)
    session.commit()


@pytest.fixture
def service(db_session, monkeypatch):
    add_trade(db_session, "sh600519", "buy", 10.0, 100, day=1)
    monkeypatch.setattr(
        "app.data.stock_data_client.StockDataClient.quote",
        lambda self, *codes: {},
    )
    svc = PortfolioService(session=db_session)
    svc.rebuild_portfolio()
    return svc


def test_derived_position_is_built_from_trades(service):
    h = service.get_holding("sh600519")
    assert h.quantity == 100
    assert h.avg_cost == pytest.approx(10.0)
    assert h.manual_override is False


def test_update_holding_locks_and_keeps_total_cost_consistent(service):
    result = service.update_holding(
        "sh600519", quantity=500, avg_cost=12.0, reason="补录历史遗漏"
    )

    assert result["manual_override"] is True
    assert "补录历史遗漏" in result["override_note"]
    h = service.get_holding("sh600519")
    assert h.quantity == 500
    assert h.avg_cost == pytest.approx(12.0)
    assert h.total_cost == pytest.approx(6000.0)
    assert h.manual_override is True


def test_rebuild_skips_locked_row(service, db_session):
    service.update_holding("sh600519", quantity=500, avg_cost=12.0, reason="校正")
    add_trade(db_session, "sh600519", "buy", 11.0, 100, day=2)

    service.rebuild_portfolio()

    h = service.get_holding("sh600519")
    assert h.quantity == 500                      # 不是 600，也不是 200
    assert h.avg_cost == pytest.approx(12.0)
    assert h.manual_override is True


def test_unlock_restores_derived_values(service, db_session):
    service.update_holding("sh600519", quantity=500, avg_cost=12.0, reason="校正")
    add_trade(db_session, "sh600519", "buy", 11.0, 100, day=2)

    result = service.unlock_holding("sh600519")

    assert result["restored"]["quantity"] == 200
    assert result["restored"]["avg_cost"] == pytest.approx(10.5)
    assert service.get_holding("sh600519").manual_override is False


def test_force_rebuild_clears_all_manual_overrides(service, db_session):
    service.update_holding("sh600519", quantity=500, avg_cost=12.0, reason="校正")
    add_trade(db_session, "sh600519", "buy", 11.0, 100, day=2)

    service.rebuild_portfolio(force=True)

    h = service.get_holding("sh600519")
    assert h.manual_override is False
    assert h.quantity == 200
    assert h.avg_cost == pytest.approx(10.5)
    assert service.locked_codes() == []


def test_locked_codes_lists_only_locked(service):
    service.update_holding("sh600519", quantity=500, reason="校正")
    assert service.locked_codes() == ["sh600519"]


def test_update_validates_inputs(service):
    with pytest.raises(ValueError, match="不能为负"):
        service.update_holding("sh600519", quantity=-1)
    with pytest.raises(ValueError, match="不能为负"):
        service.update_holding("sh600519", avg_cost=-1.0)
    with pytest.raises(ValueError, match="必须同时提供"):
        service.update_holding("sz000001", quantity=100)


def test_update_can_create_missing_holding(service):
    result = service.update_holding("sz000001", quantity=300, avg_cost=5.0, reason="漏录")

    assert result["created"] is True
    h = service.get_holding("sz000001")
    assert h.quantity == 300 and h.manual_override is True


def test_market_data_view_exposes_lock_flag(service):
    service.update_holding("sh600519", quantity=500, reason="校正")
    holdings = service.get_portfolio_with_market_data()

    assert holdings[0]["manual_override"] is True
    assert "校正" in (holdings[0]["override_note"] or "")

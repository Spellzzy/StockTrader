"""模拟盘：撮合规则与盈亏"""

from datetime import date

import pytest

from app.domain.fees import FeeModel
from app.services.paper_broker import PaperBroker, PaperTradeError


@pytest.fixture
def broker(tmp_path):
    return PaperBroker(
        data_path=str(tmp_path / "paper.json"),
        fee_model=FeeModel(),
        initial_cash=100_000.0,
    )


def test_buy_rounds_to_lot_and_charges_commission(broker):
    order = broker.buy("sh600519", 10.0, quantity=250)

    assert order.quantity == 200          # 不足 1 手的部分被舍去
    assert order.commission == pytest.approx(5.0)   # 2000*万3=0.6 → 最低 5 元
    assert broker.account.cash == pytest.approx(100_000 - 2000 - 5.0)


def test_buy_by_amount(broker):
    order = broker.buy("sh600519", 10.0, amount=5000)
    assert order.quantity == 500


def test_buy_rejects_insufficient_cash(broker):
    with pytest.raises(PaperTradeError):
        broker.buy("sh600519", 1000.0, quantity=10000)


def test_buy_rejects_less_than_one_lot(broker):
    with pytest.raises(PaperTradeError):
        broker.buy("sh600519", 10.0, quantity=10)


def test_sell_realizes_profit_and_stamp_tax(broker):
    broker.buy("sh600519", 10.0, quantity=1000)   # 成本 10000 + 佣金30 = 10030

    order = broker.sell("sh600519", 12.0, trade_date=date(2030, 1, 2))

    assert order.amount == pytest.approx(12_000.0)
    assert order.commission == pytest.approx(5.0)    # 12000*万3=3.6 → 最低 5 元
    assert order.tax == pytest.approx(12.0)          # 12000*千1
    # 成本价 10.0，卖出 1000 股：(12-10)*1000 - 佣金5 - 印花税12
    assert order.realized_profit == pytest.approx(1983.0)
    assert not broker.positions()                    # 全部卖出后不显示持仓


def test_t_plus_1_blocks_same_day_sell(broker):
    broker.buy("sh600519", 10.0, quantity=1000, trade_date=date(2030, 1, 2))

    with pytest.raises(PaperTradeError):
        broker.sell("sh600519", 11.0, trade_date=date(2030, 1, 2))


def test_t_plus_1_can_be_overridden_for_backfill(broker):
    broker.buy("sh600519", 10.0, quantity=1000, trade_date=date(2030, 1, 2))
    order = broker.sell("sh600519", 11.0, trade_date=date(2030, 1, 2), allow_same_day=True)

    assert order.side == "sell"


def test_sell_rejects_oversell(broker):
    broker.buy("sh600519", 10.0, quantity=1000)

    with pytest.raises(PaperTradeError):
        broker.sell("sh600519", 11.0, quantity=2000, trade_date=date(2030, 1, 2))


def test_sell_without_position(broker):
    with pytest.raises(PaperTradeError):
        broker.sell("sh600519", 11.0)


def test_partial_sell_keeps_cost_basis(broker):
    broker.buy("sh600519", 10.0, quantity=1000)
    broker.sell("sh600519", 11.0, quantity=500, trade_date=date(2030, 1, 2))

    position = broker.positions()[0]
    assert position.quantity == 500
    assert position.avg_cost == pytest.approx(10.0)


def test_summary_and_persistence(tmp_path):
    path = tmp_path / "paper.json"
    broker = PaperBroker(data_path=str(path), initial_cash=50_000.0)
    broker.buy("sh600519", 10.0, quantity=1000)

    reloaded = PaperBroker(data_path=str(path))
    assert reloaded.positions()[0].quantity == 1000

    summary = reloaded.summary(prices={"sh600519": 12.0})
    assert summary["market_value"] == pytest.approx(12_000.0)
    assert summary["unrealized_profit"] == pytest.approx(2_000.0)
    assert summary["total_return"] > 0
    assert summary["next_trading_day"]


def test_reset(tmp_path):
    broker = PaperBroker(data_path=str(tmp_path / "p.json"), initial_cash=10_000.0)
    broker.buy("sh600519", 10.0, quantity=100)
    broker.reset(initial_cash=20_000.0)

    assert broker.account.cash == pytest.approx(20_000.0)
    assert broker.orders() == []

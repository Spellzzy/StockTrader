"""执行层验收：状态机 / 风控 / 幂等 / 影子链路 / 纸面回放 / 对账

所有用例都跑在内存 SQLite + MockBroker 上，不连券商、不访问行情、不推送。
"""

from datetime import datetime, timedelta

import pytest

from app.domain.calendar import TradingCalendar
from app.domain.order import (
    InvalidTransition,
    Order,
    OrderSide,
    OrderStatus,
    OrderValidationError,
    RiskLimits,
    can_transition,
    is_trading_session,
    make_client_order_id,
    transition,
)
from app.services.broker import BrokerError, ManualBroker, MockBroker, get_broker
from app.services.order_planner import Signal, plan_orders
from app.services.order_service import OrderRejected, OrderService


def _cfg(enabled=False, **risk):
    return {
        "broker": {"enabled": enabled, "name": "mock", "draft_dir": "./data/orders"},
        "risk": risk,
    }


def _service(db_session, cfg=None, broker=None):
    return OrderService(
        session=db_session,
        broker=broker or MockBroker(),
        cfg=cfg or _cfg(),
        calendar=TradingCalendar(),
    )


def _order(**kwargs) -> Order:
    defaults = dict(
        client_order_id="oid-test",
        code="sh600519",
        side=OrderSide.BUY,
        price=10.0,
        quantity=100,
        strategy="test",
        bar_date="20261104",
    )
    defaults.update(kwargs)
    return Order(**defaults)


# ==================== 状态机 ====================

def test_legal_transitions():
    assert can_transition(OrderStatus.CREATED, OrderStatus.PENDING_REVIEW)
    assert transition(OrderStatus.CREATED, OrderStatus.FILLED) == OrderStatus.FILLED
    assert transition(OrderStatus.UNKNOWN, OrderStatus.FILLED) == OrderStatus.FILLED


def test_illegal_transition_raises():
    with pytest.raises(InvalidTransition):
        transition(OrderStatus.CANCELLED, OrderStatus.FILLED)
    with pytest.raises(InvalidTransition):
        transition(OrderStatus.ARCHIVED, OrderStatus.SUBMITTED)


def test_client_order_id_is_stable_across_calls():
    a = make_client_order_id("sh600519", "buy", "macd_cross", "20261104", 0)
    b = make_client_order_id("sh600519", "buy", "macd_cross", "20261104", 0)
    assert a == b
    assert a != make_client_order_id("sh600519", "sell", "macd_cross", "20261104", 0)


def test_validate_shape_enforces_lot_and_price():
    _order().validate_shape()
    for bad in (dict(quantity=150), dict(price=0), dict(side="hold")):
        with pytest.raises((OrderValidationError, ValueError)):
            _order(**bad).validate_shape()


def test_is_trading_session():
    cal = TradingCalendar()
    assert is_trading_session(datetime(2026, 11, 4, 10, 0), cal)   # 周三盘中
    assert not is_trading_session(datetime(2026, 11, 4, 12, 0), cal)  # 午休
    assert not is_trading_session(datetime(2026, 10, 31, 10, 0), cal)  # 周六


# ==================== 风控 ====================

def test_risk_kill_switch_defaults_off():
    limits = RiskLimits.from_config({"broker": {}, "risk": {}})
    assert limits.enabled is False
    assert limits.require_confirmation is True


def test_risk_static_whitelist_amount_and_session():
    limits = RiskLimits(whitelist=("sz000001",), max_order_amount=1000.0)
    order = _order(code="sh600519", price=20.0, quantity=100)  # 2000 元

    violations = limits.check_static(
        order, now=datetime(2026, 11, 4, 10, 0), calendar=TradingCalendar()
    )
    assert any("白名单" in v for v in violations)
    assert any("单笔金额" in v for v in violations)


def test_risk_static_session_violation():
    limits = RiskLimits()
    violations = limits.check_static(
        _order(), now=datetime(2026, 11, 4, 20, 0), calendar=TradingCalendar()
    )
    assert any("交易时段" in v for v in violations)


def test_risk_portfolio_daily_t1_positions_and_ratio():
    limits = RiskLimits(
        max_daily_amount=1000.0, max_positions=1,
        max_position_ratio=0.1,
    )

    assert any("当日累计" in v for v in limits.check_portfolio(
        _order(price=20.0), positions=[], daily_amount=900.0
    ))
    assert any("持仓" in v for v in limits.check_portfolio(
        _order(), positions=[object()], daily_amount=0.0
    ))
    assert any("T+1" in v for v in limits.check_portfolio(
        _order(side=OrderSide.SELL), positions=[], bought_today=True
    ))
    assert any("单票仓位" in v for v in limits.check_portfolio(
        _order(), positions=[], total_equity=1000.0
    ))


# ==================== 编排 / 纸面回放 ====================

def test_plan_orders_dedupes_and_rounds_lots():
    signals = [
        Signal(code="sh600519", side="buy", price=10.0, strategy="s", bar_date="20261104", quantity=150),
        Signal(code="sh600519", side="buy", price=10.5, strategy="s", bar_date="20261104"),
        Signal(code="sz000001", side="sell", price=5.0, strategy="s", bar_date="20261104"),
        Signal(code="bad", side="hold", price=1.0, strategy="s", bar_date="20261104"),
    ]
    plan = plan_orders(signals, default_quantity=100)

    assert len(plan.orders) == 2
    assert plan.duplicates == 1
    assert len(plan.skipped) == 1
    assert all(o.quantity % 100 == 0 for o in plan.orders)
    assert plan.orders[0].quantity == 100


def test_replay_on_historical_bars_has_no_duplicates(kline_df):
    """纸面回放：历史信号重放后同一根 K 线只产生一笔订单"""
    from app.domain.indicators import FeatureEngine
    from app.services.strategy import get_strategy

    featured = FeatureEngine().build_features(kline_df, dropna=True)
    signaled = get_strategy("macd_cross").generate_signals(featured)

    signals = []
    for _, row in signaled.iterrows():
        if int(row.get("signal", 0)) == 0:
            continue
        signals.append(Signal(
            code="sh600519",
            side="buy" if row["signal"] > 0 else "sell",
            price=float(row["close"]),
            strategy="macd_cross",
            bar_date=str(row["date"])[:10],
        ))

    plan = plan_orders(signals)
    ids = [o.client_order_id for o in plan.orders]

    assert len(ids) == len(set(ids))
    assert all(o.quantity == 100 for o in plan.orders)
    assert all(o.amount <= 50_000 for o in plan.orders)


# ==================== 服务：幂等 / 开关 ====================

def test_create_order_is_idempotent(db_session):
    svc = _service(db_session)
    first, created = svc.create_order("sh600519", "buy", 10.0, 100, strategy="s", bar_date="20261104")
    second, created_again = svc.create_order(
        "sh600519", "buy", 10.0, 100, strategy="s", bar_date="20261104"
    )

    assert created is True and created_again is False
    assert first.client_order_id == second.client_order_id
    assert len(svc.list_orders()) == 1


def test_submit_defaults_to_dry_run(db_session):
    svc = _service(db_session)
    order, _ = svc.create_order("sh600519", "buy", 10.0, 100, strategy="s", bar_date="20261104")

    result = svc.submit(order.client_order_id)

    assert result["dry_run"] is True
    assert result["status"] == OrderStatus.SUBMITTED.value
    assert svc.get(order.client_order_id).dry_run is True


def test_live_submit_rejected_by_kill_switch(db_session):
    svc = _service(db_session, cfg=_cfg(enabled=False))
    order, _ = svc.create_order("sh600519", "buy", 10.0, 100, strategy="s", bar_date="20261104")

    with pytest.raises(OrderRejected, match="kill switch"):
        svc.submit(order.client_order_id, dry_run=False, confirmed=True)

    assert svc.get(order.client_order_id).status == OrderStatus.CREATED


def test_live_submit_requires_confirmation(db_session):
    svc = _service(db_session, cfg=_cfg(enabled=True))
    order, _ = svc.create_order("sh600519", "buy", 10.0, 100, strategy="s", bar_date="20261104")

    with pytest.raises(OrderRejected, match="二次确认"):
        svc.submit(
            order.client_order_id, dry_run=False, confirmed=False,
            now=datetime(2026, 11, 4, 10, 0),
        )


def test_live_submit_blocked_by_risk(db_session):
    svc = _service(db_session, cfg=_cfg(enabled=True, whitelist=["sz000001"]))
    order, _ = svc.create_order("sh600519", "buy", 10.0, 100, strategy="s", bar_date="20261104")

    with pytest.raises(OrderRejected, match="白名单"):
        svc.submit(
            order.client_order_id, dry_run=False, confirmed=True,
            now=datetime(2026, 11, 4, 10, 0),
        )

    assert svc.get(order.client_order_id).status == OrderStatus.REJECTED


def test_unknown_order_is_never_resubmitted(db_session):
    broker = MockBroker()
    svc = _service(db_session, broker=broker)
    order, _ = svc.create_order("sh600519", "buy", 10.0, 100, strategy="s", bar_date="20261104")
    broker.fail_on = order.client_order_id

    result = svc.submit(order.client_order_id, dry_run=True)
    assert result["status"] == OrderStatus.UNKNOWN.value

    before = len(broker.submitted)
    again = svc.submit(order.client_order_id)
    assert again["ok"] is False
    assert "禁止重新提交" in again["reason"]
    assert len(broker.submitted) == before  # 没有再调通道


# ==================== 成交 / 审计 / 对账 ====================

def test_fill_writes_trade_and_audit(db_session):
    svc = _service(db_session)
    order, _ = svc.create_order(
        "sh600519", "buy", 10.0, 100, strategy="s", bar_date="20261104", name="贵州茅台"
    )

    result = svc.fill(order.client_order_id, price=10.5, write_trade=True)

    assert result["status"] == OrderStatus.FILLED.value
    assert result["trade_id"] is not None
    assert svc.get(order.client_order_id).filled_quantity == 100
    events = svc.events(order.client_order_id)
    assert len(events) >= 2  # CREATED + FILLED
    assert svc.reconcile()["ok"] is True


def test_fill_rejects_overfill_and_bad_lot(db_session):
    svc = _service(db_session)
    order, _ = svc.create_order("sh600519", "buy", 10.0, 100, strategy="s", bar_date="20261104")

    with pytest.raises(OrderRejected):
        svc.fill(order.client_order_id, price=10.0, quantity=200)
    with pytest.raises(OrderRejected):
        svc.fill(order.client_order_id, price=10.0, quantity=50)


def test_reconcile_detects_missing_trade(db_session):
    svc = _service(db_session)
    order, _ = svc.create_order("sh600519", "buy", 10.0, 100, strategy="s", bar_date="20261104")
    svc.fill(order.client_order_id, price=10.0, write_trade=False)

    report = svc.reconcile()
    assert report["ok"] is False
    assert order.client_order_id in report["missing_trades"]


def test_cancel_is_terminal(db_session):
    svc = _service(db_session)
    order, _ = svc.create_order("sh600519", "buy", 10.0, 100, strategy="s", bar_date="20261104")

    svc.cancel(order.client_order_id)
    assert svc.get(order.client_order_id).status == OrderStatus.CANCELLED
    with pytest.raises(OrderRejected):
        svc.cancel(order.client_order_id)


def test_expire_stale_drafts(db_session):
    svc = _service(db_session, cfg=_cfg(timeout_minutes=30))
    order, _ = svc.create_order("sh600519", "buy", 10.0, 100, strategy="s", bar_date="20261104")
    svc.submit(order.client_order_id, dry_run=True)
    now = datetime.now() + timedelta(hours=2)

    expired = svc.expire_stale(now=now)
    assert order.client_order_id in expired
    assert svc.get(order.client_order_id).status == OrderStatus.EXPIRED


def test_recover_marks_unknown_without_resubmitting(db_session):
    broker = MockBroker()
    svc = _service(db_session, broker=broker, cfg=_cfg(enabled=True))
    order, _ = svc.create_order("sh600519", "buy", 10.0, 100, strategy="s", bar_date="20261104")
    svc.submit(
        order.client_order_id, dry_run=False, confirmed=True,
        now=datetime(2026, 11, 4, 10, 0),
    )

    # MockBroker 是即时成交的，这里手工把状态改成"已提交未回报"，
    # 模拟进程重启后发现的遗留真实委托
    from app.models.order import OrderRecord

    rec = db_session.query(OrderRecord).filter_by(client_order_id=order.client_order_id).one()
    rec.status = OrderStatus.SUBMITTED.value
    rec.dry_run = False
    rec.submitted_at = datetime.now() - timedelta(hours=2)
    db_session.commit()

    before = len(broker.submitted)
    recovered = svc.recover_on_startup()

    assert order.client_order_id in recovered
    assert svc.get(order.client_order_id).status == OrderStatus.UNKNOWN
    assert len(broker.submitted) == before


# ==================== 通道 ====================

def test_manual_broker_writes_draft_files(tmp_path):
    broker = ManualBroker(draft_dir=str(tmp_path))
    order = _order()

    result = broker.submit(order, dry_run=False)
    assert result.status == OrderStatus.PENDING_REVIEW

    files = broker.render_draft([order], stamp="20261104")
    csv_content = open(files["csv"], encoding="utf-8").read()
    md_content = open(files["markdown"], encoding="utf-8").read()
    assert "sh600519" in csv_content
    assert "仅供参考" in md_content
    assert not open(files["csv"], "rb").read().startswith(b"\xef\xbb\xbf")


def test_unknown_broker_name_raises():
    with pytest.raises(BrokerError):
        get_broker("not-exist", cfg=_cfg())

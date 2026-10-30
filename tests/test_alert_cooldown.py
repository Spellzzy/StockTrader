"""预警冷却与去重"""

from datetime import datetime, timedelta

from sqlalchemy import create_engine, inspect

from app.db.database import ensure_alert_cooldown_column
from app.models.alert import Alert
from app.models.base import Base
from app.services.alert_service import AlertService

NOW = datetime(2024, 1, 1, 12, 0, 0)


def _alert(**kwargs) -> Alert:
    defaults = dict(stock_code="sh600519", condition_type="price_above", is_active=True)
    defaults.update(kwargs)
    return Alert(**defaults)


def test_in_cooldown_when_recently_triggered():
    alert = _alert(cooldown_minutes=30, last_triggered_at=NOW - timedelta(minutes=10))
    assert alert.in_cooldown(NOW) is True


def test_not_in_cooldown_once_window_passed():
    alert = _alert(cooldown_minutes=30, last_triggered_at=NOW - timedelta(minutes=31))
    assert alert.in_cooldown(NOW) is False


def test_never_triggered_is_not_in_cooldown():
    assert _alert(cooldown_minutes=30).in_cooldown(NOW) is False


def test_cooldown_uses_default_when_unset():
    alert = _alert(last_triggered_at=NOW - timedelta(minutes=1))
    assert alert.in_cooldown(NOW, default_minutes=0) is False
    assert alert.in_cooldown(NOW, default_minutes=30) is True


def test_cooldown_column_is_added_idempotently(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'alerts.db'}")
    Base.metadata.create_all(engine)

    ensure_alert_cooldown_column(engine)
    ensure_alert_cooldown_column(engine)  # 重复调用不应报错

    columns = {c["name"] for c in inspect(engine).get_columns("alerts")}
    assert "cooldown_minutes" in columns
    engine.dispose()


def test_select_active_alerts_skips_cooling_down(db_session):
    fresh = _alert()
    cooling = _alert(
        cooldown_minutes=30,
        repeat=True,
        last_triggered_at=datetime.now() - timedelta(minutes=5),
    )
    db_session.add_all([fresh, cooling])
    db_session.commit()

    active = AlertService(session=db_session)._select_active_alerts()
    assert [a.id for a in active] == [fresh.id]


def test_select_active_alerts_keeps_alerts_outside_window(db_session):
    fresh = _alert()
    cooled = _alert(
        cooldown_minutes=30,
        repeat=True,
        last_triggered_at=datetime.now() - timedelta(minutes=45),
    )
    db_session.add_all([fresh, cooled])
    db_session.commit()

    active = AlertService(session=db_session)._select_active_alerts()
    assert {a.id for a in active} == {fresh.id, cooled.id}

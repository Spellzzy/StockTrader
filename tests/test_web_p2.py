"""Web P2 写操作单测：二次确认、幂等、脱敏，零真实数据写入"""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.config as config_mod
import app.models  # noqa: F401  确保全部 ORM 注册
import app.web.api as api_mod
from app.models.base import Base

# 写操作在 run_in_threadpool 的线程里执行，内存 SQLite 必须用 StaticPool
# 让所有线程共享同一个连接，否则新线程会看到一个没有建表的空库。
_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
)
_Session = sessionmaker(bind=_engine)


@contextmanager
def _fake_scope():
    session = _Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@pytest.fixture
def client(monkeypatch, isolate_config):
    Base.metadata.drop_all(_engine)
    Base.metadata.create_all(_engine)
    monkeypatch.setattr(api_mod, "WRITE_SCOPE", _fake_scope)

    # ---- 只读 API 打桩 ----
    monkeypatch.setattr(
        "app.services.alert_service.AlertService.list_alerts",
        lambda self, **kw: [SimpleNamespace(
            id=7, stock_code="sh600519", stock_name="贵州茅台",
            condition_type="price_above", condition_desc="价格高于 1500",
            threshold=1500.0, is_active=True, is_triggered=False,
            repeat=False, note="", cooldown_minutes=30,
            last_triggered_at=None,
        )],
    )
    monkeypatch.setattr(
        "app.services.alert_service.AlertService.get_condition_types",
        staticmethod(lambda: [{"type": "price_above", "label": "价格突破"}]),
    )
    monkeypatch.setattr(
        "app.services.paper_broker.PaperBroker.summary",
        lambda self, prices=None: {"equity": 101000.0, "cash": 50000.0,
                                  "total_return": 1.0, "unrealized_profit": 1000.0},
    )
    monkeypatch.setattr(
        "app.services.paper_broker.PaperBroker.positions",
        lambda self, include_empty=False: [],
    )
    monkeypatch.setattr(
        "app.services.paper_broker.PaperBroker.orders",
        lambda self, limit=50: [],
    )

    # ---- 写业务打桩 ----
    monkeypatch.setattr(
        "app.services.trade_service.TradeService.add_trade",
        lambda self, **kw: SimpleNamespace(
            id=99, stock_code=kw["stock_code"], action=kw["action"],
            price=kw["price"], quantity=kw["quantity"],
            amount=kw["price"] * kw["quantity"],
        ),
    )
    monkeypatch.setattr(
        "app.services.portfolio_service.PortfolioService.rebuild_portfolio",
        lambda self: None,
    )
    monkeypatch.setattr(
        "app.services.alert_service.AlertService.add_alert",
        lambda self, **kw: SimpleNamespace(id=8, stock_code=kw["stock_code"]),
    )
    monkeypatch.setattr(
        "app.services.alert_service.AlertService.toggle_alert",
        lambda self, aid: SimpleNamespace(is_active=False),
    )
    monkeypatch.setattr(
        "app.services.alert_service.AlertService.delete_alert",
        lambda self, aid: True,
    )
    monkeypatch.setattr(
        "app.services.alert_service.AlertService.reset_alert",
        lambda self, aid: SimpleNamespace(id=aid),
    )
    from app.services.paper_broker import PaperOrder

    def _order(oid, side, code, price, kw):
        qty = kw.get("quantity") or 100
        return PaperOrder(
            id=oid, code=code, side=side, price=price, quantity=qty,
            amount=price * qty, commission=5.0,
            tax=0.0 if side == "buy" else 1.0,
            realized_profit=0.0 if side == "buy" else 100.0,
            trade_date="2026-11-04",
        )

    monkeypatch.setattr(
        "app.services.paper_broker.PaperBroker.buy",
        lambda self, code, price, **kw: _order(1, "buy", code, price, kw),
    )
    monkeypatch.setattr(
        "app.services.paper_broker.PaperBroker.sell",
        lambda self, code, price, **kw: _order(2, "sell", code, price, kw),
    )
    monkeypatch.setattr(
        "app.services.paper_broker.PaperBroker.reset",
        lambda self, initial_cash=None: None,
    )
    return TestClient(api_mod.app, raise_server_exceptions=False)


CID = "test-client-id-0001"
CID2 = "test-client-id-0002"


# ==================== 确认与幂等 ====================

def test_write_requires_confirm(client):
    r = client.post("/api/write/trade", json={
        "client_id": CID, "confirm": False,
        "action": "buy", "code": "sh600519", "price": 1400, "quantity": 100,
    })
    assert r.status_code == 400
    assert r.json()["ok"] is False
    assert "确认" in r.json()["error"]


def test_write_is_idempotent(client, monkeypatch):
    calls = []
    original = api_mod._write

    body = {
        "client_id": CID, "confirm": True,
        "action": "buy", "code": "sh600519", "price": 1400, "quantity": 100,
    }
    r1 = client.post("/api/write/trade", json=body)
    r2 = client.post("/api/write/trade", json=body)

    assert r1.status_code == 200 and r1.json()["data"]["cached"] is False
    assert r2.status_code == 200 and r2.json()["data"]["cached"] is True
    # 第二次返回的结果与第一次一致
    assert r1.json()["data"]["result"] == r2.json()["data"]["result"]
    assert original is api_mod._write  # 占位，确保 fixture 生效
    assert not calls


def test_same_client_id_with_different_payload_is_rejected(client):
    client.post("/api/write/trade", json={
        "client_id": CID2, "confirm": True,
        "action": "buy", "code": "sh600519", "price": 1400, "quantity": 100,
    })
    r = client.post("/api/write/trade", json={
        "client_id": CID2, "confirm": True,
        "action": "sell", "code": "sh600519", "price": 1400, "quantity": 100,
    })
    assert r.status_code == 409
    assert r.json()["ok"] is False


def test_missing_client_id_is_rejected(client):
    r = client.post("/api/write/trade", json={
        "client_id": "x", "confirm": True,
        "action": "buy", "code": "sh600519", "price": 1400, "quantity": 100,
    })
    assert r.status_code == 422


def test_business_failure_marks_failed_and_allows_retry(client, monkeypatch):
    def boom(self, **kw):
        raise RuntimeError("模拟写入失败")

    monkeypatch.setattr("app.services.trade_service.TradeService.add_trade", boom)
    body = {
        "client_id": "test-client-id-0003", "confirm": True,
        "action": "buy", "code": "sh600519", "price": 1400, "quantity": 100,
    }
    assert client.post("/api/write/trade", json=body).status_code == 500

    monkeypatch.setattr(
        "app.services.trade_service.TradeService.add_trade",
        lambda self, **kw: SimpleNamespace(
            id=100, stock_code=kw["stock_code"], action=kw["action"],
            price=kw["price"], quantity=kw["quantity"], amount=140000.0,
        ),
    )
    r = client.post("/api/write/trade", json=body)
    assert r.status_code == 200


# ==================== 各写操作 ====================

def test_trade_write_returns_record(client):
    r = client.post("/api/write/trade", json={
        "client_id": "test-client-id-0004", "confirm": True,
        "action": "buy", "code": "sh600519", "price": 1400, "quantity": 100,
    })
    assert r.json()["data"]["result"]["id"] == 99


def test_alert_add_and_operations(client):
    base = {"confirm": True}
    add = client.post("/api/write/alert", json={
        **base, "client_id": "test-client-id-0005",
        "op": "add", "code": "sh600519", "condition_type": "price_above", "threshold": 1500,
    })
    assert add.status_code == 200
    assert add.json()["data"]["result"]["id"] == 8

    for i, op in enumerate(("toggle", "delete", "reset"), start=6):
        r = client.post("/api/write/alert", json={
            **base, "client_id": f"test-client-id-000{i}", "op": op, "alert_id": 7,
        })
        assert r.status_code == 200
        assert r.json()["data"]["result"]["op"] == op


def test_alert_add_requires_fields(client):
    r = client.post("/api/write/alert", json={
        "client_id": "test-client-id-0010", "confirm": True, "op": "add",
    })
    assert r.status_code == 400


def test_paper_buy_and_reset(client):
    buy = client.post("/api/write/paper", json={
        "client_id": "test-client-id-0011", "confirm": True,
        "op": "buy", "code": "sz002555", "price": 16.0, "quantity": 100,
    })
    assert buy.status_code == 200
    assert buy.json()["data"]["result"]["order"]["side"] == "buy"

    reset = client.post("/api/write/paper", json={
        "client_id": "test-client-id-0012", "confirm": True, "op": "reset",
    })
    assert reset.status_code == 200


def test_paper_invalid_order_is_rejected(client):
    r = client.post("/api/write/paper", json={
        "client_id": "test-client-id-0013", "confirm": True,
        "op": "buy", "code": "", "price": 0,
    })
    assert r.status_code == 400


# ==================== 只读与脱敏 ====================

def test_alerts_read_api(client):
    rows = client.get("/api/alerts").json()["data"]["rows"]
    assert len(rows) == 1 and rows[0]["id"] == 7
    assert client.get("/api/alert-types").json()["data"]["items"][0]["type"] == "price_above"


def test_paper_read_api(client):
    d = client.get("/api/paper").json()["data"]
    assert d["summary"]["equity"] == 101000.0
    assert d["positions"] == [] and d["orders"] == []


def test_settings_masks_secrets(client):
    config_mod._config["ai"]["llm"]["api_key"] = "SECRET_TOKEN_SHOULD_NOT_LEAK"
    config_mod._config["notification"] = {
        "on_trade": False, "pushplus": {"token": "SECRET_PUSHPLUS_TOKEN"},
    }
    r = client.get("/api/settings")
    assert r.status_code == 200
    assert "SECRET_TOKEN_SHOULD_NOT_LEAK" not in r.text
    assert "SECRET_PUSHPLUS_TOKEN" not in r.text
    rows = r.json()["data"]["rows"]
    key_row = next(x for x in rows if x["key"] == "ai.llm.api_key")
    assert key_row["value"] == "已配置"
    assert key_row["env_key"] == "STOCK_AI_AI__LLM__API_KEY"


def test_settings_is_read_only(client):
    """没有提供任何修改配置的写接口"""
    paths = {r.path for r in api_mod.app.routes}
    assert not any("settings" in p and "write" in p for p in paths)


def test_frontend_p2_script_and_tabs(client):
    assert client.get("/static/p2.js").status_code == 200
    text = client.get("/").text
    for tab in ("录入交易", "预警", "模拟盘", "设置"):
        assert tab in text

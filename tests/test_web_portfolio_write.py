"""持仓手工校正 Web 接口：确认、幂等、参数校验、强制重建"""

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
import app.web.api as api_mod
from app.models.base import Base

_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
)
_Session = sessionmaker(bind=_engine)


@contextmanager
def _scope():
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
    monkeypatch.setattr(api_mod, "WRITE_SCOPE", _scope)

    monkeypatch.setattr(
        "app.services.portfolio_service.PortfolioService.get_portfolio_with_market_data",
        lambda self, **kw: [{
            "stock_code": "sh600519", "stock_name": "贵州茅台", "quantity": 500,
            "avg_cost": 12.0, "current_price": 1400.0,
            "unrealized_profit": 1000.0, "unrealized_profit_rate": 1.0,
            "manual_override": True, "override_note": "校正留痕", "override_at": None,
        }],
    )
    monkeypatch.setattr(
        "app.services.portfolio_service.PortfolioService.get_total_summary",
        lambda self: {"holding_count": 1, "total_profit": 1000.0},
    )
    monkeypatch.setattr(
        "app.services.portfolio_service.PortfolioService.update_holding",
        lambda self, code, **kw: {
            "stock_code": code, "created": False, "manual_override": True,
            "before": {"quantity": 100}, "after": {"quantity": kw.get("quantity", 100)},
            "override_note": kw.get("reason", ""),
        },
    )
    monkeypatch.setattr(
        "app.services.portfolio_service.PortfolioService.unlock_holding",
        lambda self, code: {"stock_code": code, "restored": {"quantity": 100, "avg_cost": 10.0}},
    )

    rebuild_calls = []

    def fake_rebuild(self, force=False):
        rebuild_calls.append(force)

    monkeypatch.setattr(
        "app.services.portfolio_service.PortfolioService.rebuild_portfolio", fake_rebuild
    )
    api_mod.__dict__["_test_rebuild_calls"] = rebuild_calls
    return TestClient(api_mod.app, raise_server_exceptions=False)


def _body(cid, **kw):
    return {
        "client_id": cid, "confirm": True, "op": "edit",
        "code": "sh600519", "quantity": 500, "avg_cost": 12.0,
        "reason": "补录历史遗漏", **kw,
    }


def test_confirm_required(client):
    r = client.post("/api/write/portfolio", json={
        **_body("pos-client-0001"), "confirm": False,
    })
    assert r.status_code == 400
    assert "确认" in r.json()["error"]


def test_edit_success(client):
    r = client.post("/api/write/portfolio", json=_body("pos-client-0002"))
    assert r.status_code == 200
    result = r.json()["data"]["result"]
    assert result["op"] == "edit"
    assert result["stock_code"] == "sh600519"
    assert result["manual_override"] is True


def test_edit_is_idempotent(client):
    body = _body("pos-client-0003")
    r1 = client.post("/api/write/portfolio", json=body)
    r2 = client.post("/api/write/portfolio", json=body)

    assert r1.json()["data"]["cached"] is False
    assert r2.json()["data"]["cached"] is True
    assert r1.json()["data"]["result"] == r2.json()["data"]["result"]


def test_edit_requires_code(client):
    r = client.post("/api/write/portfolio", json=_body("pos-client-0004", code=""))
    assert r.status_code == 400


def test_edit_requires_at_least_one_field(client):
    r = client.post("/api/write/portfolio", json={
        "client_id": "pos-client-0005", "confirm": True,
        "op": "edit", "code": "sh600519",
    })
    assert r.status_code == 400


def test_negative_quantity_rejected(client):
    r = client.post("/api/write/portfolio", json=_body("pos-client-0006", quantity=-1))
    assert r.status_code == 422


def test_unlock(client):
    r = client.post("/api/write/portfolio", json={
        "client_id": "pos-client-0007", "confirm": True,
        "op": "unlock", "code": "sh600519",
    })
    assert r.status_code == 200
    assert r.json()["data"]["result"]["restored"]["quantity"] == 100


def test_force_rebuild(client):
    r = client.post("/api/write/portfolio", json={
        "client_id": "pos-client-0008", "confirm": True, "op": "rebuild",
    })
    assert r.status_code == 200
    assert r.json()["data"]["result"]["locked_cleared"] is True
    assert api_mod.__dict__["_test_rebuild_calls"] == [True]


def test_invalid_op_rejected(client):
    r = client.post("/api/write/portfolio", json=_body("pos-client-0009", op="delete"))
    assert r.status_code == 422


def test_portfolio_read_exposes_lock_flag(client):
    d = client.get("/api/portfolio").json()["data"]
    assert d["holdings"][0]["manual_override"] is True
    assert d["holdings"][0]["override_note"] == "校正留痕"


def test_frontend_has_edit_controls(client):
    text = client.get("/").text
    for marker in ("pos-edit-box", "pos-confirm", "pos-rebuild",
                   "pos-show-cleared", "pos-add", "pos-code"):
        assert marker in text
    js = client.get("/static/p2.js").text
    for marker in ("include_cleared=", "data-pos=\"clear\"",
                   "openPosEdit(null, 'create')", "op: 'clear'",
                   "pos-show-cleared", "pos-add"):
        assert marker in js, f"p2.js 缺少 {marker}"
    assert client.get("/static/p2.js").status_code == 200


def test_portfolio_read_supports_include_cleared(client, monkeypatch):
    seen = []

    def fake_view(self, **kw):
        seen.append(kw)
        return [{
            "stock_code": "sh600519", "stock_name": "", "quantity": 0,
            "avg_cost": 0.0, "current_price": 0, "unrealized_profit": 0,
            "manual_override": True, "override_note": "", "override_at": None,
            "is_cleared": True,
        }]

    monkeypatch.setattr(
        "app.services.portfolio_service.PortfolioService.get_portfolio_with_market_data",
        fake_view,
    )
    d = client.get("/api/portfolio?include_cleared=true").json()["data"]

    assert d["include_cleared"] is True
    assert d["holdings"][0]["is_cleared"] is True
    assert seen == [{"include_cleared": True}]
    assert client.get("/api/portfolio").json()["data"]["include_cleared"] is False


def test_clear_op(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.portfolio_service.PortfolioService.clear_holding",
        lambda self, code, reason="": {
            "stock_code": code, "cleared": True, "manual_override": True,
        },
    )
    r = client.post("/api/write/portfolio", json={
        "client_id": "pos-client-0010", "confirm": True,
        "op": "clear", "code": "sh600519", "reason": "页面手工清仓",
    })
    assert r.status_code == 200
    assert r.json()["data"]["result"]["cleared"] is True
    assert r.json()["data"]["result"]["op"] == "clear"

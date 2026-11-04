"""Web 自选编辑写接口：二次确认、幂等、新增/移除/改备注"""

from contextlib import contextmanager
from types import SimpleNamespace

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
        "app.services.watchlist_service.WatchlistService.add_watch",
        lambda self, code, note="": SimpleNamespace(code=code, name="贵州茅台"),
    )
    monkeypatch.setattr(
        "app.services.watchlist_service.WatchlistService.remove_watch",
        lambda self, code: True,
    )
    monkeypatch.setattr(
        "app.services.watchlist_service.WatchlistService.update_note",
        lambda self, code, note: True,
    )
    return TestClient(api_mod.app, raise_server_exceptions=False)


def _body(cid, **kw):
    return {"client_id": cid, "confirm": True, "op": "add",
            "code": "sh600519", "note": "长期关注", **kw}


def test_confirm_required(client):
    r = client.post("/api/write/watchlist", json={
        **_body("wl-client-0001"), "confirm": False,
    })
    assert r.status_code == 400
    assert "确认" in r.json()["error"]


def test_add_success(client):
    r = client.post("/api/write/watchlist", json=_body("wl-client-0002"))
    result = r.json()["data"]["result"]
    assert r.status_code == 200
    assert result["op"] == "add"
    assert result["code"] == "sh600519"


def test_add_is_idempotent(client):
    body = _body("wl-client-0003")
    r1 = client.post("/api/write/watchlist", json=body)
    r2 = client.post("/api/write/watchlist", json=body)

    assert r1.json()["data"]["cached"] is False
    assert r2.json()["data"]["cached"] is True
    assert r1.json()["data"]["result"] == r2.json()["data"]["result"]


def test_remove(client):
    r = client.post("/api/write/watchlist", json=_body(
        "wl-client-0004", op="remove",
    ))
    assert r.status_code == 200
    assert r.json()["data"]["result"]["removed"] is True


def test_update_note(client):
    r = client.post("/api/write/watchlist", json=_body(
        "wl-client-0005", op="note", note="等回调再买",
    ))
    assert r.status_code == 200
    assert r.json()["data"]["result"]["updated"] is True


def test_code_required(client):
    r = client.post("/api/write/watchlist", json=_body(
        "wl-client-0006", code="",
    ))
    assert r.status_code == 400


def test_invalid_op_rejected(client):
    r = client.post("/api/write/watchlist", json=_body(
        "wl-client-0007", op="delete-all",
    ))
    assert r.status_code == 422


def test_frontend_wires_watchlist_editor(client):
    html = client.get("/").text
    for marker in ("wl-code", "wl-note", "wl-confirm", "wl-add", "wl-note-save"):
        assert marker in html

    js = client.get("/static/p2.js").text
    for marker in ("/api/write/watchlist", "data-wl=\"note\"",
                   "data-wl=\"remove\"", "wlWrite", "removeWatch"):
        assert marker in js, f"p2.js 缺少 {marker}"

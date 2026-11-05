"""代码 → 名称自动填充：接口与前端接线"""

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
import app.web.api as api_mod
from app.models.base import Base
from app.models.stock import Stock

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
    monkeypatch.setattr("app.db.database.session_scope", _scope)
    return TestClient(api_mod.app, raise_server_exceptions=False)


def test_name_from_local_stock(client):
    with _scope() as s:
        s.add(Stock(code="sh600519", name="贵州茅台", market="A"))
        s.commit()

    d = client.get("/api/stock/name?code=600519").json()["data"]
    assert d == {"code": "sh600519", "name": "贵州茅台", "source": "local"}


def test_name_falls_back_to_quote(client, monkeypatch):
    calls = []

    def fake_quote(self, *codes, **kw):
        calls.append(codes)
        return {"sh600519": {"name": "贵州茅台", "price": 1400.0}}

    monkeypatch.setattr("app.data.stock_data_client.StockDataClient.quote", fake_quote)
    d = client.get("/api/stock/name?code=sh600519").json()["data"]

    assert d["source"] == "quote" and d["name"] == "贵州茅台"
    assert calls == [("sh600519",)]


def test_local_hit_does_not_touch_network(client, monkeypatch):
    with _scope() as s:
        s.add(Stock(code="sh600519", name="贵州茅台", market="A"))
        s.commit()

    def boom(*a, **kw):
        raise AssertionError("本地命中时不应请求行情")

    monkeypatch.setattr("app.data.stock_data_client.StockDataClient.quote", boom)
    d = client.get("/api/stock/name?code=sh600519").json()["data"]
    assert d["source"] == "local"


def test_unknown_code_returns_empty_name(client, monkeypatch):
    monkeypatch.setattr(
        "app.data.stock_data_client.StockDataClient.quote",
        lambda self, *codes, **kw: {},
    )
    d = client.get("/api/stock/name?code=sh600519").json()["data"]
    assert d["name"] == "" and d["source"] == "none"


def test_quote_failure_returns_empty_name(client, monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("行情不可用")

    monkeypatch.setattr("app.data.stock_data_client.StockDataClient.quote", boom)
    d = client.get("/api/stock/name?code=sh600519").json()["data"]
    assert d["name"] == "" and d["source"] == "none"


def test_short_code_rejected(client):
    assert client.get("/api/stock/name?code=abc").status_code == 422


def test_frontend_wires_auto_fill(client):
    p2 = client.get("/static/p2.js").text
    for marker in ("/api/stock/name", "bindNameFill('pos-code', 'pos-name')",
                   "bindNameFill('w-code', 'w-name')", "dataset.autoName",
                   "autoFillName"):
        assert marker in p2, f"p2.js 缺少 {marker}"

    ux = client.get("/static/ux.js").text
    assert "dispatchEvent(new Event('change'" in ux

    html = client.get("/").text
    assert "pos-name" in html and "w-name" in html

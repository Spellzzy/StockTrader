"""个股详情：后端聚合接口 + 前端子页面接线"""

from contextlib import contextmanager

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
import app.web.api as api_mod
from app.models.base import Base
from app.models.portfolio import PortfolioRecord
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


def _kline_df():
    return pd.DataFrame({
        "date": pd.bdate_range("2026-01-01", periods=30),
        "close": [10.0 + i * 0.2 for i in range(30)],
        "open": [10.0 + i * 0.2 for i in range(30)],
        "high": [10.5 + i * 0.2 for i in range(30)],
        "low": [9.5 + i * 0.2 for i in range(30)],
        "volume": [1000 + i for i in range(30)],
    })


@pytest.fixture
def client(monkeypatch):
    Base.metadata.drop_all(_engine)
    Base.metadata.create_all(_engine)
    with _scope() as s:
        s.add(Stock(code="sh600519", name="贵州茅台", market="A",
                    industry="白酒", sector="消费", is_watched=True,
                    watch_note="长期关注"))
        s.add(PortfolioRecord(stock_code="sh600519", stock_name="贵州茅台",
                              market="A", quantity=100, avg_cost=1400.0,
                              total_cost=140000.0, realized_profit=1200.0))
        s.commit()

    monkeypatch.setattr("app.db.database.session_scope", _scope)
    monkeypatch.setattr(
        "app.services.market_service.MarketService.get_quote",
        lambda self, *codes: {"sh600519": {
            "name": "贵州茅台", "price": 1446.44, "change": 3.44,
            "change_percent": 0.24, "open": 1443.0, "high": 1450.0,
            "low": 1438.0, "volume": 12345, "turnover": 0.8, "pe_ratio": 30.2,
        }},
    )
    monkeypatch.setattr(
        "app.services.market_service.MarketService.get_kline_df",
        lambda self, code, **kw: _kline_df(),
    )
    monkeypatch.setattr(
        "app.services.market_service.MarketService.get_profile",
        lambda self, code: {"data": {"name": "贵州茅台", "industry": "白酒"}},
    )
    return TestClient(api_mod.app, raise_server_exceptions=False)


def test_detail_aggregates_all_sources(client):
    d = client.get("/api/stock/detail?code=600519").json()["data"]

    assert d["code"] == "sh600519"          # 自动补全前缀
    assert d["name"] == "贵州茅台"
    assert d["quote"]["price"] == 1446.44
    assert len(d["kline"]) == 30
    assert d["tech"]["ma5"] > d["tech"]["ma20"]   # 递增序列
    assert d["stock"]["is_watched"] is True
    assert d["stock"]["watch_note"] == "长期关注"
    assert d["holding"]["quantity"] == 100
    assert d["holding"]["is_cleared"] is False
    assert d["alert_count"] == 0
    assert d["recent_trades"] == []
    assert d["generated_at"]


def test_detail_tolerates_market_failures(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.market_service.MarketService.get_quote",
        lambda self, *codes: (_ for _ in ()).throw(RuntimeError("行情不可用")),
    )
    monkeypatch.setattr(
        "app.services.market_service.MarketService.get_kline_df",
        lambda self, code, **kw: (_ for _ in ()).throw(RuntimeError("K线不可用")),
    )
    d = client.get("/api/stock/detail?code=sh600519").json()["data"]

    assert d["quote"] == {}
    assert d["kline"] == [] and d["tech"] == {}
    assert d["holding"]["quantity"] == 100   # 本地数据仍然返回


def test_detail_missing_code(client):
    assert client.get("/api/stock/detail").status_code == 422


def test_detail_short_code_rejected(client):
    """过短代码在参数校验阶段就被拦下，不会进到子进程调用"""
    assert client.get("/api/stock/detail?code=???").status_code == 422


def test_profile_endpoint(client):
    d = client.get("/api/stock/profile?code=600519").json()["data"]
    assert d["code"] == "sh600519"
    assert d["profile"]["industry"] == "白酒"


def test_profile_tolerates_failure(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.market_service.MarketService.get_profile",
        lambda self, code: (_ for _ in ()).throw(RuntimeError("不可用")),
    )
    d = client.get("/api/stock/profile?code=sh600519").json()["data"]
    assert "error" in d["profile"]


def test_kline_tech_handles_empty():
    assert api_mod._kline_tech([]) == {}
    assert api_mod._kline_tech([{"close": None}]) == {}


def test_frontend_detail_page_is_wired(client):
    html = client.get("/").text
    for marker in ("stock-detail", "detail-body", "detail-profile", "detail-close"):
        assert marker in html

    order = [html.index("/static/" + n) for n in
             ("app.js", "ux.js", "p1.js", "p2.js", "detail.js")]
    assert order == sorted(order)

    detail_js = client.get("/static/detail.js").text
    for marker in ("/api/stock/detail", "/api/stock/profile",
                   "ST.openStockDetail", "location.hash", "detail-goto-predict"):
        assert marker in detail_js

    ux_js = client.get("/static/ux.js").text
    for marker in ("td.stock-link", "picker-detail", "查看个股详情"):
        assert marker in ux_js

    css = client.get("/static/style.css").text
    assert ".detail-drawer" in css and "td.stock-link" in css

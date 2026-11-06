"""个股详情：后端聚合接口 + 前端子页面接线"""

from contextlib import contextmanager
from datetime import datetime

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
        lambda self, code, *args, **kw: _kline_df(),
    )
    monkeypatch.setattr(
        "app.services.market_service.MarketService.get_profile",
        lambda self, code: {"data": {"name": "贵州茅台", "industry": "白酒"}},
    )
    monkeypatch.setattr(
        "app.services.market_service.MarketService.get_fund_flow",
        lambda self, code, days=10: {
            "code": 0, "data": {"historyFundFlow": {"oneDayKlineList": [
                {"date": "2026-11-02", "mainNetIn": "34807822",
                 "price": "8.83", "avgIn": "-12700391"},
                {"date": "2026-11-03", "mainNetIn": "-97,408,254",
                 "price": "7.95", "avgIn": "-18043123"},
            ]}}
        },
    )
    monkeypatch.setattr(
        "app.services.market_service.MarketService.get_news",
        lambda self, code, page=1, size=20: {
            "code": 0, "data": {"total_num": 9999, "data": [
                {"time": "2026-11-04 15:18:02", "title": "测试新闻标题",
                 "url": "https://example.com/news/1", "src": "智选洞察",
                 "summary": "测试摘要"},
            ]}
        },
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


def test_fund_endpoint_parses_nested_structure(client):
    d = client.get("/api/stock/fund?code=600519&days=10").json()["data"]

    assert d["code"] == "sh600519"
    assert d["days"] == 10
    assert len(d["rows"]) == 2
    assert d["rows"][0]["date"] == "2026-11-02"
    assert d["rows"][0]["main_net_in"] == 34807822.0
    assert d["rows"][1]["main_net_in"] == -97408254.0   # 带逗号也能解析
    assert d["rows"][1]["price"] == 7.95


def test_fund_endpoint_tolerates_failure(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.market_service.MarketService.get_fund_flow",
        lambda self, code, days=10: (_ for _ in ()).throw(RuntimeError("不可用")),
    )
    d = client.get("/api/stock/fund?code=sh600519").json()["data"]
    assert d["rows"] == [] and "不可用" in d["error"]


def test_fund_extractor_supports_flat_list_and_empty():
    rows = api_mod._extract_fund_rows({"data": [
        {"date": "2026-11-01", "main_flow": "1,000", "price": "10"},
    ]})
    assert rows[0]["main_net_in"] == 1000.0
    assert api_mod._extract_fund_rows({}) == []
    assert api_mod._extract_fund_rows({"data": {"todayFundFlow": None}}) == []


def test_news_endpoint(client):
    d = client.get("/api/stock/news?code=600519&size=15").json()["data"]

    assert d["code"] == "sh600519"
    assert d["total"] == 9999
    assert d["rows"][0]["title"] == "测试新闻标题"
    assert d["rows"][0]["url"].startswith("https://")
    assert d["rows"][0]["source"] == "智选洞察"


def test_news_endpoint_tolerates_failure(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.market_service.MarketService.get_news",
        lambda self, code, page=1, size=20: (_ for _ in ()).throw(RuntimeError("不可用")),
    )
    d = client.get("/api/stock/news?code=sh600519").json()["data"]
    assert d["rows"] == [] and "不可用" in d["error"]


def test_news_extractor_handles_empty():
    assert api_mod._extract_news_rows({}) == ([], None)
    assert api_mod._extract_news_rows({"data": {}}) == ([], None)


def test_frontend_detail_panes_are_wired(client):
    detail_js = client.get("/static/detail.js").text
    for marker in ("detail-tab", "switchPane", "/api/stock/fund",
                   "/api/stock/news", "flow-bar", "news-item", "paneLoaded",
                   "candleChart", "maSeries", "kline-period", "kline-adjust",
                   "orderBook", "innerOuter", "total_market_cap",
                   "量比", "放量", "平量", "缩量", "—", "vr-card",
                   "turnover_rate", "最新量 / 均量",
                   "recentVolumeHtml", "vol-mini", "连放", "连缩"):
        assert marker in detail_js, f"detail.js 缺少 {marker}"
    assert "/api/stock/volume" not in detail_js

    css = client.get("/static/style.css").text
    for cls in (".detail-tabs", ".detail-tab", ".flow-bar", ".news-item",
                ".candle-svg", ".book-bar", ".io-bar", ".kline-tools",
                ".vr-card", ".warn", ".turnover-card", ".vol-mini", ".vol-bar"):
        assert cls in css, f"style.css 缺少 {cls}"


def _freeze_at(monkeypatch, hour, minute):
    frozen = datetime(2026, 11, 6, hour, minute, 0)

    class _Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen

    monkeypatch.setattr(api_mod, "datetime", _Clock)


def test_detail_volume_ratio_uses_quote_field(client, monkeypatch):
    """有源字段时直接采用，不拿 5 日回退或 60 日均量倍数顶替。"""
    _freeze_at(monkeypatch, 10, 30)
    monkeypatch.setattr(
        "app.services.market_service.MarketService.get_quote",
        lambda self, *codes: {"sh600519": {
            "price": 10, "volume": 50, "volume_ratio": 2.5, "vol_ratio": 9.9,
            "turnover_rate": 1.2,
        }},
    )
    d = client.get("/api/stock/detail?code=600519").json()["data"]
    assert d.get("volume_ratio") == pytest.approx(2.5)
    assert d["quote"]["volume_ratio"] == 2.5
    assert d["quote"]["turnover_rate"] == 1.2


def test_detail_volume_ratio_uses_vol_ratio_when_primary_missing(client, monkeypatch):
    _freeze_at(monkeypatch, 10, 30)
    monkeypatch.setattr(
        "app.services.market_service.MarketService.get_quote",
        lambda self, *codes: {"sh600519": {
            "price": 10, "volume": 50, "volume_ratio": 0, "vol_ratio": 1.25,
        }},
    )
    d = client.get("/api/stock/detail?code=600519").json()["data"]
    assert d.get("volume_ratio") == pytest.approx(1.25)


def test_detail_volume_ratio_falls_back_like_watch(client, monkeypatch):
    """无源字段：排除当天的最多 5 日均量 × 已过分钟/240。"""
    _freeze_at(monkeypatch, 10, 30)
    calls = []

    def kline(self, code, period="day", count=60, adjust="qfq"):
        calls.append((period, count))
        if count == 6:
            return pd.DataFrame({"volume": [100, 100, 100, 100, 100, 9999]})
        # 60 日序列的「最新/均量」约为 1.x，不能被当成量比
        return _kline_df()

    monkeypatch.setattr("app.services.market_service.MarketService.get_kline_df", kline)
    monkeypatch.setattr(
        "app.services.market_service.MarketService.get_quote",
        lambda self, *codes: {"sh600519": {"price": 10, "volume": 50, "turnover_rate": 0.8}},
    )
    d = client.get("/api/stock/detail?code=600519").json()["data"]

    assert ("day", 6) in calls
    assert d.get("volume_ratio") == pytest.approx(2.0)
    assert "volume_ratio" not in d["quote"]
    vols = _kline_df()["volume"].tolist()
    sixty = vols[-1] / (sum(vols) / len(vols))
    assert d["volume_ratio"] != pytest.approx(sixty)


def test_detail_volume_ratio_missing_is_null(client, monkeypatch):
    """开盘前、或 K 线也没有时，不把量比写成 0。"""
    _freeze_at(monkeypatch, 9, 0)
    monkeypatch.setattr(
        "app.services.market_service.MarketService.get_quote",
        lambda self, *codes: {"sh600519": {"price": 10, "volume": 50, "turnover_rate": 0.3}},
    )
    before_open = client.get("/api/stock/detail?code=600519").json()["data"]
    assert before_open.get("volume_ratio", "MISSING") is None

    _freeze_at(monkeypatch, 10, 30)

    def boom(self, code, period="day", count=60, adjust="qfq"):
        raise RuntimeError("K线不可用")

    monkeypatch.setattr("app.services.market_service.MarketService.get_kline_df", boom)
    monkeypatch.setattr(
        "app.services.market_service.MarketService.get_quote",
        lambda self, *codes: {"sh600519": {"price": 10, "volume": 50}},
    )
    no_kline = client.get("/api/stock/detail?code=600519").json()["data"]
    assert no_kline.get("volume_ratio", "MISSING") is None
    assert no_kline["kline"] == []


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

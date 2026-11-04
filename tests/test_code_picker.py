"""AI 预测快捷下拉：已收藏 + 持仓的数据源"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.web.api as api_mod


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(
        "app.services.watchlist_service.WatchlistService.list_watched",
        lambda self: [
            SimpleNamespace(code="sh600519", name="贵州茅台"),
            SimpleNamespace(code="sz000001", name="平安银行"),
        ],
    )
    monkeypatch.setattr(
        "app.services.portfolio_service.PortfolioService.get_portfolio",
        lambda self, **kw: [
            SimpleNamespace(stock_code="sz000985", stock_name="中煤能源"),
        ],
    )

    def no_network(self, *codes):
        raise AssertionError("代码快捷选择不应请求行情")

    monkeypatch.setattr(
        "app.data.stock_data_client.StockDataClient.quote", no_network
    )
    return TestClient(api_mod.app, raise_server_exceptions=False)


def test_code_picker_returns_both_groups(client):
    d = client.get("/api/code-picker").json()["data"]

    assert [x["code"] for x in d["watchlist"]] == ["sh600519", "sz000001"]
    assert d["watchlist"][0]["name"] == "贵州茅台"
    assert [x["code"] for x in d["holdings"]] == ["sz000985"]
    assert d["holdings"][0]["name"] == "中煤能源"


def test_code_picker_handles_empty_lists(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.watchlist_service.WatchlistService.list_watched",
        lambda self: [],
    )
    monkeypatch.setattr(
        "app.services.portfolio_service.PortfolioService.get_portfolio",
        lambda self, **kw: [],
    )

    d = client.get("/api/code-picker").json()["data"]
    assert d == {"watchlist": [], "holdings": []}


def test_frontend_wires_the_picker(client):
    html = client.get("/").text
    assert "predict-picker" in html
    assert "predict-code" in html

    js = client.get("/static/p1.js").text
    for marker in ("/api/code-picker", "optgroup", "我的自选", "当前持仓",
                   "predict-picker"):
        assert marker in js, f"p1.js 缺少 {marker}"


def test_watchlist_quotes_api(client, monkeypatch):
    rows = [{
        "code": "sh600519", "name": "贵州茅台", "market": "A", "note": "长期关注",
        "price": 1446.44, "change": -33.56, "change_percent": -2.27,
        "open": 1470.0, "high": 1480.6, "low": 1439.0,
    }]
    monkeypatch.setattr(
        "app.services.watchlist_service.WatchlistService.list_watched_with_quote",
        lambda self: rows,
    )

    d = client.get("/api/watchlist/quotes").json()["data"]
    assert d["rows"][0]["code"] == "sh600519"
    assert d["rows"][0]["note"] == "长期关注"
    assert d["generated_at"]


def test_watchlist_quotes_empty(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.watchlist_service.WatchlistService.list_watched_with_quote",
        lambda self: [],
    )
    d = client.get("/api/watchlist/quotes").json()["data"]
    assert d["rows"] == []


def test_frontend_wires_watchlist_table(client):
    html = client.get("/").text
    for marker in ("watchlist-quotes", "watchlist-refresh", "watchlist-time"):
        assert marker in html

    js = client.get("/static/p2.js").text
    for marker in ("/api/watchlist/quotes", "register('market', loadMarket)",
                   "tr[data-code]"):
        assert marker in js, f"p2.js 缺少 {marker}"

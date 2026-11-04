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

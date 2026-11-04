"""Web API 单测：TestClient + mock，零网络、零真实数据写入"""

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import app.web.api as api_mod


@pytest.fixture
def client(monkeypatch):
    """把所有会触网/读真实 DB 的数据块打桩"""
    monkeypatch.setattr(
        "app.services.portfolio_service.PortfolioService.get_total_summary",
        lambda self: {
            "holding_count": 2,
            "total_cost": 100000.0,
            "total_market_value": 90000.0,
            "total_unrealized_profit": -10000.0,
            "total_realized_profit": 0.0,
            "total_profit": -10000.0,
            "holdings": [
                {"stock_code": "sh600519", "stock_name": "贵州茅台", "quantity": 100,
                 "avg_cost": 1400.0, "current_price": 1450.0, "market_value": 145000.0,
                 "unrealized_profit": 5000.0, "unrealized_profit_rate": 3.57},
            ],
        },
    )
    monkeypatch.setattr(
        "app.services.analysis_service.AnalysisService.summary",
        lambda self, *a, **kw: {"total_trades": 12, "win_rate": 41.7},
    )
    monkeypatch.setattr(api_mod, "_alert_count", lambda: 3)
    monkeypatch.setattr(api_mod, "_model_count", lambda: 22)
    monkeypatch.setattr(api_mod, "_report_files", lambda: [
        {"name": "report_20261104.html", "size": 1024, "updated_at": "2026-11-04T10:00:00", "kind": "html"},
    ])

    def fake_quote(self, *codes):
        return {
            code: {"name": "测试" + code, "price": 10.0, "change_percent": 1.5,
                   "change": 0.15, "open": 9.9, "high": 10.2, "low": 9.8}
            for code in codes
        }

    monkeypatch.setattr(
        "app.services.market_service.MarketService.get_quote", fake_quote
    )
    monkeypatch.setattr(
        "app.services.market_service.MarketService.search",
        lambda self, kw: f"搜索结果: {kw}",
    )
    return TestClient(api_mod.app, raise_server_exceptions=False)


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert "version" in r.json()["data"]


def test_overview_aggregates_all_blocks(client):
    d = client.get("/api/overview").json()
    assert d["ok"] is True
    data = d["data"]
    assert data["portfolio"]["total_profit"] == -10000.0
    assert data["analysis"]["total_trades"] == 12
    assert data["alerts_active"] == 3
    assert data["models"] == 22
    assert data["reports"] == 1
    assert data["warnings"] == []


def test_overview_survives_one_failing_block(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.portfolio_service.PortfolioService.get_total_summary",
        lambda self: (_ for _ in ()).throw(RuntimeError("DB 挂了")),
    )
    d = client.get("/api/overview").json()
    assert d["ok"] is True
    assert d["data"]["portfolio"] == {}
    assert "持仓数据不可用" in d["data"]["warnings"]


def test_overview_serializes_numpy_scalars(client, monkeypatch):
    """回归：numpy.int64 / Timestamp 会让 FastAPI 的 Pydantic 序列化 500"""
    import numpy as np

    monkeypatch.setattr(
        "app.services.analysis_service.AnalysisService.summary",
        lambda self, *a, **kw: {
            "total_trades": np.int64(12),
            "win_rate": np.float64(41.7),
        },
    )
    r = client.get("/api/overview")
    assert r.status_code == 200
    assert r.json()["data"]["analysis"]["total_trades"] == 12
    assert r.json()["data"]["analysis"]["win_rate"] == pytest.approx(41.7)


def test_plain_normalizes_common_types():
    import numpy as np

    result = api_mod._plain({
        "n": np.int64(3), "f": np.float64(1.5),
        "t": pd.Timestamp("2026-01-01"),
        "nested": [np.int32(7), None, "ok"],
    })
    assert result["n"] == 3 and result["f"] == 1.5
    assert result["t"].startswith("2026-01-01")
    assert result["nested"] == [7, None, "ok"]


def test_quote_accepts_space_and_comma_forms(client):
    d1 = client.get("/api/quote", params={"codes": "sh600519 sz000001"}).json()
    d2 = client.get("/api/quote", params={"codes": "sh600519,sz000001"}).json()

    assert d1["data"]["codes"] == d2["data"]["codes"] == ["sh600519", "sz000001"]
    assert len(d1["data"]["rows"]) == 2


def test_quote_rejects_empty_codes(client):
    r = client.get("/api/quote", params={"codes": "  "})
    assert r.status_code == 400
    assert r.json()["ok"] is False


def test_kline_serializes_dates_and_nan(client, monkeypatch):
    df = pd.DataFrame({
        "date": pd.bdate_range("2026-01-01", periods=3),
        "close": [10.0, None, 12.0],
        "volume": [100, 200, 300],
    })
    monkeypatch.setattr(
        "app.services.market_service.MarketService.get_kline_df",
        lambda self, *a, **kw: df,
    )
    rows = client.get("/api/kline", params={"code": "sh600519"}).json()["data"]["rows"]

    assert len(rows) == 3
    assert rows[0]["date"] == "2026-01-01"
    assert rows[1]["close"] is None  # NaN 不能出现在 JSON 里


def test_kline_forwards_period_count_adjust(client, monkeypatch):
    seen = {}
    df = pd.DataFrame({
        "date": pd.bdate_range("2026-01-01", periods=2),
        "close": [10.0, 11.0],
    })

    def fake(self, code, **kw):
        seen.update(kw)
        return df

    monkeypatch.setattr(
        "app.services.market_service.MarketService.get_kline_df", fake
    )
    d = client.get("/api/kline", params={
        "code": "sh600519", "period": "week", "count": 60, "adjust": "hfq",
    }).json()["data"]

    assert seen == {"period": "week", "count": 60, "adjust": "hfq"}
    assert d["period"] == "week" and d["adjust"] == "hfq"


def test_kline_rejects_invalid_adjust(client):
    r = client.get("/api/kline", params={"code": "sh600519", "adjust": "bad"})
    assert r.status_code == 422


def test_search(client):
    d = client.get("/api/search", params={"keyword": "茅台"}).json()
    assert d["data"]["result"] == "搜索结果: 茅台"


def test_reports_list(client):
    d = client.get("/api/reports").json()
    assert d["data"]["files"][0]["name"] == "report_20261104.html"


def test_report_path_traversal_is_blocked(client):
    r = client.get("/reports/..%2F..%2Fconfig.yaml")
    assert r.status_code in (400, 404)
    assert r.json()["ok"] is False


def test_report_not_found(client):
    r = client.get("/reports/missing.html")
    assert r.status_code == 404


def test_index_page_contains_three_tabs(client):
    r = client.get("/")
    assert r.status_code == 200
    text = r.text
    for tab in ("总览", "行情", "报告"):
        assert tab in text


def test_static_assets_are_served(client):
    assert client.get("/static/style.css").status_code == 200
    assert client.get("/static/app.js").status_code == 200


def test_unexpected_error_has_unified_shape(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.market_service.MarketService.get_quote",
        lambda self, *codes: (_ for _ in ()).throw(RuntimeError("token=SECRET 内部细节")),
    )
    r = client.get("/api/quote", params={"codes": "sh600519"})
    assert r.status_code == 500
    body = r.json()
    assert body["ok"] is False
    assert "SECRET" not in body["error"]  # 堆栈/细节不回传前端

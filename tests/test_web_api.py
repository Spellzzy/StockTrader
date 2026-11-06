"""Web API 单测：TestClient + mock，零网络、零真实数据写入"""

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import app.web.api as api_mod

_REAL_REPORT_FILES = api_mod._report_files

CREDIBILITY_MD = """# 智能日报 2026-11-06 09:30 (am)

## 可信度
- 行情截止: 2026-11-06 09:25:00
- 置信度: 72.5%（样本 120 日）
- 数据状态: 行情快照已对齐，样本不足项已降权

### 重点关注
贵州茅台 看涨
"""


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


def test_reports_list_includes_html_and_markdown(client, monkeypatch, tmp_path):
    """列表仍同时返回 HTML 账户报告和 Markdown 日报，其它后缀不入列。"""
    (tmp_path / "daily_20261106_am.html").write_text("<html>账户</html>", encoding="utf-8")
    (tmp_path / "digest_20261106_am.md").write_text(CREDIBILITY_MD, encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignore", encoding="utf-8")
    monkeypatch.setattr(api_mod, "DEFAULT_REPORT_DIR", tmp_path)
    monkeypatch.setattr(api_mod, "_report_files", _REAL_REPORT_FILES)

    files = client.get("/api/reports").json()["data"]["files"]
    by_name = {item["name"]: item for item in files}

    assert set(by_name) == {"digest_20261106_am.md", "daily_20261106_am.html"}
    assert by_name["digest_20261106_am.md"]["kind"] == "markdown"
    assert by_name["daily_20261106_am.html"]["kind"] == "html"


def test_report_markdown_content_returns_utf8_body(client, monkeypatch, tmp_path):
    """点击历史 digest_*.md 时，接口原样返回 UTF-8 正文（含可信度卡片）。"""
    name = "digest_20261106_am.md"
    path = tmp_path / name
    path.write_text(CREDIBILITY_MD, encoding="utf-8")
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf")
    monkeypatch.setattr(api_mod, "DEFAULT_REPORT_DIR", tmp_path)

    r = client.get(f"/api/reports/{name}/content")

    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["data"]["name"] == name
    assert body["data"]["content"] == CREDIBILITY_MD
    for line in ("## 可信度", "行情截止: 2026-11-06 09:25:00", "置信度: 72.5%"):
        assert line in body["data"]["content"]


def test_report_content_rejects_non_markdown(client, monkeypatch, tmp_path):
    (tmp_path / "daily_20261106_am.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(api_mod, "DEFAULT_REPORT_DIR", tmp_path)

    r = client.get("/api/reports/daily_20261106_am.html/content")

    assert r.status_code == 400
    assert r.json() == {"ok": False, "error": "只支持读取 Markdown 报告"}


def test_report_content_missing_matches_existing_error(client, monkeypatch, tmp_path):
    monkeypatch.setattr(api_mod, "DEFAULT_REPORT_DIR", tmp_path)

    r = client.get("/api/reports/digest_missing.md/content")

    assert r.status_code == 404
    assert r.json() == {"ok": False, "error": "报告不存在"}


def test_report_content_illegal_name_matches_existing_error(client, monkeypatch, tmp_path):
    monkeypatch.setattr(api_mod, "DEFAULT_REPORT_DIR", tmp_path)
    (tmp_path / "config.yaml").write_text("secret: 1", encoding="utf-8")

    traversal = client.get("/api/reports/..%2F..%2Fconfig.yaml/content")
    bad_suffix = client.get("/api/reports/notes.txt/content")
    hidden = client.get("/api/reports/.secret.md/content")

    assert traversal.status_code in (400, 404)
    assert traversal.json()["ok"] is False
    assert "secret" not in traversal.text
    for r in (bad_suffix, hidden):
        assert r.status_code == 400
        assert r.json() == {"ok": False, "error": "非法文件名"}


def test_open_report_still_serves_html_only(client, monkeypatch, tmp_path):
    (tmp_path / "daily_20261106_am.html").write_text("<html>账户报告</html>", encoding="utf-8")
    (tmp_path / "digest_20261106_am.md").write_text(CREDIBILITY_MD, encoding="utf-8")
    monkeypatch.setattr(api_mod, "DEFAULT_REPORT_DIR", tmp_path)

    html = client.get("/reports/daily_20261106_am.html")
    assert html.status_code == 200
    assert "账户报告" in html.text

    md = client.get("/reports/digest_20261106_am.md")
    assert md.status_code == 400
    assert md.json() == {"ok": False, "error": "只支持打开 HTML 报告"}


def test_reports_list_includes_json_digest(client, monkeypatch, tmp_path):
    payload = {
        "date": "2026-11-06 09:30",
        "slot": "am",
        "total": 1,
        "bullish": [{"code": "sh600519", "name": "茅台", "quality": {"factor": 0.4}}],
        "bearish": [],
        "neutral": [],
    }
    (tmp_path / "digest_20261106_am.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8",
    )
    (tmp_path / "digest_20261106_am.md").write_text(CREDIBILITY_MD, encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignore", encoding="utf-8")
    monkeypatch.setattr(api_mod, "DEFAULT_REPORT_DIR", tmp_path)
    monkeypatch.setattr(api_mod, "_report_files", _REAL_REPORT_FILES)

    files = client.get("/api/reports").json()["data"]["files"]
    by_name = {item["name"]: item for item in files}
    assert by_name["digest_20261106_am.json"]["kind"] == "json"
    assert by_name["digest_20261106_am.md"]["kind"] == "markdown"
    assert "notes.txt" not in by_name


def test_report_json_content_returns_parsed_object(client, monkeypatch, tmp_path):
    payload = {
        "date": "2026-11-06 09:30",
        "slot": "am",
        "total": 1,
        "bullish": [{
            "code": "sh600519",
            "name": "茅台",
            "quality": {"below_baseline": True, "mean_accuracy": 0.27, "factor": 0.4},
        }],
        "bearish": [],
        "neutral": [],
    }
    name = "digest_20261106_am.json"
    (tmp_path / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(api_mod, "DEFAULT_REPORT_DIR", tmp_path)

    r = client.get(f"/api/reports/{name}/content")

    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert isinstance(body["data"], dict)
    assert body["data"]["slot"] == "am"
    assert body["data"]["bullish"][0]["quality"]["factor"] == 0.4
    assert "content" not in body["data"]


def test_report_json_content_rejects_invalid_json(client, monkeypatch, tmp_path):
    (tmp_path / "digest_bad.json").write_text("{", encoding="utf-8")
    monkeypatch.setattr(api_mod, "DEFAULT_REPORT_DIR", tmp_path)

    r = client.get("/api/reports/digest_bad.json/content")

    assert r.status_code == 400
    assert r.json() == {"ok": False, "error": "JSON 无法解析"}


def test_open_report_rejects_json_file(client, monkeypatch, tmp_path):
    (tmp_path / "digest_20261106_am.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(api_mod, "DEFAULT_REPORT_DIR", tmp_path)

    r = client.get("/reports/digest_20261106_am.json")

    assert r.status_code == 400
    assert r.json() == {"ok": False, "error": "只支持打开 HTML 报告"}


def test_overview_today_digest_summary_is_wired(client):
    """总览挂最新 digest JSON：空态、Top 5 行、完整日报跳转都复用现有报告接口。"""
    html = client.get("/").text
    overview = html.split('id="panel-market"', 1)[0]
    for marker in (
        "今日日报",
        'id="today-digest"',
        'id="today-digest-meta"',
        'id="today-digest-open"',
        "查看完整日报",
        'id="cards"',
        'id="holdings"',
        'id="meta-cards"',
    ):
        assert marker in overview, f"总览面板缺少 {marker}"

    js = client.get("/static/app.js").text
    for marker in (
        "function pickLatestDigestFile",
        "function loadTodayDigest",
        "async function openTodayDigestReport",
        "loadTodayDigest()",
        "digestRows(",
        ".slice(0, 5)",
        "^digest_.+\\.json$",
        "暂无结构化日报",
        "日报读取失败",
        "openJsonReport",
        '/api/reports/',
        '.tab[data-tab="reports"]',
        "st.tab",
    ):
        assert marker in js, f"app.js 缺少 {marker}"
    assert 'kind === "json"' in js or "kind === 'json'" in js
    assert "/api/digest" not in js
    assert "digest-run" not in js


def test_reports_page_previews_json_readonly(client):
    """JSON 打开后是结构化预览，不是可编辑编辑器；Markdown 原文路径仍在。"""
    html = client.get("/").text
    assert "只读结构化回放" in html
    js = client.get("/static/app.js").text
    assert "function renderDigestPreview" in js
    assert "async function openJsonReport" in js
    assert "openJsonReport(this.getAttribute('data-json'))" in js
    assert "report-json" in js
    assert "<textarea" not in js
    assert "contenteditable" not in js
    css = client.get("/static/style.css").text
    assert ".report-json" in css
    assert ".badge.json" in css


def test_reports_panel_opens_markdown_inline_and_html_in_new_tab(client):
    """报告页：Markdown 走内容接口并在面板内展示原文；HTML 仍新标签打开。"""
    html = client.get("/").text
    assert 'id="panel-reports"' in html
    assert 'id="report-body"' in html

    js = client.get("/static/app.js").text
    assert "async function loadReports" in js
    assert "async function openMarkdownReport" in js
    assert "/api/reports/" in js and "/content" in js
    assert 'target="_blank"' in js
    assert 'href="${href}"' in js or "target=\"_blank\"" in js
    assert "/reports/" in js
    assert "pre.textContent = String(d.content" in js
    assert "report-body" in js


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

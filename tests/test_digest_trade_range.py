"""智能日报：今日参考区间与买卖参考价的接入、渲染、快照"""

from datetime import datetime

import pytest

from app.domain.report_persist import build_digest_snapshot
from app.services.smart_digest import SmartDigestService

FAKE_FORECAST = {
    "day_range": {"low": 9.5, "high": 10.8},
    "buy_ref": 9.83,
    "sell_ref": 10.48,
    "stop_loss_ref": 9.34,
    "stop_loss_pct": 5.0,
    "price": 10.2,
    "prev_close": 10.0,
    "phase": "intraday",
    "as_of": "20261109103000",
    "basis": {"sample_days": 120},
    "quality": {"range_coverage": 0.62},
}


def _items():
    return [
        {"code": "sh600519", "name": "A", "signal": "看涨", "score": 30.0,
         "confidence": 70.0, "stars": 4, "key_factors": ["MA 多头"]},
        {"code": "sz000001", "name": "B", "signal": "看跌", "score": -20.0,
         "confidence": 65.0, "stars": 2, "key_factors": []},
        {"code": "sh601519", "name": "C", "signal": "震荡", "score": 1.0,
         "confidence": 50.0, "stars": 3, "key_factors": []},
    ]


@pytest.fixture
def patched(monkeypatch, isolate_config):
    isolate_config["digest"] = {
        "trade_range": {"enabled": True, "max_codes": 2}
    }
    calls = []

    def fake_quote(self, *codes):
        calls.append(codes)
        return {c: {"price": 10.2} for c in codes}

    monkeypatch.setattr(
        "app.services.market_service.MarketService.get_quote", fake_quote
    )
    monkeypatch.setattr(
        "app.services.high_forecast_service.HighForecastService.forecast",
        lambda self, code, now=None, quote=None: dict(FAKE_FORECAST),
    )
    return calls


def test_attach_respects_limit_and_batches_quote(patched):
    items = _items()
    SmartDigestService._attach_trade_ranges(items, [x["code"] for x in items])

    # 限量 2：优先看涨 + 看跌，震荡那只不带区间
    with_range = [x for x in items if "trade_range" in x]
    assert len(with_range) == 2
    assert {x["code"] for x in with_range} == {"sh600519", "sz000001"}
    assert with_range[0]["trade_range"] == {
        "low": 9.5, "high": 10.8, "buy": 9.83, "sell": 10.48,
        "stop_loss": 9.34, "stop_loss_pct": 5.0,
        "price": 10.2, "prev_close": 10.0, "phase": "intraday",
        "as_of": "20261109103000", "sample_days": 120,
        "range_coverage": 0.62, "note": "统计参考，非投资建议",
    }
    # 一次批量行情，而不是每只一次
    assert patched == [("sh600519", "sz000001", "sh601519")]


def test_disabled_skips_everything(monkeypatch, isolate_config, patched):
    isolate_config["digest"]["trade_range"]["enabled"] = False
    items = _items()
    SmartDigestService._attach_trade_ranges(items, [x["code"] for x in items])
    assert not any("trade_range" in x for x in items)
    assert patched == []


def test_single_failure_does_not_break_digest(patched, monkeypatch):
    def sometimes_fail(self, code, now=None, quote=None):
        if code == "sh600519":
            raise ValueError("K 线不可用")
        return dict(FAKE_FORECAST)

    monkeypatch.setattr(
        "app.services.high_forecast_service.HighForecastService.forecast",
        sometimes_fail,
    )
    items = _items()
    SmartDigestService._attach_trade_ranges(items, [x["code"] for x in items])
    assert "trade_range" not in items[0]
    assert "trade_range" in items[1]


def _digest(items):
    return {
        "date": "2026-11-09 10:30",
        "total": len(items),
        "bullish": [x for x in items if x["signal"] == "看涨"],
        "bearish": [x for x in items if x["signal"] == "看跌"],
        "neutral": [x for x in items if x["signal"] == "震荡"],
        "llm_reports": {},
        "market_picks": {},
        "summary_text": "",
        "plain_text": "",
    }


def _with_ranges():
    items = _items()
    for item in items:
        item["trade_range"] = {
            "low": 9.5, "high": 10.8, "buy": 9.83, "sell": 10.48,
            "stop_loss": 9.34, "stop_loss_pct": 5.0,
            "sample_days": 120, "range_coverage": 0.62,
        }
    return items


def test_markdown_renders_all_three_sections():
    svc = SmartDigestService()
    text = svc._build_markdown_digest(_digest(_with_ranges()), {})
    assert text.count("📐 今日参考区间") == 3
    assert "买入参考 9.83" in text and "卖出参考 10.48" in text
    assert text.count("低价参考 9.50") == 3
    assert text.count("止损参考 9.34") == 3
    assert "-5.0%" in text
    assert "区间回测覆盖率 62%" in text
    assert "统计参考，非投资建议" in text


def test_old_format_without_stop_loss_omits_line():
    items = _with_ranges()
    for item in items:
        del item["trade_range"]["stop_loss"]
        del item["trade_range"]["stop_loss_pct"]
    text = SmartDigestService()._build_markdown_digest(_digest(items), {})
    assert "今日参考区间" in text
    assert "止损参考" not in text


def test_plain_digest_renders_range():
    svc = SmartDigestService()
    text = svc._build_plain_digest(_digest(_with_ranges()), {})
    assert text.count("📐 今日参考区间") == 3


def test_no_range_renders_nothing():
    svc = SmartDigestService()
    text = svc._build_markdown_digest(_digest(_items()), {})
    assert "今日参考区间" not in text


def test_json_snapshot_keeps_trade_range():
    digest = _digest(_with_ranges())
    snap = build_digest_snapshot(
        digest, slot="am", now=datetime(2026, 11, 9, 10, 30)
    )
    assert snap["bullish"][0]["trade_range"]["buy"] == 9.83
    assert "scan_results" not in snap and "summary_text" not in snap


def test_frontend_wires_trade_range():
    from pathlib import Path

    js = (Path(__file__).resolve().parent.parent / "app/web/static/app.js").read_text(
        encoding="utf-8"
    )
    for marker in ("snap.trade_range", "📐 区间", "统计参考", "今日参考区间",
                   "止损参考", "stop_loss_pct"):
        assert marker in js, f"app.js 缺少 {marker}"

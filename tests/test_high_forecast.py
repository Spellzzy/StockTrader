"""今日目标最高价：统计分位数 / 盘中收敛 / 涨跌停 / 回测质量 / API"""

from datetime import datetime

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import app.web.api as api_mod
from app.services.high_forecast_service import (
    HighForecastService,
    limit_up_pct,
    trading_progress,
)

CONFIG = {
    "lookback": 60,
    "levels": [50, 75, 90],
    "backtest_days": 20,
    "decay_alpha": 0.7,
}


def _kline(n=130, end="2026-11-05", volatility=0.02, include_today=False):
    rng = np.random.default_rng(42)
    dates = pd.bdate_range(end=end, periods=n)
    close = 10.0 + np.cumsum(rng.normal(0, 0.05, n))
    close = np.maximum(close, 5.0)
    high = close * (1 + rng.uniform(0.005, volatility, n))
    low = close * (1 - rng.uniform(0.005, volatility * 0.8, n))
    open_ = close * (1 + rng.normal(0, 0.004, n))
    if include_today:
        dates = list(dates) + [pd.Timestamp("2026-11-06")]
        close = np.append(close, close[-1] * 1.03)
        high = np.append(high, close[-1] * 1.05)
        low = np.append(low, close[-1] * 0.99)
        open_ = np.append(open_, close[-2])
    return pd.DataFrame({
        "date": dates, "open": open_, "close": close,
        "high": high, "low": low, "volume": 100000,
    })


QUOTE = {
    "name": "测试股", "price": 10.5, "prev_close": 10.0, "open": 10.2,
    "high": 10.6, "low": 10.1, "time": "20261106103000",
}


class FakeMarket:
    def __init__(self, df=None, quote=None):
        self.df = df if df is not None else _kline()
        self.quote = quote if quote is not None else dict(QUOTE)

    def get_kline_df(self, code, **kw):
        return self.df

    def get_quote(self, *codes):
        return {codes[0]: dict(self.quote)}


@pytest.fixture
def svc():
    return HighForecastService(market=FakeMarket(), config=CONFIG)


def test_trading_progress():
    assert trading_progress(datetime(2026, 11, 6, 9, 0))[0] == "premarket"
    phase, p = trading_progress(datetime(2026, 11, 6, 10, 30))
    assert phase == "intraday" and 0 < p < 0.5
    assert trading_progress(datetime(2026, 11, 6, 14, 30))[1] > 0.8
    assert trading_progress(datetime(2026, 11, 6, 15, 30))[0] == "closed"


def test_limit_up_pct():
    assert limit_up_pct("sh600519") == 10.0
    assert limit_up_pct("sh688981") == 20.0
    assert limit_up_pct("sz300750") == 20.0
    assert limit_up_pct("bj430047") == 30.0
    assert limit_up_pct("sh600519", "*ST测试") == 5.0
    assert limit_up_pct("hk00700") is None


def test_premarket_returns_monotonic_band(svc):
    d = svc.forecast("600519", now=datetime(2026, 11, 6, 9, 0))

    assert d["code"] == "sh600519" and d["phase"] == "premarket"
    assert d["targets"]["p50"] <= d["targets"]["p75"] <= d["targets"]["p90"]
    assert d["band"] == {"low": d["targets"]["p50"], "high": d["targets"]["p90"]}
    assert d["center"] == d["targets"]["p75"]
    assert d["probabilities"]["p50"] > d["probabilities"]["p90"]
    assert d["basis"]["sample_days"] >= 30
    assert d["quality"]["samples"] > 0


def test_intraday_converges_over_time(svc):
    early = svc.forecast("sh600519", now=datetime(2026, 11, 6, 10, 0))
    late = svc.forecast("sh600519", now=datetime(2026, 11, 6, 14, 30))

    assert early["phase"] == late["phase"] == "intraday"
    assert early["basis"]["decay"] > late["basis"]["decay"]
    assert early["targets"]["p90"] >= late["targets"]["p90"]
    # 盘中目标不能低于当天已经出现的高点
    assert late["targets"]["p90"] >= late["realized_high"]
    assert late["targets"]["p50"] >= late["realized_high"] - 1e-6


def test_closed_shows_realized_high(svc):
    d = svc.forecast("sh600519", now=datetime(2026, 11, 6, 15, 30))

    assert d["phase"] == "closed"
    assert all(abs(v - d["realized_high"]) < 1e-6 for v in d["targets"].values())
    assert all(v == 0 for v in d["probabilities"].values())


def test_limit_up_clamps_target(svc):
    # 制造高波动历史，让 P90 远超 10% 涨停
    market = FakeMarket(df=_kline(volatility=0.2))
    d = HighForecastService(market=market, config=CONFIG).forecast(
        "sh600519", now=datetime(2026, 11, 6, 9, 0)
    )
    assert d["targets"]["p90"] <= d["basis"]["limit_price"] + 1e-6


def test_creative_board_uses_20pct_cap():
    market = FakeMarket(df=_kline(volatility=0.2))
    d = HighForecastService(market=market, config=CONFIG).forecast(
        "sh688981", now=datetime(2026, 11, 6, 9, 0)
    )
    assert d["basis"]["limit_pct"] == 20.0


def test_today_kline_excluded_from_history(svc):
    with_today = HighForecastService(
        market=FakeMarket(df=_kline(include_today=True)), config=CONFIG
    )
    without = HighForecastService(
        market=FakeMarket(df=_kline()), config=CONFIG
    )
    a = with_today.forecast("sh600519", now=datetime(2026, 11, 6, 9, 0))
    b = without.forecast("sh600519", now=datetime(2026, 11, 6, 9, 0))

    # 当日 K 线被剔除，样本与分位数一致，不含未来信息
    assert a["basis"]["sample_days"] == b["basis"]["sample_days"]


def test_quote_from_previous_day_is_treated_as_closed(svc):
    market = FakeMarket(quote={**QUOTE, "time": "20261105103000"})
    d = HighForecastService(market=market, config=CONFIG).forecast(
        "sh600519", now=datetime(2026, 11, 6, 10, 30)
    )
    assert d["phase"] == "closed"


def test_index_rejected(svc):
    with pytest.raises(ValueError, match="指数"):
        svc.forecast("sh000001")


def test_insufficient_samples():
    tiny = _kline()[:10]
    with pytest.raises(ValueError, match="K 线不足"):
        HighForecastService(market=FakeMarket(df=tiny), config=CONFIG).forecast("sh600519")


def test_no_quote_falls_back_to_premarket():
    market = FakeMarket(quote={})
    d = HighForecastService(market=market, config=CONFIG).forecast(
        "sh600519", now=datetime(2026, 11, 6, 14, 0)
    )
    assert d["phase"] == "premarket" and d["price"] == 0


def test_day_range_and_reference_prices(svc):
    d = svc.forecast("sh600519", now=datetime(2026, 11, 6, 9, 0))
    r = d["day_range"]
    assert r["low"] < d["buy_ref"] < d["sell_ref"] < r["high"]
    assert d["basis"]["down_p25_pct"] is not None
    assert d["basis"]["limit_down"] is not None
    assert 0 <= d["quality"]["range_coverage"] <= 1
    assert "非投资建议" in d["note"]


def test_low_and_stop_loss_reference(svc):
    d = svc.forecast("sh600519", now=datetime(2026, 11, 6, 9, 0))
    assert d["low_ref"] == d["day_range"]["low"]
    assert d["stop_loss_ref"] < d["buy_ref"]
    assert d["stop_loss_ref"] >= d["basis"]["limit_down"] - 1e-6
    assert 0 <= d["stop_loss_pct"] <= 5.0 + 1e-6
    assert d["basis"]["stop_loss_target_pct"] == 5.0


def test_stop_loss_pct_is_configurable():
    cfg = dict(CONFIG, stop_loss_pct=8.0)
    d = HighForecastService(market=FakeMarket(), config=cfg).forecast(
        "sh600519", now=datetime(2026, 11, 6, 9, 0)
    )
    assert d["basis"]["stop_loss_target_pct"] == 8.0
    assert abs(d["stop_loss_pct"] - 8.0) < 0.05   # 未触及跌停 clamp


def test_stop_loss_clamped_to_limit_down():
    cfg = dict(CONFIG, stop_loss_pct=50.0)
    d = HighForecastService(market=FakeMarket(), config=cfg).forecast(
        "sh600519", now=datetime(2026, 11, 6, 9, 0)
    )
    assert d["stop_loss_ref"] >= d["basis"]["limit_down"] - 1e-6
    # clamp 后如实标注实际亏损，而不是虚标 -50%
    assert d["stop_loss_pct"] < 50.0


def test_intraday_reference_prices_stay_actionable(svc):
    d = svc.forecast("sh600519", now=datetime(2026, 11, 6, 10, 30))
    assert d["buy_ref"] <= QUOTE["price"] + 1e-6
    assert d["sell_ref"] >= QUOTE["price"] - 1e-6
    assert d["buy_ref"] <= d["sell_ref"]


def test_intraday_range_uses_realized_low(svc):
    d = svc.forecast("sh600519", now=datetime(2026, 11, 6, 10, 30))
    assert d["day_range"]["low"] == round(QUOTE["low"], 3)


def test_closed_range_shows_realized_day(svc):
    d = svc.forecast("sh600519", now=datetime(2026, 11, 6, 15, 30))
    assert d["day_range"]["low"] == round(QUOTE["low"], 3)
    assert d["day_range"]["high"] == round(max(QUOTE["high"], QUOTE["price"]), 3)


def test_injected_quote_avoids_extra_request():
    class CountingMarket(FakeMarket):
        def __init__(self):
            super().__init__()
            self.quote_calls = 0

        def get_quote(self, *codes):
            self.quote_calls += 1
            return super().get_quote(*codes)

    market = CountingMarket()
    service = HighForecastService(market=market, config=CONFIG)
    service.forecast("sh600519", quote=dict(QUOTE))
    assert market.quote_calls == 0


def test_range_low_clamped_to_limit_down():
    market = FakeMarket(df=_kline(volatility=0.25))
    d = HighForecastService(market=market, config=CONFIG).forecast(
        "sh600519", now=datetime(2026, 11, 6, 9, 0)
    )
    assert d["day_range"]["low"] >= d["basis"]["limit_down"] - 1e-6


def test_quality_report_has_baseline_comparison(svc):
    q = svc.forecast("sh600519", now=datetime(2026, 11, 6, 9, 0))["quality"]
    for key in ("samples", "touch_p50", "touch_p75", "touch_p90",
                "mae_pct", "baseline_mae_pct", "coverage", "better_than_baseline"):
        assert key in q
    assert 0 <= q["touch_p50"] <= 1
    assert 0 <= q["coverage"] <= 1


# ==================== API / 前端 ====================

@pytest.fixture
def client():
    return TestClient(api_mod.app, raise_server_exceptions=False)


def test_api_forecast(client, monkeypatch):
    payload = {"code": "sh600519", "phase": "premarket", "targets": {"p75": 10.8}}
    monkeypatch.setattr(
        "app.services.high_forecast_service.HighForecastService.forecast",
        lambda self, code: payload,
    )
    d = client.get("/api/forecast/high?code=600519").json()
    assert d["ok"] is True and d["data"]["phase"] == "premarket"


def test_api_invalid_code(client):
    r = client.get("/api/forecast/high?code=!!!")
    assert r.status_code == 422


def test_api_index_returns_400(client, monkeypatch):
    def boom(self, code):
        raise ValueError("指数不适用个股目标高点预测")

    monkeypatch.setattr(
        "app.services.high_forecast_service.HighForecastService.forecast", boom
    )
    r = client.get("/api/forecast/high?code=sh000001")
    assert r.status_code == 400 and "指数" in r.json()["error"]


def test_frontend_wires_forecast(client):
    html = client.get("/").text
    assert "high-forecast" in html and "high-refresh" in html

    js = client.get("/static/p1.js").text
    for marker in ("/api/forecast/high", "loadHighForecast", "PHASE_LABEL",
                   "better_than_baseline", "touch_p75",
                   "syncHighForecast", "el.dataset.code",
                   "input.dispatchEvent(new Event('change'", "esc(d.code)",
                   "ref-prices", "低价参考", "止损参考", "low_ref",
                   "stop_loss_ref", "跌停下限"):
        assert marker in js, f"p1.js 缺少 {marker}"

    css = client.get("/static/style.css").text
    assert ".ref-prices" in css and ".ref-stop" in css


def test_cli_command_registered():
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    cli = (root / "app/cli.py").read_text(encoding="utf-8")
    index = (root / "app/commands/index.py").read_text(encoding="utf-8")
    assert "register_forecast_commands(app)" in cli
    assert "target-high" in index

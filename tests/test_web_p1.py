"""Web P1 API 单测：统计 / 回测 / 策略实验室 / AI 预测 / 交易持仓

所有会触网或跑长任务的 service 都打桩，零网络、零真实数据写入。
"""

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import app.web.api as api_mod
from app.services.backtest_service import BacktestResult


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(
        "app.services.analysis_service.AnalysisService.summary",
        lambda self, *a, **kw: {"total_trades": 12, "win_rate": 41.7, "profit_loss_ratio": 1.2},
    )
    monkeypatch.setattr(
        "app.services.analysis_service.AnalysisService.monthly_summary",
        lambda self, *a, **kw: pd.DataFrame({
            "month": ["2026-01", "2026-02"], "trade_count": [2, 3],
            "total_profit": [100.0, -50.0], "win_rate": [50.0, 33.3],
        }),
    )
    monkeypatch.setattr(
        "app.services.analysis_service.AnalysisService.stock_pnl_ranking",
        lambda self, *a, **kw: pd.DataFrame({
            "stock_code": ["sh600519"], "trades": [3],
            "profit": [1200.0], "win_rate": [66.7],
        }),
    )
    monkeypatch.setattr(
        "app.services.analysis_service.AnalysisService.max_drawdown",
        lambda self, *a, **kw: {"max_drawdown": 5000.0, "max_drawdown_rate": 12.5},
    )
    monkeypatch.setattr(
        "app.services.analysis_service.AnalysisService.get_trades_df",
        lambda self, *a, **kw: pd.DataFrame({
            "trade_time": pd.to_datetime(["2026-01-01", "2026-02-01"]),
            "stock_code": ["sh600519", "sz000001"], "action": ["buy", "sell"],
            "price": [1400.0, 12.0], "quantity": [100, 500],
            "profit": [None, 300.0], "strategy": ["manual", ""],
        }),
    )
    monkeypatch.setattr(
        "app.services.portfolio_service.PortfolioService.get_portfolio_with_market_data",
        lambda self, **kw: [{"stock_code": "sh600519", "stock_name": "贵州茅台",
                       "quantity": 100, "avg_cost": 1400.0,
                       "current_price": 1450.0, "unrealized_profit": 5000.0}],
    )
    monkeypatch.setattr(
        "app.services.portfolio_service.PortfolioService.get_total_summary",
        lambda self: {"holding_count": 1, "total_profit": 5000.0},
    )

    def fake_run(self, code, strategy="macd_cross", days=180, **kw):
        r = BacktestResult(code=code, strategy_name=strategy)
        r.total_return = -12.25 if strategy == "ma_cross" else -21.03
        r.total_trades = 4
        r.win_rate = 25.0
        r.max_drawdown = 16.0
        r.sharpe_ratio = -1.2
        r.net_profit = -12250.0
        r.equity_curve = pd.DataFrame({
            "date": pd.bdate_range("2026-01-01", periods=3),
            "equity": [100000.0, 98000.0, 87750.0],
        })
        return r

    monkeypatch.setattr("app.services.backtest_service.BacktestService.run", fake_run)
    monkeypatch.setattr(
        "app.services.backtest_service.BacktestService.run_portfolio",
        lambda self, codes, **kw: {
            "codes": codes, "strategy": kw.get("strategy", ""),
            "total_return": -15.0, "max_drawdown": 20.0,
            "equity_curve": pd.DataFrame({"date": ["2026-01-01"], "equity": [85000.0]}),
            "details": [fake_run(self, c) for c in codes],
        },
    )
    monkeypatch.setattr(
        "app.services.strategy_lab.StrategyLab.analyze_all",
        lambda self, code, days=250, horizon=5: [
            {"strategy": "macd_cross", "hit_rate": 55.0, "decay": 7.1, "total_signals": 20},
        ],
    )
    monkeypatch.setattr(
        "app.services.strategy_lab.StrategyLab.grid_search",
        lambda self, code, strategy, days=180, max_combos=8: {
            "code": code, "strategy": strategy, "combos": 2,
            "rows": [{"params": {"short": 5, "long": 20}, "total_return": -12.0,
                      "max_drawdown": 16.0, "sharpe_ratio": -1.0, "total_trades": 4}],
        },
    )
    monkeypatch.setattr(
        "app.services.strategy_lab.StrategyLab.walk_forward",
        lambda self, code, strategy, days=250, n_splits=3, max_combos=8: {
            "folds": [], "mean_test_hit_rate": None, "decay": None,
            "reliable_folds": 0, "total_folds": 3,
            "conclusion": "样本外信号不足，无法判断是否存在过拟合，请拉长回测区间",
        },
    )
    monkeypatch.setattr(
        "app.ai.predictor_service.PredictorService.predict",
        lambda self, code, use_dl=False, auto_train=False: {
            "code": code,
            "combined": {"signal": "震荡", "score": 0.0, "stars": 2,
                         "confidence": 41.4, "key_factors": ["RSI 超卖"],
                         "quality": {"below_baseline": True, "mean_accuracy": 0.273,
                                     "baseline": 0.3333, "note": "模型无预测能力"}},
            "ml_xgb": {"signal": "震荡", "confidence": 59.4, "model_accuracy": 0.28,
                       "indicators": {"rsi6": 24.2}},
        },
    )
    return TestClient(api_mod.app, raise_server_exceptions=False)


# ==================== 统计 / 交易持仓 ====================

def test_analysis_endpoints(client):
    assert client.get("/api/analysis/summary").json()["data"]["total_trades"] == 12
    assert len(client.get("/api/analysis/monthly").json()["data"]["rows"]) == 2
    assert client.get("/api/analysis/ranking").json()["data"]["rows"][0]["stock_code"] == "sh600519"
    assert client.get("/api/analysis/drawdown").json()["data"]["max_drawdown_rate"] == 12.5


def test_trades_returns_newest_first_with_null_profit(client):
    rows = client.get("/api/trades?limit=10").json()["data"]["rows"]
    assert rows[0]["stock_code"] == "sz000001"  # 倒序
    assert rows[1]["profit"] is None  # NaN → None


def test_portfolio(client):
    d = client.get("/api/portfolio").json()["data"]
    assert len(d["holdings"]) == 1
    assert d["summary"]["holding_count"] == 1


def test_strategies_list(client):
    items = client.get("/api/strategies").json()["data"]["items"]
    assert len(items) == 7
    assert all("name" in x and "description" in x for x in items)


# ==================== 回测 ====================

def test_backtest_run_returns_curve_and_trades(client):
    d = client.post("/api/backtest/run", json={"code": "sz002555"}).json()["data"]
    assert d["total_return"] == -21.03
    assert len(d["equity_curve"]) == 3
    assert d["equity_curve"][0]["date"] == "2026-01-01"
    assert "trades" in d


def test_backtest_compare_is_ranked(client):
    rows = client.post("/api/backtest/compare", json={"code": "sz002555"}).json()["data"]["rows"]
    assert len(rows) == 7
    assert rows[0]["strategy_name"] == "ma_cross"  # -12.25 > -21.03


def test_backtest_compare_accepts_explicit_strategy_list(client):
    rows = client.post("/api/backtest/compare", json={
        "code": "sz002555", "strategies": ["rsi", "ma_cross"],
    }).json()["data"]["rows"]
    assert len(rows) == 2


def test_backtest_portfolio_serializes_dataframes(client):
    d = client.post("/api/backtest/portfolio", json={
        "codes": "sh600519,sz000001",
    }).json()["data"]
    assert len(d["codes"]) == 2
    assert len(d["equity_curve"]) == 1
    assert len(d["details"]) == 2
    assert "equity" not in str(d["details"])


def test_backtest_portfolio_rejects_empty_codes(client):
    r = client.post("/api/backtest/portfolio", json={"codes": [""]})
    assert r.status_code == 400
    assert r.json()["ok"] is False


def test_backtest_param_validation(client):
    r = client.post("/api/backtest/run", json={"code": "x", "days": 5})
    assert r.status_code == 422
    assert r.json()["ok"] is False


# ==================== 策略实验室 / 预测 ====================

def test_lab_signals(client):
    rows = client.get("/api/lab/signals", params={"code": "sz002555"}).json()["data"]["rows"]
    assert rows[0]["strategy"] == "macd_cross"


def test_lab_optimize(client):
    d = client.post("/api/lab/optimize", json={"code": "sz002555"}).json()["data"]
    assert d["grid"]["rows"][0]["params"] == {"short": 5, "long": 20}
    assert "样本外信号不足" in d["walk_forward"]["conclusion"]


def test_predict_never_auto_trains(client, monkeypatch):
    seen = {}

    def spy(self, code, use_dl=False, auto_train=False):
        seen.update(use_dl=use_dl, auto_train=auto_train)
        return {"code": code, "combined": {"signal": "震荡", "stars": 1}}

    monkeypatch.setattr("app.ai.predictor_service.PredictorService.predict", spy)
    client.get("/api/predict", params={"code": "sz002555", "dl": "true"})

    assert seen == {"use_dl": True, "auto_train": False}


def test_predict_quality_gate_is_exposed(client):
    d = client.get("/api/predict", params={"code": "sz002555"}).json()["data"]
    assert d["combined"]["quality"]["below_baseline"] is True
    assert d["combined"]["stars"] <= 2


def test_frontend_p1_script_is_served(client):
    assert client.get("/static/p1.js").status_code == 200
    text = client.get("/").text
    for tab in ("统计", "回测", "策略实验室", "AI 预测", "交易持仓"):
        assert tab in text

"""落盘模型必须在全量数据上重训

留出集只用来报准确率；如果直接把只看了前 80% 数据的模型存下来，
最近 20%（约半年）的行情就被白白浪费了。
"""

import numpy as np
import pandas as pd

from app.ai.ml_predictor import MLPredictor


def _make_data(n=400, seed=0):
    rng = np.random.default_rng(seed)
    close = 10 + np.cumsum(rng.normal(0, 0.1, n))
    return pd.DataFrame(
        {
            "date": pd.bdate_range("2024-01-01", periods=n),
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": rng.integers(1e5, 1e6, n),
        }
    )


def _prepare_like_real(df):
    """模拟 _prepare_data：算指标 + 打标签"""
    from app.domain.indicators import FeatureEngine

    engine = FeatureEngine()
    out = engine.build_features(df, dropna=True)
    return FeatureEngine.add_label_classification(out, horizon=5, threshold=2.0)


class _Recorder:
    """记录 save_ml_model 的入参"""

    def __init__(self):
        self.saved = {}

    def save_ml_model(self, model, code, model_type="xgb", meta=None):
        self.saved[model_type] = {"model": model, "meta": meta or {}}
        return f"/tmp/{code}_{model_type}.joblib"

    def load_ml_model(self, code, model_type="xgb"):
        return self.saved.get(model_type)

    @staticmethod
    def is_expired(payload):
        return False


def test_saved_model_is_fitted_on_full_data(monkeypatch):
    df = _prepare_like_real(_make_data())
    monkeypatch.setattr(MLPredictor, "_prepare_data", lambda self, *a, **kw: df)

    predictor = MLPredictor()
    recorder = _Recorder()
    predictor.model_manager = recorder

    result = predictor.train("sh600519")

    assert result is not None
    assert "rf" in result

    meta = recorder.saved["rf"]["meta"]
    assert meta["fitted_on"] == "full"
    assert meta["train_size"] == len(df)          # 全量，不是 80%
    assert meta["test_size"] < len(df)            # 准确率仍来自留出集
    # 训练区间要覆盖到最新一根 K 线
    assert meta["train_end"] >= str(df["date"].iloc[-1])[:10]
    # 留出集区间另存，用于追溯准确率是怎么来的
    assert meta["holdout_train_end"] <= meta["train_end"]


def test_reported_accuracy_still_comes_from_holdout(monkeypatch):
    df = _prepare_like_real(_make_data())
    monkeypatch.setattr(MLPredictor, "_prepare_data", lambda self, *a, **kw: df)

    predictor = MLPredictor()
    recorder = _Recorder()
    predictor.model_manager = recorder

    result = predictor.train("sh600519")

    rf_meta_acc = recorder.saved["rf"]["meta"]["accuracy"]
    assert rf_meta_acc == result["rf"]["accuracy"]

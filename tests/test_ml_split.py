"""ML/DL 时序切分与训练行为"""

from datetime import datetime, timedelta

import pytest

from app.ai.ml_predictor import MLPredictor
from app.ai.model_manager import ModelManager
from app.ai.split import time_split_indices


def test_split_without_gap():
    train, test = time_split_indices(100, 0.2, 0)
    assert (train.start, train.stop) == (0, 80)
    assert (test.start, test.stop) == (80, 100)


def test_split_with_gap_purges_train_tail_and_embargoes_test_head():
    """标签用了未来 horizon 天的收益，切分点两侧各留 horizon 的间隔"""
    train, test = time_split_indices(100, 0.2, 5)
    assert (train.start, train.stop) == (0, 75)
    assert (test.start, test.stop) == (85, 100)


def test_split_never_overlaps():
    train, test = time_split_indices(500, 0.25, 10)
    assert train.stop <= test.start


def test_split_falls_back_when_data_too_small():
    train, test = time_split_indices(20, 0.2, 5)
    assert train.stop <= test.start
    assert test.stop == 20
    assert test.start < test.stop


def test_walk_forward_returns_one_score_per_fold(kline_df, monkeypatch):
    from app.ai.feature_engine import FeatureEngine

    df = FeatureEngine.add_label_classification(
        FeatureEngine().build_features(kline_df), horizon=5, threshold=2.0
    )
    predictor = MLPredictor()
    monkeypatch.setattr(MLPredictor, "_prepare_data", lambda self, *a, **k: df)

    result = predictor.walk_forward("sh600519", n_splits=3)

    assert result is not None
    assert len(result["folds"]) == 3
    assert 0.0 <= result["mean_accuracy"] <= 1.0
    assert all(f["test_size"] > 0 for f in result["folds"])


def test_predict_does_not_train_silently(monkeypatch):
    """扫描大量股票时，缺模型不应该触发隐式训练"""
    predictor = MLPredictor()
    monkeypatch.setattr(predictor.model_manager, "load_ml_model", lambda *a, **k: None)

    trained = []
    monkeypatch.setattr(predictor, "train", lambda *a, **k: trained.append(True))

    assert predictor.predict("sh600519") is None
    assert trained == []


def test_predict_can_train_when_explicitly_allowed(monkeypatch):
    predictor = MLPredictor()
    monkeypatch.setattr(predictor.model_manager, "load_ml_model", lambda *a, **k: None)

    calls = []
    monkeypatch.setattr(predictor, "train", lambda *a, **k: calls.append(True) or None)

    assert predictor.predict("sh600519", auto_train=True) is None  # 训练后仍无模型 → None
    assert calls == [True]


def test_model_expiry_is_detected_from_meta(tmp_path):
    manager = ModelManager(base_dir=str(tmp_path))
    past = (datetime.now() - timedelta(days=1)).isoformat()
    future = (datetime.now() + timedelta(days=1)).isoformat()

    assert manager.is_expired({"meta": {"expires_at": past}}) is True
    assert manager.is_expired({"meta": {"expires_at": future}}) is False
    assert manager.is_expired({"meta": {}}) is False
    assert manager.is_expired({}) is False


@pytest.mark.parametrize("payload", [None])
def test_is_expired_handles_none(payload):
    assert ModelManager.is_expired(payload) is False

"""模型管理：代码规范化 + 拒绝指数"""

import pytest

from app.ai.model_manager import ModelManager


def test_save_normalizes_code(tmp_path):
    manager = ModelManager(base_dir=str(tmp_path))
    path = manager.save_ml_model("dummy", "605099", "rf")

    assert "sh605099_rf_" in path
    assert manager.load_ml_model("sh605099", "rf") is not None


def test_load_accepts_unnormalized_code(tmp_path):
    manager = ModelManager(base_dir=str(tmp_path))
    manager.save_ml_model("dummy", "sh605099", "rf")

    payload = manager.load_ml_model("605099", "rf")
    assert payload is not None
    assert payload["code"] == "sh605099"


def test_save_rejects_index_code(tmp_path):
    manager = ModelManager(base_dir=str(tmp_path))
    with pytest.raises(ValueError):
        manager.save_ml_model("dummy", "sh000001", "rf")
    with pytest.raises(ValueError):
        manager.save_ml_model("dummy", "sz399001", "xgb")


def test_saved_meta_records_code(tmp_path):
    manager = ModelManager(base_dir=str(tmp_path))
    manager.save_ml_model("dummy", "600519", "rf", meta={"accuracy": 0.5})

    assert manager.load_ml_model("sh600519", "rf")["meta"]["accuracy"] == 0.5

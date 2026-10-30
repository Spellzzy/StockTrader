"""模型清理脚本的规划逻辑（只读规划，不实际删除）"""

from scripts.clean_models import build_cleanup_plan


def _touch(base, *names):
    for name in names:
        path = base / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")


def test_duplicate_without_prefix_is_deleted(tmp_path):
    _touch(
        tmp_path,
        "ml/sh605099_rf_20260408.joblib",
        "ml/605099_rf_20260408.joblib",
    )
    plan = build_cleanup_plan(tmp_path)

    assert [p.name for p in plan.delete] == ["605099_rf_20260408.joblib"]
    assert "重复(保留规范化代码)" in plan.delete_reasons["605099_rf_20260408.joblib"]
    assert [p.name for p in plan.keep] == ["sh605099_rf_20260408.joblib"]


def test_lone_unnormalized_file_is_renamed(tmp_path):
    _touch(tmp_path, "ml/605099_xgb_20260408.joblib")
    plan = build_cleanup_plan(tmp_path)

    assert plan.delete == []
    assert [(src.name, dst.name) for src, dst in plan.rename] == [
        ("605099_xgb_20260408.joblib", "sh605099_xgb_20260408.joblib")
    ]


def test_index_models_are_deleted(tmp_path):
    _touch(
        tmp_path,
        "ml/sh000001_rf_20260408.joblib",
        "ml/sh600519_rf_20260408.joblib",
    )
    plan = build_cleanup_plan(tmp_path)

    assert [p.name for p in plan.delete] == ["sh000001_rf_20260408.joblib"]
    assert "指数" in plan.delete_reasons["sh000001_rf_20260408.joblib"]
    assert [p.name for p in plan.keep] == ["sh600519_rf_20260408.joblib"]


def test_scaler_files_are_handled_too(tmp_path):
    _touch(
        tmp_path,
        "dl/sh605099_lstm_scaler.joblib",
        "dl/605099_lstm_scaler.joblib",
    )
    plan = build_cleanup_plan(tmp_path)

    assert [p.name for p in plan.delete] == ["605099_lstm_scaler.joblib"]


def test_apply_removes_and_renames(tmp_path):
    _touch(
        tmp_path,
        "ml/sh605099_rf_20260408.joblib",
        "ml/605099_rf_20260408.joblib",
        "ml/605099_xgb_20260408.joblib",
    )
    plan = build_cleanup_plan(tmp_path)
    plan.apply()

    remaining = sorted(p.name for p in (tmp_path / "ml").iterdir())
    assert remaining == ["sh605099_rf_20260408.joblib", "sh605099_xgb_20260408.joblib"]

"""预测质量闸门：弱模型不能靠高置信度顶出 5 星强信号"""

from app.ai.predictor_service import PredictorService


def _pred(signal_value=1, confidence=90.0, accuracy=0.5):
    return {
        "signal_value": signal_value,
        "confidence": confidence,
        "model_accuracy": accuracy,
        "signal": "看涨" if signal_value > 0 else "看跌",
        "indicators": {},
    }


def test_strong_models_keep_full_strength():
    svc = PredictorService()
    combined = svc._combine_predictions(_pred(accuracy=0.55), _pred(accuracy=0.50), None)

    assert combined["quality"]["below_baseline"] is False
    assert combined["quality"]["factor"] == 1.0
    assert combined["stars"] >= 3
    assert combined["signal"] == "看涨"


def test_weak_models_are_downweighted_and_capped_at_two_stars():
    svc = PredictorService()
    combined = svc._combine_predictions(_pred(accuracy=0.28), _pred(accuracy=0.26), None)

    quality = combined["quality"]
    assert quality["below_baseline"] is True
    assert quality["factor"] < 1.0
    assert quality["mean_accuracy"] < quality["baseline"]
    assert "随机基线" in quality["note"]
    assert combined["stars"] <= 2
    # 评分要明显低于同等信号强度的可靠模型
    strong = svc._combine_predictions(_pred(accuracy=0.55), _pred(accuracy=0.50), None)
    assert combined["score"] < strong["score"]
    assert combined["confidence"] < strong["confidence"]


def test_boundary_exactly_at_baseline_is_not_flagged():
    svc = PredictorService(quality_baseline=0.3333)
    combined = svc._combine_predictions(
        _pred(accuracy=0.3333), _pred(accuracy=0.3333), None
    )
    assert combined["quality"]["below_baseline"] is False


def test_missing_accuracy_is_not_penalized():
    svc = PredictorService()
    pred = {"signal_value": 1, "confidence": 80.0, "signal": "看涨", "indicators": {}}
    combined = svc._combine_predictions(pred, None, None)

    assert combined["quality"]["mean_accuracy"] is None
    assert combined["quality"]["below_baseline"] is False
    assert combined["quality"]["factor"] == 1.0


def test_one_strong_one_weak_weak_model_weight_is_reduced():
    svc = PredictorService()
    weak_first = svc._combine_predictions(_pred(accuracy=0.20), _pred(accuracy=0.60), None)
    strong_first = svc._combine_predictions(_pred(accuracy=0.60), _pred(accuracy=0.60), None)

    # 同样的信号方向，弱模型参与时综合评分应更低
    assert weak_first["score"] <= strong_first["score"]


def test_no_models_returns_no_data():
    combined = PredictorService()._combine_predictions(None, None, None)
    assert combined["signal"] == "无数据"
    assert combined["score"] == 0

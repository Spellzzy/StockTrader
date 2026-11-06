"""路线 A 第一刀：SmartDigest 透传/渲染 combined.quality"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.smart_digest import SmartDigestService


def _scan_row(code, signal, score, *, quality=None, confidence=60.0, stars=3):
    combined = {
        "signal": signal,
        "score": score,
        "confidence": confidence,
        "stars": stars,
        "key_factors": ["样例因子"],
    }
    if quality is not None:
        combined["quality"] = quality
    return {"code": code, "combined": combined}


WEAK_QUALITY = {
    "below_baseline": True,
    "factor": 0.4,
    "mean_accuracy": 0.27,
    "baseline": 0.3333,
    "note": "准确率低于随机基线，信号已降权",
}

STRONG_QUALITY = {
    "below_baseline": False,
    "factor": 1.0,
    "mean_accuracy": 0.55,
    "baseline": 0.3333,
    "note": "",
}


class _FakeScan:
    def latest(self):
        return {}


def test_generate_projects_quality_onto_bullish_and_bearish_items(monkeypatch):
    svc = SmartDigestService()
    watched = [
        SimpleNamespace(code="sh600001", name="弱看涨"),
        SimpleNamespace(code="sz000001", name="弱看跌"),
    ]
    monkeypatch.setattr(svc, "_watchlist", MagicMock(list_watched=lambda: watched))
    monkeypatch.setattr(
        svc,
        "_predictor",
        MagicMock(
            scan=lambda codes, use_dl=False: [
                _scan_row("sh600001", "看涨", 12.0, quality=WEAK_QUALITY, stars=2),
                _scan_row("sz000001", "看跌", -18.0, quality=WEAK_QUALITY, stars=1),
            ],
            has_llm=False,
        ),
    )

    import app.services.market_scan_service as mss

    monkeypatch.setattr(mss, "MarketScanService", _FakeScan)

    digest = svc.generate()
    assert digest is not None
    assert digest["bullish"][0]["quality"]["below_baseline"] is True
    assert digest["bearish"][0]["quality"]["below_baseline"] is True

    md = digest["summary_text"]
    plain = digest["plain_text"]
    assert "准确率低于随机基线" in md
    assert "准确率低于随机基线" in plain
    assert md.count("⚠️ 可信度:") >= 2


def test_markdown_and_plain_warn_with_default_note_when_quality_note_empty():
    svc = SmartDigestService()
    digest = {
        "date": "2026-11-06 12:00",
        "total": 2,
        "bullish": [
            {
                "code": "sh600001",
                "name": "弱看涨",
                "signal": "看涨",
                "score": 10.0,
                "confidence": 40.0,
                "stars": 2,
                "key_factors": [],
                "quality": {
                    "below_baseline": True,
                    "factor": 0.5,
                    "mean_accuracy": 0.2,
                    "baseline": 0.3333,
                    "note": "   ",
                },
            }
        ],
        "bearish": [
            {
                "code": "sz000001",
                "name": "弱看跌",
                "signal": "看跌",
                "score": -10.0,
                "confidence": 40.0,
                "stars": 1,
                "key_factors": [],
                "quality": {
                    "below_baseline": True,
                    "factor": 0.5,
                    "mean_accuracy": 0.2,
                    "baseline": 0.3333,
                },
            }
        ],
        "neutral": [],
        "llm_reports": {},
    }
    md = svc._build_markdown_digest(digest, {})
    plain = svc._build_plain_digest(digest, {})
    assert "弱于基线，勿当强信号" in md
    assert "弱于基线，勿当强信号" in plain


def test_no_quality_no_crash_no_false_warning():
    svc = SmartDigestService()
    digest = {
        "date": "2026-11-06 12:00",
        "total": 2,
        "bullish": [
            {
                "code": "sh600519",
                "name": "强看涨",
                "signal": "看涨",
                "score": 30.0,
                "confidence": 80.0,
                "stars": 4,
                "key_factors": ["动量"],
                "quality": STRONG_QUALITY,
            }
        ],
        "bearish": [
            {
                "code": "sz000002",
                "name": "无质量字段",
                "signal": "看跌",
                "score": -20.0,
                "confidence": 70.0,
                "stars": 3,
                "key_factors": [],
            }
        ],
        "neutral": [
            {
                "code": "sz000003",
                "name": "震荡",
                "signal": "震荡",
                "score": 1.0,
                "confidence": 50.0,
                "stars": 2,
                "key_factors": [],
            }
        ],
        "llm_reports": {},
        "market_picks": {},
    }
    md = svc._build_markdown_digest(digest, {})
    plain = svc._build_plain_digest(digest, {})
    assert "弱于基线" not in md and "可信度:" not in md
    assert "弱于基线" not in plain and "可信度:" not in plain
    assert "自选股智能日报" in md


def test_quality_warning_helper():
    assert SmartDigestService._quality_warning({}) is None
    assert SmartDigestService._quality_warning({"quality": STRONG_QUALITY}) is None
    assert (
        SmartDigestService._quality_warning({"quality": WEAK_QUALITY})
        == "准确率低于随机基线，信号已降权"
    )

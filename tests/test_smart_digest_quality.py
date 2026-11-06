"""路线 A：SmartDigest 透传 combined.quality，并渲染可信摘要。

第一刀：弱于基线时单行「⚠️ 可信度:」。
第二刀：看涨/看跌在有 quality 时改为四行可信摘要卡片，替换该单行；震荡仍只保留单行警示。
"""

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
    # 看涨/看跌有 quality：完整卡片替换单行警示，不双写
    assert md.count("📎 可信摘要") == 2
    assert plain.count("📎 可信摘要") == 2
    assert "⚠️ 可信度:" not in md
    assert "⚠️ 可信度:" not in plain
    assert "- 质量: 弱于基线" in md
    assert "- 质量: 弱于基线" in plain
    assert "- 依据: 样例因子" in md
    assert "- 信号: 看涨 · 评分 +12.0 · ⭐⭐" in md
    assert "- 信号: 看跌 · 评分 -18.0 · ⭐" in plain


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
    assert "- 说明: 弱于基线，勿当强信号" in md
    assert "- 说明: 弱于基线，勿当强信号" in plain
    assert md.count("- 说明: 弱于基线，勿当强信号") == 2
    assert "⚠️ 📎 可信摘要" in md
    assert "⚠️ 可信度:" not in md
    assert "⚠️ 可信度:" not in plain
    assert "- 依据:" not in md
    assert "- 依据:" not in plain


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


def _item(code, name, signal, score, stars, factors, quality="__missing__"):
    item = {
        "code": code,
        "name": name,
        "signal": signal,
        "score": score,
        "confidence": 55.0,
        "stars": stars,
        "key_factors": factors,
    }
    if quality != "__missing__":
        item["quality"] = quality
    return item


def _digest(bullish=None, bearish=None, neutral=None):
    bullish = bullish or []
    bearish = bearish or []
    neutral = neutral or []
    return {
        "date": "2026-11-06 12:00",
        "total": len(bullish) + len(bearish) + len(neutral),
        "bullish": bullish,
        "bearish": bearish,
        "neutral": neutral,
        "llm_reports": {},
        "market_picks": {},
    }


def _render(digest):
    svc = SmartDigestService()
    return (
        svc._build_markdown_digest(digest, {}),
        svc._build_plain_digest(digest, {}),
    )


def _cards(text: str) -> list[str]:
    """抽出可信摘要块（去掉缩进与 plain 的 yellow 标记），便于两路对照。"""
    cards = []
    buf = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("[yellow]"):
            line = line[len("[yellow]"):]
        if line.endswith("[/yellow]"):
            line = line[: -len("[/yellow]")]
        line = line.strip()
        is_title = line.startswith("📎 可信摘要") or line.startswith("⚠️ 📎 可信摘要")
        if is_title:
            if buf:
                cards.append("\n".join(buf))
            buf = [line]
        elif buf and line.startswith("- "):
            buf.append(line)
        elif buf:
            cards.append("\n".join(buf))
            buf = []
    if buf:
        cards.append("\n".join(buf))
    return cards


def _credibility_card(item):
    render = getattr(SmartDigestService, "_credibility_card", None)
    if render is None:
        return None
    return render(item)


_SCARE = ("⚠️", "勿当", "弱于", "警告", "不具备", "恐吓")


def test_weak_bullish_and_bearish_render_full_card_in_markdown_and_plain():
    bull = _item(
        "sh600001", "弱看涨", "看涨", 12.0, 2, ["动量", "放量"], quality=WEAK_QUALITY,
    )
    bear = _item(
        "sz000001", "弱看跌", "看跌", -18.0, 1, ["破位"], quality=dict(WEAK_QUALITY, note=""),
    )
    md, plain = _render(_digest(bullish=[bull], bearish=[bear]))

    bull_card = "\n".join([
        "⚠️ 📎 可信摘要",
        "- 信号: 看涨 · 评分 +12.0 · ⭐⭐",
        "- 质量: 弱于基线",
        "- 说明: 准确率低于随机基线，信号已降权",
        "- 依据: 动量、放量",
        "- 准确率: 27.0% · 基线 33.3%",
        "- 降权: 0.40",
        "- 置信度: 55.0%",
    ])
    bear_card = "\n".join([
        "⚠️ 📎 可信摘要",
        "- 信号: 看跌 · 评分 -18.0 · ⭐",
        "- 质量: 弱于基线",
        "- 说明: 弱于基线，勿当强信号",
        "- 依据: 破位",
        "- 准确率: 27.0% · 基线 33.3%",
        "- 降权: 0.40",
        "- 置信度: 55.0%",
    ])
    assert _credibility_card(bull) == bull_card
    assert _credibility_card(bear) == bear_card
    assert _cards(md) == [bull_card, bear_card]
    assert _cards(plain) == [bull_card, bear_card]
    assert "⚠️ 可信度:" not in md
    assert "⚠️ 可信度:" not in plain


def test_strong_card_says_better_than_baseline_without_scare_copy():
    item = _item(
        "sh600519", "强看涨", "看涨", 8.5, 4,
        ["均线多头", "放量", "北向流入", "不应出现的第四条"],
        quality={"below_baseline": False, "note": "  "},
    )
    expected = "\n".join([
        "📎 可信摘要",
        "- 信号: 看涨 · 评分 +8.5 · ⭐⭐⭐⭐",
        "- 质量: 优于基线",
        "- 说明: 质量正常",
        "- 依据: 均线多头、放量、北向流入",
        "- 置信度: 55.0%",
    ])
    assert _credibility_card(item) == expected
    for word in _SCARE:
        assert word not in expected

    noted = _item(
        "sh600519", "强看涨", "看涨", 8.5, 4, [],
        quality={"below_baseline": False, "note": "样本充足，与基线持平"},
    )
    noted_card = _credibility_card(noted)
    assert noted_card is not None
    assert "- 说明: 样本充足，与基线持平" in noted_card
    assert "质量正常" not in noted_card
    assert "- 依据:" not in noted_card
    for word in _SCARE:
        assert word not in noted_card

    md, plain = _render(_digest(bullish=[item, noted]))
    assert _cards(md) == _cards(plain)
    assert "优于基线" in md and "优于基线" in plain
    assert "⚠️ 可信度:" not in md and "⚠️ 可信度:" not in plain


def test_missing_or_non_dict_quality_omits_card_and_does_not_crash():
    missing = _item("sh600000", "无质量", "看涨", 3.0, 1, ["因子"])
    bad = _item("sz000001", "坏质量", "看跌", -3.0, 1, ["因子"], quality="nope")
    assert _credibility_card(missing) is None
    assert _credibility_card(bad) is None
    md, plain = _render(_digest(bullish=[missing], bearish=[bad]))
    assert "📎 可信摘要" not in md and "📎 可信摘要" not in plain
    assert "⚠️ 可信度:" not in md and "⚠️ 可信度:" not in plain
    assert "无质量" in md and "坏质量" in plain


def test_sideways_weak_quality_keeps_warning_line_without_full_card():
    sideways = _item(
        "sz000003", "震荡股", "震荡", 0.5, 2, ["横盘"],
        quality={"below_baseline": True, "note": "震荡模型偏弱"},
    )
    bull = _item(
        "sh600001", "弱看涨", "看涨", 6.0, 2, [],
        quality={"below_baseline": True, "note": "看涨模型偏弱"},
    )
    md, plain = _render(_digest(bullish=[bull], neutral=[sideways]))
    for text in (md, plain):
        assert text.count("📎 可信摘要") == 1
        assert text.count("⚠️ 可信度:") == 1
        assert "⚠️ 可信度: 震荡模型偏弱" in text
        assert "⚠️ 可信度: 看涨模型偏弱" not in text
        assert "- 说明: 看涨模型偏弱" in text
        assert "- 质量:" in text
    # 震荡段本身没有四行卡片
    for text in (md, plain):
        neutral_part = text.split("继续持有", 1)[1]
        assert "📎 可信摘要" not in neutral_part
        assert "- 质量:" not in neutral_part
        assert "- 依据:" not in neutral_part
        assert "准确率:" not in neutral_part
        assert "降权:" not in neutral_part


def test_evidence_lines_appear_only_when_quality_has_numbers():
    full = _item(
        "sh600519", "完整", "看涨", 9.0, 3, [],
        quality={
            "below_baseline": False,
            "mean_accuracy": 0.273,
            "baseline": 0.333,
            "factor": 0.4,
            "note": "样本一般",
            "confidence": 12.5,
            "models_used": 3,
        },
    )
    card = _credibility_card(full)
    assert "- 质量: 优于基线" in card
    assert "- 说明: 样本一般" in card
    assert "- 准确率: 27.3% · 基线 33.3%" in card
    assert "- 降权: 0.40" in card
    assert "- 置信度: 12.5%" in card
    assert "- 模型数: 3" in card
    assert "⚠️" not in card

    only_acc = _item(
        "sh600000", "只有准确率", "看涨", 1.0, 1, [],
        quality={"below_baseline": False, "mean_accuracy": 0.5, "note": "质量正常"},
    )
    only_acc["confidence"] = None
    acc_card = _credibility_card(only_acc)
    assert "- 准确率: 50.0%" in acc_card
    assert " · 基线" not in acc_card
    assert "- 基线:" not in acc_card
    assert "降权:" not in acc_card
    assert "置信度:" not in acc_card
    assert "模型数:" not in acc_card

    only_base = _item(
        "sh600001", "只有基线", "看跌", -1.0, 1, [],
        quality={"below_baseline": True, "baseline": 0.333, "note": "弱"},
    )
    only_base.pop("confidence")
    base_card = _credibility_card(only_base)
    assert "- 基线: 33.3%" in base_card
    assert "准确率:" not in base_card
    assert "- 质量: 弱于基线" in base_card
    assert base_card.startswith("⚠️ 📎 可信摘要")

    zero_factor = _item(
        "sz000001", "零降权", "看涨", 2.0, 1, [],
        quality={"below_baseline": False, "factor": 0, "note": "质量正常"},
    )
    zero_factor.pop("confidence")
    assert "- 降权: 0.00" in _credibility_card(zero_factor)

    junk = _item(
        "sz000002", "坏数字", "看涨", 2.0, 1, [],
        quality={
            "below_baseline": False,
            "mean_accuracy": "高",
            "baseline": None,
            "factor": True,
            "note": "质量正常",
            "models_used": "两只",
        },
    )
    junk.pop("confidence")
    junk_card = _credibility_card(junk)
    assert "- 质量: 优于基线" in junk_card
    assert "- 说明: 质量正常" in junk_card
    assert "准确率:" not in junk_card
    assert "降权:" not in junk_card
    assert "模型数:" not in junk_card


def test_sideways_keeps_warning_even_when_quality_has_evidence_numbers():
    quality = dict(WEAK_QUALITY, note="震荡模型偏弱")
    sideways = _item("sz000003", "震荡股", "震荡", 0.5, 2, [], quality=quality)
    bull = _item(
        "sh600001", "弱看涨", "看涨", 6.0, 2, [],
        quality=dict(WEAK_QUALITY, note="看涨模型偏弱"),
    )
    md, plain = _render(_digest(bullish=[bull], neutral=[sideways]))
    for text in (md, plain):
        neutral_part = text.split("继续持有", 1)[1]
        assert "⚠️ 可信度: 震荡模型偏弱" in neutral_part
        assert "准确率:" not in neutral_part
        assert "降权:" not in neutral_part
        assert "📎 可信摘要" not in neutral_part
        assert "- 准确率: 27.0% · 基线 33.3%" in text
        assert "- 降权: 0.40" in text
        assert text.count("📎 可信摘要") == 1


def test_generate_copies_models_used_onto_card(monkeypatch):
    svc = SmartDigestService()
    watched = [SimpleNamespace(code="sh600001", name="弱看涨")]
    row = _scan_row("sh600001", "看涨", 12.0, quality=WEAK_QUALITY, stars=2)
    row["combined"]["models_used"] = 3
    monkeypatch.setattr(svc, "_watchlist", MagicMock(list_watched=lambda: watched))
    monkeypatch.setattr(
        svc, "_predictor",
        MagicMock(scan=lambda codes, use_dl=False: [row], has_llm=False),
    )
    import app.services.market_scan_service as mss

    monkeypatch.setattr(mss, "MarketScanService", _FakeScan)

    digest = svc.generate()
    assert digest["bullish"][0]["models_used"] == 3
    assert digest["bullish"][0]["quality"]["factor"] == 0.4
    for text in (digest["summary_text"], digest["plain_text"]):
        assert "- 准确率: 27.0% · 基线 33.3%" in text
        assert "- 降权: 0.40" in text
        assert "- 模型数: 3" in text
        assert "- 质量: 弱于基线" in text
        assert "⚠️ 可信度:" not in text

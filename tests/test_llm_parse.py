"""LLM 响应解析（三级兜底）"""

from app.ai.llm_analyzer import LLMAnalyzer


def _parse(raw: str):
    return LLMAnalyzer()._parse_response(raw, "sh600519")


def test_parse_plain_json():
    raw = '{"technical_analysis":"均线多头","confidence":80,"overall_rating":"看多"}'
    report = _parse(raw)

    assert report.error == ""
    assert report.code == "sh600519"
    assert report.technical_analysis == "均线多头"
    assert report.confidence == 80
    assert report.overall_rating == "看多"


def test_parse_fenced_json_block():
    raw = '分析如下:\n```json\n{"overall_rating":"看空","risk_warnings":["高位放量"]}\n```'
    report = _parse(raw)

    assert report.error == ""
    assert report.overall_rating == "看空"
    assert report.risk_warnings == ["高位放量"]


def test_parse_json_surrounded_by_text():
    raw = '前缀说明 {"confidence": 55, "news_sentiment": "positive"} 后缀说明'
    report = _parse(raw)

    assert report.error == ""
    assert report.confidence == 55
    assert report.news_sentiment == "positive"


def test_parse_garbage_returns_raw_text():
    raw = "抱歉，我无法完成这个请求"
    report = _parse(raw)

    assert report.error
    assert report.technical_analysis == raw
    assert report.overall_rating == "中性"

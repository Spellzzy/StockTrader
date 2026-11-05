"""全市场摘选：预筛 / 打分 / 落库 / 日报附加段"""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
import app.services.market_scan_service as scan_mod
from app.models.base import Base

_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
)
_Session = sessionmaker(bind=_engine)


@contextmanager
def _scope():
    session = _Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _quote(code, name, price=10.0, amount=8000, change=1.0, volume=10000):
    return {
        "code": code, "name": name, "price": price, "amount": amount,
        "change_percent": change, "volume": volume,
    }


CODES = ["sh600001", "sh600002", "sh600003", "sh600004", "sh600005"]
QUOTES = {
    "sh600001": _quote("sh600001", "正常甲", amount=9000),
    "sh600002": _quote("sh600002", "ST测试", amount=20000),   # ST 过滤
    "sh600003": _quote("sh600003", "低成交", amount=100),      # 成交额过滤
    "sh600004": _quote("sh600004", "涨停股", change=10.5),     # 涨跌停过滤
    "sh600005": _quote("sh600005", "正常乙", amount=5000),
}


class FakeClient:
    def __init__(self, *a, **kw):
        pass

    def quote(self, *codes, **kw):
        return {c: QUOTES[c] for c in codes if c in QUOTES}


class FakeScreener:
    instances = []
    screen_calls = 0

    def __init__(self, screener_config=None):
        self.cfg = screener_config or {}
        self.received = []
        FakeScreener.instances.append(self)

    def resolve_pool(self, pool=None):
        return list(CODES)

    def screen(self, codes, side="buy", positions=None, progress_cb=None):
        FakeScreener.screen_calls += 1
        self.received = list(codes)
        return [
            SimpleNamespace(code="sh600005", name="正常乙", side=side, price=10.0,
                            matched=[("ma_uptrend", "MA20向上")], total_rules=4),
            SimpleNamespace(code="sh600001", name="正常甲", side=side, price=10.0,
                            matched=[("ma_uptrend", "MA20向上"),
                                     ("volume_expand", "放量")], total_rules=4),
        ]


@pytest.fixture
def svc(monkeypatch, isolate_config):
    Base.metadata.drop_all(_engine)
    Base.metadata.create_all(_engine)
    FakeScreener.instances = []
    FakeScreener.screen_calls = 0
    monkeypatch.setattr(scan_mod, "StockDataClient", FakeClient)
    monkeypatch.setattr(scan_mod, "ScreenerService", FakeScreener)
    return scan_mod.MarketScanService(
        config={"pool": "all_a", "batch_size": 2, "candidate_limit": 10,
                "min_amount_wan": 3000, "min_price": 2.0, "max_price": 500.0,
                "max_change_pct": 9.8, "exclude_st": True,
                "exclude_delisted": True, "top_n": 20, "side": "buy"},
        scope=_scope,
    )


def test_prefilter_applies_hard_filters_and_sorts_by_amount(svc):
    candidates, stats = svc.prefilter(CODES)

    assert candidates == ["sh600001", "sh600005"]   # 成交额降序
    assert stats["universe"] == 5 and stats["candidates"] == 2


def test_prefilter_excludes_delisted_and_suspended(svc, monkeypatch):
    extra = dict(QUOTES)
    extra["sh600005"] = _quote("sh600005", "某某退", amount=9000)
    extra["sh600003"] = _quote("sh600003", "停牌股", amount=9000, volume=0)
    monkeypatch.setattr(FakeClient, "quote", lambda self, *codes, **kw:
                        {c: extra[c] for c in codes if c in extra})

    candidates, _ = svc.prefilter(CODES)
    assert "sh600005" not in candidates and "sh600003" not in candidates


def test_prefilter_respects_candidate_limit(svc):
    svc.cfg["candidate_limit"] = 1
    candidates, _ = svc.prefilter(CODES)
    assert candidates == ["sh600001"]


def test_run_saves_and_scores_by_matched_count(svc):
    result = svc.run()

    assert result["cached"] is False
    assert result["universe_count"] == 5
    assert result["candidate_count"] == 2
    assert result["hit_count"] == 2
    assert result["hits"][0]["code"] == "sh600001"     # 命中 2 条排前面
    assert result["hits"][0]["matched_count"] == 2
    assert FakeScreener.instances[0].received == ["sh600001", "sh600005"]


def test_run_reuses_today_result_without_rescanning(svc):
    first = svc.run()
    second = svc.run()

    assert second["cached"] is True
    assert second["id"] == first.get("id") or second["hit_count"] == first["hit_count"]
    assert FakeScreener.screen_calls == 1        # 第二次没有跑条件评估


def test_force_reruns(svc):
    svc.run()
    assert svc.run(force=True)["cached"] is False
    assert FakeScreener.screen_calls == 2


def test_latest_and_list_runs(svc):
    assert svc.latest() is None
    assert svc.list_runs() == []
    svc.run()
    latest = svc.latest()
    assert latest and latest["hits"][0]["code"] == "sh600001"
    assert len(svc.list_runs(limit=5)) == 1


def test_scan_uses_independent_relaxed_rules_by_default(svc):
    """全市场摘选不应沿用自选股 sn 的 mode=all 严格规则"""
    cfg = FakeScreener.instances[0].cfg
    assert cfg["buy"]["mode"] == "atleast:2"
    names = [r["name"] for r in cfg["buy"]["rules"]]
    assert "ma_bull" in names and "macd_golden" in names
    assert "sector_strong" not in names       # 需要基准数据的硬条件不进默认
    assert scan_mod.DEFAULT_SCAN_RULES[4]["params"]["ratio"] == 1.2


def test_custom_rules_override_defaults(monkeypatch, isolate_config):
    monkeypatch.setattr(scan_mod, "StockDataClient", FakeClient)
    monkeypatch.setattr(scan_mod, "ScreenerService", FakeScreener)
    custom = [{"name": "rsi_below", "params": {"threshold": 40}}]
    scan_mod.MarketScanService(
        config={"mode": "any", "rules": custom}, scope=_scope
    )
    cfg = FakeScreener.instances[-1].cfg
    assert cfg["buy"]["mode"] == "any" and cfg["buy"]["rules"] == custom


def test_inherit_screener_keeps_original_rules(monkeypatch, isolate_config):
    isolate_config["screener"] = {
        "buy": {
            "mode": "all",
            "rules": [{"name": "sector_strong", "params": {}}],
        }
    }
    monkeypatch.setattr(scan_mod, "StockDataClient", FakeClient)
    monkeypatch.setattr(scan_mod, "ScreenerService", FakeScreener)
    scan_mod.MarketScanService(
        config={"inherit_screener": True}, scope=_scope
    )
    cfg = FakeScreener.instances[-1].cfg
    assert cfg["buy"]["mode"] == "all"
    assert any(r["name"] == "sector_strong" for r in cfg["buy"]["rules"])


def test_params_hash_changes_with_rules(svc):
    a = svc.params_hash()
    svc.cfg["mode"] = "any"
    assert svc.params_hash() != a


def test_params_hash_changes_with_config_and_actual_pool(svc):
    a = svc.params_hash()
    svc.cfg["min_amount_wan"] = 9999
    assert svc.params_hash() != a

    # 命令行覆盖的池 / 方向必须参与哈希，避免跨池误复用
    assert svc.params_hash("watchlist") != svc.params_hash("all_a")
    assert svc.params_hash("all_a", "sell") != svc.params_hash("all_a", "buy")


def test_is_star_market_recognises_688_and_689_only():
    from app.services.market_scan_service import is_star_market

    assert is_star_market("sh688001") is True
    assert is_star_market("sh689009") is True
    assert is_star_market("688001") is True
    for code in ("sh600001", "sz300001", "sz000001", "sh605099"):
        assert is_star_market(code) is False


def test_exclude_star_filters_before_quote(svc, monkeypatch):
    seen = []
    extra = dict(QUOTES)
    extra.update({
        "sh688001": _quote("sh688001", "科创股", amount=99999),
        "sh689002": _quote("sh689002", "CDR股", amount=99999),
        "sz300001": _quote("sz300001", "创业板", amount=9000),
    })

    def fake_quote(self, *codes, **kw):
        seen.extend(codes)
        return {c: extra[c] for c in codes if c in extra}

    monkeypatch.setattr(FakeClient, "quote", fake_quote)
    codes = ["sh600001", "sh688001", "sh689002", "sz300001"]
    svc.cfg["exclude_star"] = True

    candidates, stats = svc.prefilter(codes)

    assert stats["universe"] == 4           # 池规模仍是原始值
    assert stats["star_excluded"] == 2
    assert "sh688001" not in seen and "sh689002" not in seen  # 连 quote 都没发
    assert set(candidates) == {"sh600001", "sz300001"}


def test_star_codes_kept_when_option_off(svc, monkeypatch):
    extra = dict(QUOTES)
    extra["sh688001"] = _quote("sh688001", "科创股", amount=99999)
    monkeypatch.setattr(FakeClient, "quote", lambda self, *codes, **kw:
                        {c: extra[c] for c in codes if c in extra})
    svc.cfg["exclude_star"] = False

    candidates, stats = svc.prefilter(["sh600001", "sh688001"])
    assert "sh688001" in candidates and stats["star_excluded"] == 0


def test_params_hash_includes_exclude_star(svc):
    a = svc.params_hash()
    svc.cfg["exclude_star"] = True
    assert svc.params_hash() != a


def test_report_shows_star_excluded():
    from scripts.scheduled_screen import build_report

    text = build_report({
        "generated_at": "2026-11-05T15:30:00", "pool": "all_a",
        "universe_count": 5000, "star_excluded": 120,
        "candidate_count": 600, "hit_count": 2, "duration_seconds": 12.3,
        "hits": [],
    })
    assert "跳过科创板" in text and "120" in text


def test_report_contains_hits_and_stats():
    from scripts.scheduled_screen import build_report

    text = build_report({
        "generated_at": "2026-11-05T15:30:00", "pool": "all_a",
        "universe_count": 5000, "candidate_count": 600, "hit_count": 2,
        "duration_seconds": 12.3,
        "hits": [
            {"code": "sh600001", "name": "正常甲", "price": 10.0,
             "matched_count": 2, "total_rules": 4,
             "matched": [["ma_uptrend", ""], ["volume_expand", ""]]},
        ],
    })
    assert "全市场摘选" in text and "sh600001" in text and "600" in text


def test_digest_includes_market_picks_section():
    from app.services.smart_digest import SmartDigestService

    digest = {
        "date": "2026-11-05 15:30", "total": 1,
        "bullish": [], "bearish": [], "neutral": [], "llm_reports": {},
        "market_picks": {
            "run_date": "2026-11-05", "pool": "all_a",
            "universe_count": 5000, "candidate_count": 600,
            "hit_count": 3, "duration_seconds": 12.3,
            "hits": [{"code": "sh600001", "name": "正常甲",
                      "matched_count": 2, "total_rules": 4,
                      "matched": [["ma_uptrend", ""], ["volume_expand", ""]]}],
        },
    }
    svc = SmartDigestService()
    md = svc._build_markdown_digest(digest, {})
    plain = svc._build_plain_digest(digest, {})

    assert "今日全市场摘选" in md and "sh600001" in md
    assert "今日全市场摘选" in plain


def test_digest_shows_summary_even_when_no_hits():
    """0 命中也要说明扫了什么，不能整段消失"""
    from app.services.smart_digest import SmartDigestService

    digest = {
        "date": "2026-11-05 15:30", "total": 1,
        "bullish": [], "bearish": [], "neutral": [], "llm_reports": {},
        "market_picks": {
            "run_date": "2026-11-05", "pool": "all_a",
            "universe_count": 5000, "candidate_count": 600,
            "hit_count": 0, "duration_seconds": 12.3, "hits": [],
        },
    }
    svc = SmartDigestService()
    md = svc._build_markdown_digest(digest, {})
    plain = svc._build_plain_digest(digest, {})
    assert "今日全市场摘选" in md and "没有股票满足" in md
    assert "今日全市场摘选" in plain and "本次无命中" in plain


def test_digest_without_scan_still_works():
    from app.services.smart_digest import SmartDigestService

    digest = {
        "date": "2026-11-05 15:30", "total": 0,
        "bullish": [], "bearish": [], "neutral": [], "llm_reports": {},
    }
    assert "自选股智能日报" in SmartDigestService()._build_markdown_digest(digest, {})

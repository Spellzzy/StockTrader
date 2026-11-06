"""digest run / push 成功后落盘；preview 不落盘；落盘失败不让命令失败"""

import json
from pathlib import Path

from typer.testing import CliRunner

from app.cli import app


SUMMARY = "📎 可信摘要\n质量正常"
PLAIN = "PLAIN_ONLY_DO_NOT_PERSIST"
ITEM = {
    "code": "sh600519",
    "name": "茅台",
    "signal": "看涨",
    "score": 3.2,
    "confidence": 70.0,
    "stars": 3,
    "key_factors": ["放量"],
    "quality": {
        "below_baseline": False,
        "mean_accuracy": 0.55,
        "baseline": 0.333,
        "factor": 1.0,
    },
}
DIGEST = {
    "date": "2026-11-06 09:30",
    "total": 1,
    "bullish": [ITEM],
    "bearish": [],
    "neutral": [],
    "summary_text": SUMMARY,
    "plain_text": PLAIN,
    "scan_results": [{"secret": "SCAN_SHOULD_NOT_LEAK"}],
    "llm_reports": {"sh600519": {"body": "LLM_SHOULD_NOT_LEAK"}},
}


class _Watch:
    code = "sh600519"
    name = "茅台"


class _FakeDigestService:
    def __init__(self, digest=DIGEST, enabled=True):
        self._digest = digest
        self.watchlist = self
        self.notifier = type("Notifier", (), {"is_enabled": enabled})()

    def list_watched(self):
        return [_Watch()]

    def generate(self, **kwargs):
        return self._digest

    def generate_and_push(self, **kwargs):
        return {"digest": self._digest, "push_results": [("飞书", True, "")]}

    def auto_configure_alerts(self, digest):
        return []


def _install_service(monkeypatch, service):
    import app.logging_setup as logging_setup
    import app.services.smart_digest as smart_digest

    monkeypatch.setattr(smart_digest, "SmartDigestService", lambda: service)
    monkeypatch.setattr("app.cli.init_db", lambda: None)
    monkeypatch.setattr(logging_setup, "setup_logging", lambda *a, **kw: None)


def _silence_html(monkeypatch):
    import app.visualization.report as report_module

    def fake_build(self, **kwargs):
        path = Path(self.output_dir) / kwargs["filename"]
        path.write_text("<html></html>", encoding="utf-8")
        return str(path)

    monkeypatch.setattr(report_module.HTMLReport, "build", fake_build)


def test_digest_run_writes_summary_under_data_reports(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _install_service(monkeypatch, _FakeDigestService())
    _silence_html(monkeypatch)

    result = CliRunner().invoke(app, ["digest", "run"])

    assert result.exit_code == 0, result.output
    reports = tmp_path / "data" / "reports"
    md_files = list(reports.glob("digest_*.md"))
    html_files = list(reports.glob("daily_*.html"))
    assert len(md_files) == 1
    assert len(html_files) == 1
    assert md_files[0].name.replace("digest_", "daily_").replace(".md", ".html") == html_files[0].name
    body = md_files[0].read_text(encoding="utf-8")
    assert "可信" in body
    assert PLAIN not in body
    json_files = list(reports.glob("digest_*.json"))
    assert len(json_files) == 1
    assert json_files[0].name == md_files[0].name.replace(".md", ".json")
    payload = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert payload["date"] == "2026-11-06 09:30"
    assert payload["slot"] in ("am", "pm")
    assert payload["total"] == 1
    assert payload["bullish"][0]["quality"]["factor"] == 1.0
    assert payload["bullish"][0]["code"] == "sh600519"
    raw = json_files[0].read_text(encoding="utf-8")
    assert "SCAN_SHOULD_NOT_LEAK" not in raw
    assert "LLM_SHOULD_NOT_LEAK" not in raw
    assert PLAIN not in raw
    assert "scan_results" not in payload


def test_digest_push_writes_the_same_report(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _install_service(monkeypatch, _FakeDigestService())
    _silence_html(monkeypatch)

    result = CliRunner().invoke(app, ["digest", "push"])

    assert result.exit_code == 0, result.output
    reports = tmp_path / "data" / "reports"
    md_files = list(reports.glob("digest_*.md"))
    assert len(md_files) == 1
    assert "可信" in md_files[0].read_text(encoding="utf-8")
    assert PLAIN not in md_files[0].read_text(encoding="utf-8")
    json_files = list(reports.glob("digest_*.json"))
    assert len(json_files) == 1
    assert "SCAN_SHOULD_NOT_LEAK" not in json_files[0].read_text(encoding="utf-8")


def test_digest_preview_does_not_write_reports(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _install_service(monkeypatch, _FakeDigestService())
    calls = []

    def spy(*args, **kwargs):
        calls.append((args, kwargs))
        return {}

    monkeypatch.setattr("app.domain.report_persist.persist_daily_reports", spy)

    result = CliRunner().invoke(app, ["digest", "preview"])

    assert result.exit_code == 0, result.output
    assert calls == []
    assert list(tmp_path.rglob("digest_*.md")) == []
    assert list(tmp_path.rglob("digest_*.json")) == []
    assert list(tmp_path.rglob("daily_*.html")) == []


def test_persist_failure_does_not_fail_digest_run(monkeypatch):
    _install_service(monkeypatch, _FakeDigestService())

    def boom(*args, **kwargs):
        raise OSError("read-only")

    monkeypatch.setattr("app.domain.report_persist.persist_daily_reports", boom)

    result = CliRunner().invoke(app, ["digest", "run"])

    assert result.exit_code == 0, result.output
    assert "落盘失败" in result.output


def test_empty_persist_result_does_not_fail_digest_push(monkeypatch):
    _install_service(monkeypatch, _FakeDigestService())
    monkeypatch.setattr(
        "app.domain.report_persist.persist_daily_reports", lambda *a, **k: {}
    )

    result = CliRunner().invoke(app, ["digest", "push"])

    assert result.exit_code == 0, result.output
    assert "落盘失败" in result.output


def test_failed_generation_does_not_persist(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _install_service(monkeypatch, _FakeDigestService(digest=None))
    calls = []
    monkeypatch.setattr(
        "app.domain.report_persist.persist_daily_reports",
        lambda *a, **k: calls.append(1),
    )

    result = CliRunner().invoke(app, ["digest", "run"])

    assert result.exit_code == 0, result.output
    assert calls == []
    assert list(tmp_path.rglob("digest_*.md")) == []
    assert list(tmp_path.rglob("digest_*.json")) == []

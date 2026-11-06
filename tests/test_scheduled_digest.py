"""定时日报落盘：推送之外必须留一份文件"""

import importlib.util
import json
import logging
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT_ROOT / "scripts" / "scheduled_digest.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("scheduled_digest_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_persist_writes_markdown_and_html(tmp_path, monkeypatch):
    module = _load_script()
    import app.visualization.report as report_module

    seen = {}

    def fake_build(self, **kwargs):
        seen.update(kwargs)
        path = Path(self.output_dir) / kwargs["filename"]
        path.write_text("<html></html>", encoding="utf-8")
        return str(path)

    monkeypatch.setattr(report_module.HTMLReport, "build", fake_build)
    digest = {"summary_text": "# 今日概览\n自选股 12 只，涨 3 跌 8"}

    paths = module.persist_daily_reports(digest, output_dir=str(tmp_path))

    stamp = datetime.now().strftime("%Y%m%d")
    slot = "am" if datetime.now().hour < 12 else "pm"
    md = tmp_path / f"digest_{stamp}_{slot}.md"
    assert md.exists()
    content = md.read_text(encoding="utf-8")
    assert "今日概览" in content
    assert "12 只" in content
    # 显式 UTF-8 写入，不能带 BOM
    assert not md.read_bytes().startswith(b"\xef\xbb\xbf")

    assert "markdown" in paths
    assert seen["filename"] == f"daily_{stamp}_{slot}.html"
    assert paths["html"].endswith(f"daily_{stamp}_{slot}.html")
    assert Path(paths["html"]).exists()

    js = tmp_path / f"digest_{stamp}_{slot}.json"
    assert paths["json"] == str(js)
    assert js.exists()
    assert not js.read_bytes().startswith(b"\xef\xbb\xbf")
    payload = json.loads(js.read_text(encoding="utf-8"))
    assert payload["slot"] == slot
    assert "今日概览" not in js.read_text(encoding="utf-8")
    assert "scan_results" not in payload


def test_no_html_option(tmp_path):
    module = _load_script()

    paths = module.persist_daily_reports(
        {"summary_text": "内容"}, output_dir=str(tmp_path), with_html=False
    )

    assert "markdown" in paths
    assert "html" not in paths


def test_html_failure_does_not_lose_markdown(tmp_path, monkeypatch):
    module = _load_script()

    import app.visualization.report as report_module

    def boom(self, **kwargs):
        raise RuntimeError("图表炸了")

    monkeypatch.setattr(report_module.HTMLReport, "build", boom)

    paths = module.persist_daily_reports(
        {"summary_text": "内容"}, output_dir=str(tmp_path)
    )

    assert "markdown" in paths
    assert "html" not in paths


def test_digest_without_summary_still_creates_file(tmp_path):
    module = _load_script()

    paths = module.persist_daily_reports({}, output_dir=str(tmp_path), with_html=False)

    assert "markdown" in paths
    assert Path(paths["markdown"]).exists()


def test_scheduled_digest_uses_shared_persist():
    """定时脚本的落盘入口就是共享模块，避免两套实现分叉"""
    module = _load_script()
    from app.domain.report_persist import persist_daily_reports

    assert module.persist_daily_reports is persist_daily_reports


def _freeze_slot(monkeypatch, hour: int):
    from datetime import datetime as real_datetime

    import app.domain.report_persist as persist_module

    class Frozen(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 6, hour, 15)

    monkeypatch.setattr(persist_module, "datetime", Frozen)


def test_persist_writes_summary_text_not_plain_text(tmp_path):
    from app.domain.report_persist import persist_daily_reports

    paths = persist_daily_reports(
        {
            "summary_text": "📎 可信摘要\n质量正常",
            "plain_text": "PLAIN_ONLY_DO_NOT_PERSIST",
        },
        output_dir=str(tmp_path),
        with_html=False,
    )

    content = Path(paths["markdown"]).read_text(encoding="utf-8")
    assert "可信" in content
    assert "PLAIN_ONLY_DO_NOT_PERSIST" not in content


def test_same_slot_overwrites_and_am_pm_coexist(tmp_path, monkeypatch):
    from app.domain.report_persist import persist_daily_reports

    _freeze_slot(monkeypatch, 9)
    persist_daily_reports(
        {"summary_text": "上午第一版"}, output_dir=str(tmp_path), with_html=False
    )
    persist_daily_reports(
        {"summary_text": "上午覆盖版 可信摘要"}, output_dir=str(tmp_path), with_html=False
    )

    _freeze_slot(monkeypatch, 15)
    persist_daily_reports(
        {"summary_text": "下午版"}, output_dir=str(tmp_path), with_html=False
    )

    am = tmp_path / "digest_20261106_am.md"
    pm = tmp_path / "digest_20261106_pm.md"
    assert am.exists() and pm.exists()
    assert "上午覆盖版" in am.read_text(encoding="utf-8")
    assert "上午第一版" not in am.read_text(encoding="utf-8")
    assert "下午版" in pm.read_text(encoding="utf-8")
    assert {p.name for p in tmp_path.glob("digest_*.md")} == {
        "digest_20261106_am.md",
        "digest_20261106_pm.md",
    }
    am_json = json.loads((tmp_path / "digest_20261106_am.json").read_text(encoding="utf-8"))
    pm_json = json.loads((tmp_path / "digest_20261106_pm.json").read_text(encoding="utf-8"))
    assert am_json["slot"] == "am" and pm_json["slot"] == "pm"
    assert "上午第一版" not in (tmp_path / "digest_20261106_am.json").read_text(encoding="utf-8")
    assert "下午版" not in (tmp_path / "digest_20261106_am.json").read_text(encoding="utf-8")


def test_json_write_failure_keeps_markdown_and_does_not_raise(tmp_path, monkeypatch, caplog):
    from app.domain.report_persist import persist_daily_reports

    original = Path.write_text

    def wrapped(self, *args, **kwargs):
        if self.suffix == ".json":
            raise OSError("disk full")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", wrapped)
    digest = {
        "summary_text": "正文还在",
        "date": "2026-11-06 09:30",
        "total": 1,
        "bullish": [{"code": "sh600519", "quality": {"factor": 0.4}}],
        "bearish": [],
        "neutral": [],
        "scan_results": [{"secret": "NOPE"}],
    }

    with caplog.at_level(logging.WARNING):
        paths = persist_daily_reports(digest, output_dir=str(tmp_path), with_html=False)

    assert "markdown" in paths
    assert "json" not in paths
    assert "正文还在" in Path(paths["markdown"]).read_text(encoding="utf-8")
    assert list(tmp_path.glob("*.json")) == []
    assert any("JSON" in record.message for record in caplog.records)

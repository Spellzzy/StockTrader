"""Web 市场摘选 P2：后台任务 / 进度 / 取消 / 历史回看"""

import time
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
import app.web.api as api_mod
import app.web.scan_tasks as tasks_mod
from app.models.base import Base
from app.services.market_scan_service import ScanCancelled

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


def _wait(manager, task_id, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        task = manager.get(task_id)
        if task and task["status"] != "running":
            return task
        time.sleep(0.02)
    return manager.get(task_id)


class FakeScanService:
    """模拟扫描，不触网、不落库"""

    calls = []

    def __init__(self, config=None):
        self.config = config

    def run(self, **kw):
        FakeScanService.calls.append(kw)
        prefilter_cb = kw.get("prefilter_cb")
        screen_cb = kw.get("screen_cb")
        if prefilter_cb:
            prefilter_cb(100, 100, 20)
        if kw.get("cancel_event") is not None and kw["cancel_event"].is_set():
            raise ScanCancelled("已取消")
        if screen_cb:
            screen_cb(20, 20, 3)
        return {
            "run_date": "2026-11-05", "pool": "watchlist",
            "universe_count": 100, "candidate_count": 20, "hit_count": 3,
            "duration_seconds": 0.4, "generated_at": "2026-11-05T15:30:00",
            "hits": [{"code": "sh600001", "name": "甲", "price": 10.0,
                      "matched_count": 2, "total_rules": 5, "matched": []}],
        }


class SlowScanService(FakeScanService):
    def run(self, **kw):
        time.sleep(0.35)
        return super().run(**kw)


@pytest.fixture
def manager():
    FakeScanService.calls = []
    return tasks_mod.ScanTaskManager(service_factory=lambda top: FakeScanService())


def test_task_runs_to_completion_with_progress(manager):
    started = manager.start(pool="watchlist")
    assert not started["already_running"]

    task = _wait(manager, started["task_id"])
    assert task["status"] == "done"
    assert task["progress"] == 100
    assert task["result"]["hit_count"] == 3
    assert task["finished_at"]
    assert FakeScanService.calls[0]["prefilter_cb"] is not None


def test_second_start_reports_already_running():
    mgr = tasks_mod.ScanTaskManager(service_factory=lambda top: SlowScanService())
    first = mgr.start(pool="watchlist")
    second = mgr.start(pool="all_a")

    assert first["already_running"] is False
    assert second["already_running"] is True
    assert second["task_id"] == first["task_id"]
    _wait(mgr, first["task_id"])


def test_cancel_marks_task_cancelled():
    # 用会阻塞的 fake，保证取消发生在任务运行期间
    mgr = tasks_mod.ScanTaskManager(service_factory=lambda top: SlowScanService())
    started = mgr.start(pool="watchlist")
    result = mgr.cancel(started["task_id"])
    assert result["cancelled"] is True

    ended = _wait(mgr, started["task_id"])
    assert ended["status"] == "cancelled"


def test_cancel_unknown_task(manager):
    assert manager.cancel("nope")["cancelled"] is False


def test_get_unknown_returns_none(manager):
    assert manager.get("nope") is None
    assert manager.current() is None


def test_service_honours_cancel_event_in_prefilter(monkeypatch, isolate_config):
    """服务层在预筛批次边界中止，不落库"""
    import app.services.market_scan_service as scan_mod

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        def quote(self, *codes, **kw):
            return {c: {"name": "甲", "price": 10.0, "amount": 9000,
                        "change_percent": 1.0, "volume": 1000} for c in codes}

    class FakeScreener:
        def __init__(self, screener_config=None):
            pass

        def resolve_pool(self, pool=None):
            return ["sh600001", "sh600002"]

    monkeypatch.setattr(scan_mod, "StockDataClient", FakeClient)
    monkeypatch.setattr(scan_mod, "ScreenerService", FakeScreener)

    import threading
    svc = scan_mod.MarketScanService(config={"save": False}, scope=_scope)
    event = threading.Event()
    event.set()
    with pytest.raises(ScanCancelled):
        svc.run(pool="watchlist", save=False, cancel_event=event)


# ==================== API ====================

class FakeManager:
    def __init__(self):
        self.start_calls = []

    def start(self, pool="", force=False, top=0, exclude_star=None):
        self.start_calls.append((pool, force, top, exclude_star))
        return {"task_id": "task-0001", "already_running": False}

    def get(self, task_id):
        return {"id": task_id, "status": "running", "progress": 42,
                "message": "条件评估 8/20", "phase": "screen", "result": None}

    def current(self):
        return self.get("task-0001")

    def cancel(self, task_id):
        return {"cancelled": True, "task_id": task_id}


class FakeHistoryService:
    def __init__(self, *a, **kw):
        pass

    def list_runs(self, limit=10):
        return [{"id": 1, "run_date": "2026-11-05", "pool": "watchlist",
                 "candidate_count": 9, "hit_count": 3,
                 "duration_seconds": 5.5, "created_at": None}]

    def get_run(self, run_id):
        if run_id == 999:
            return None
        return {"id": run_id, "hits": [], "hit_count": 0}

    def latest(self):
        return {"id": 1, "hits": [], "hit_count": 0}


@pytest.fixture
def client(monkeypatch, isolate_config):
    Base.metadata.drop_all(_engine)
    Base.metadata.create_all(_engine)
    monkeypatch.setattr(api_mod, "WRITE_SCOPE", _scope)
    monkeypatch.setattr(tasks_mod, "SCAN_TASKS", FakeManager())
    monkeypatch.setattr(
        "app.services.market_scan_service.MarketScanService", FakeHistoryService
    )
    return TestClient(api_mod.app, raise_server_exceptions=False)


def _body(cid, **kw):
    return {"client_id": cid, "confirm": True, "pool": "watchlist",
            "force": False, "top": 20, **kw}


def test_start_requires_confirm(client):
    r = client.post("/api/scan/start", json={**_body("scan-client-0001"), "confirm": False})
    assert r.status_code == 400
    assert "确认" in r.json()["error"]


def test_start_returns_task_id(client):
    r = client.post("/api/scan/start", json=_body("scan-client-0002"))
    assert r.status_code == 200
    assert r.json()["data"]["result"]["task_id"] == "task-0001"


def test_start_is_idempotent(client, monkeypatch):
    mgr = tasks_mod.SCAN_TASKS
    body = _body("scan-client-0003")
    r1 = client.post("/api/scan/start", json=body)
    r2 = client.post("/api/scan/start", json=body)

    assert r1.json()["data"]["cached"] is False
    assert r2.json()["data"]["cached"] is True
    assert len(mgr.start_calls) == 1


def test_status_and_cancel(client):
    status = client.get("/api/scan/status?task_id=task-0001").json()["data"]["task"]
    assert status["progress"] == 42 and status["status"] == "running"

    current = client.get("/api/scan/status").json()["data"]["task"]
    assert current["id"] == "task-0001"

    cancelled = client.post("/api/scan/cancel?task_id=task-0001").json()["data"]
    assert cancelled["cancelled"] is True


def test_history_and_run_detail(client):
    rows = client.get("/api/scan/runs?limit=5").json()["data"]["rows"]
    assert rows[0]["hit_count"] == 3

    run = client.get("/api/scan/run/1").json()["data"]["run"]
    assert run["id"] == 1

    assert client.get("/api/scan/run/999").status_code == 404
    assert client.get("/api/scan/latest").json()["data"]["run"]["id"] == 1


def test_start_passes_exclude_star(client, monkeypatch):
    mgr = tasks_mod.SCAN_TASKS
    r = client.post("/api/scan/start", json={
        **_body("scan-client-0010"), "exclude_star": True,
    })
    assert r.status_code == 200
    assert mgr.start_calls[-1][3] is True

    r2 = client.post("/api/scan/start", json={
        **_body("scan-client-0011"), "exclude_star": False,
    })
    assert r2.status_code == 200
    assert mgr.start_calls[-1][3] is False


def test_scan_config_endpoint(client, isolate_config):
    isolate_config["market_scan"] = {"exclude_star": True, "top_n": 7}
    d = client.get("/api/scan/config").json()["data"]
    assert d["exclude_star"] is True and d["top_n"] == 7


def test_frontend_scan_page_is_wired(client):
    html = client.get("/").text
    for marker in ("data-tab=\"scan\"", "panel-scan", "scan-progress",
                   "scan-hits", "scan-history", "scan-exclude-star",
                   "/static/scan.js"):
        assert marker in html, f"index.html 缺少 {marker}"

    order = [html.index("/static/" + n) for n in
             ("app.js", "ux.js", "p1.js", "p2.js", "detail.js", "scan.js")]
    assert order == sorted(order)


def test_scan_hits_have_quick_add_watchlist(client):
    """市场摘选命中行要能一键加自选，且沿用 confirm + 幂等键"""
    html = client.get("/").text
    assert "<th>操作</th>" in html

    js = client.get("/static/scan.js").text
    for marker in ("button[data-watch]", "data-watch=", "/api/write/watchlist",
                   "/api/code-picker", "refreshWatched", "addWatchFromScan",
                   "confirm: true", "client_id: newId()", "已自选",
                   "e.stopPropagation()"):
        assert marker in js, f"scan.js 缺少 {marker}"

    js = client.get("/static/scan.js").text
    for marker in ("/api/scan/start", "/api/scan/status", "/api/scan/cancel",
                   "/api/scan/runs", "/api/scan/run/", "/api/scan/config",
                   "register('scan'", "startPolling", "loadResult",
                   "td.stock-link", "exclude_star", "star_excluded"):
        assert marker in js, f"scan.js 缺少 {marker}"

    ux_js = client.get("/static/ux.js").text
    assert "['scan', '市场摘选']" in ux_js

    css = client.get("/static/style.css").text
    assert ".scan-bar" in css

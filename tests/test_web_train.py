"""AI 预测：缺模型时的「准备模型」后台训练流程"""

import time
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
import app.web.api as api_mod
import app.web.train_tasks as train_mod
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


class FakePredictor:
    calls = []

    def train(self, code, use_dl=False, dl_arch="lstm"):
        FakePredictor.calls.append((code, use_dl, dl_arch))
        return {"ml": {"accuracy": 0.61}}


class SlowPredictor(FakePredictor):
    def train(self, code, use_dl=False, dl_arch="lstm"):
        time.sleep(0.3)
        return super().train(code, use_dl, dl_arch)


@pytest.fixture
def manager():
    FakePredictor.calls = []
    return train_mod.TrainTaskManager(service_factory=lambda: FakePredictor())


def _wait(manager, task_id, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        task = manager.get(task_id)
        if task and task["status"] != "running" and task["finished_at"]:
            return task
        time.sleep(0.02)
    return manager.get(task_id)


def test_train_task_completes(manager):
    started = manager.start("600519")
    assert started["already_running"] is False

    task = _wait(manager, started["task_id"])
    assert task["status"] == "done"
    assert task["code"] == "sh600519"          # 自动补全前缀
    assert task["result"]["ml"]["accuracy"] == 0.61
    assert task["finished_at"]
    assert FakePredictor.calls == [("sh600519", False, "lstm")]


def test_train_rejects_index_codes(manager):
    with pytest.raises(ValueError, match="指数不参与模型训练"):
        manager.start("sh000001")


def test_train_rejects_empty_code(manager):
    with pytest.raises(ValueError):
        manager.start("")


def test_second_start_reports_already_running():
    mgr = train_mod.TrainTaskManager(service_factory=lambda: SlowPredictor())
    first = mgr.start("sh600519")
    second = mgr.start("sz000001")

    assert second["already_running"] is True
    assert second["task_id"] == first["task_id"]
    _wait(mgr, first["task_id"])


def test_train_failure_is_captured():
    class BrokenPredictor:
        def train(self, *a, **kw):
            raise RuntimeError("行情不可用")

    mgr = train_mod.TrainTaskManager(service_factory=lambda: BrokenPredictor())
    task = _wait(mgr, mgr.start("sh600519")["task_id"])
    assert task["status"] == "failed" and "行情不可用" in task["error"]


def test_get_unknown_task(manager):
    assert manager.get("nope") is None


# ==================== API ====================

class FakeManager:
    def __init__(self):
        self.start_calls = []

    def start(self, code="", use_dl=False):
        self.start_calls.append((code, use_dl))
        return {"task_id": "train-0001", "already_running": False}

    def get(self, task_id):
        return {"id": task_id, "code": "sh600519", "status": "running",
                "phase": "training", "message": "正在训练…", "result": None}

    def current(self):
        return None


@pytest.fixture
def client(monkeypatch, isolate_config, tmp_path):
    Base.metadata.drop_all(_engine)
    Base.metadata.create_all(_engine)
    monkeypatch.setattr(api_mod, "WRITE_SCOPE", _scope)
    monkeypatch.setattr(train_mod, "TRAIN_TASKS", FakeManager())
    isolate_config["ai"] = {"model": {"save_dir": str(tmp_path / "models")}}
    return TestClient(api_mod.app, raise_server_exceptions=False)


def _body(cid, **kw):
    return {"client_id": cid, "confirm": True, "code": "600519",
            "use_dl": False, **kw}


def test_train_requires_confirm(client):
    r = client.post("/api/predict/train", json={
        **_body("train-client-0001"), "confirm": False,
    })
    assert r.status_code == 400 and "确认" in r.json()["error"]


def test_train_returns_task_id(client):
    r = client.post("/api/predict/train", json=_body("train-client-0002"))
    assert r.status_code == 200
    assert r.json()["data"]["result"]["task_id"] == "train-0001"
    assert train_mod.TRAIN_TASKS.start_calls[-1] == ("600519", False)


def test_train_is_idempotent(client):
    mgr = train_mod.TRAIN_TASKS
    body = _body("train-client-0003")
    r1 = client.post("/api/predict/train", json=body)
    r2 = client.post("/api/predict/train", json=body)
    assert r1.json()["data"]["cached"] is False
    assert r2.json()["data"]["cached"] is True
    assert len(mgr.start_calls) == 1


def test_train_invalid_code_returns_400(client, monkeypatch):
    monkeypatch.setattr(train_mod.TRAIN_TASKS, "start",
                        lambda code, use_dl=False: train_mod.TrainTaskManager.validate_code(code))
    r = client.post("/api/predict/train", json=_body("train-client-0004", code="sh000001"))
    assert r.status_code == 400


def test_train_status(client):
    d = client.get("/api/predict/train/status?task_id=train-0001").json()["data"]
    assert d["task"]["status"] == "running" and d["task"]["phase"] == "training"


def test_model_status_no_model(client):
    d = client.get("/api/predict/model-status?code=600519").json()["data"]
    assert d["code"] == "sh600519" and d["ready"] is False
    assert d["can_train"] is True and d["training"] is False


def test_model_status_with_model(client, tmp_path):
    ml_dir = tmp_path / "models" / "ml"
    ml_dir.mkdir(parents=True, exist_ok=True)
    (ml_dir / "sh600519_xgb_20261105.joblib").write_bytes(b"fake")
    (ml_dir / "sh600519_rf_20261105.joblib").write_bytes(b"fake")

    d = client.get("/api/predict/model-status?code=sh600519").json()["data"]
    assert d["ready"] is True and len(d["models"]) == 2


def test_model_status_index_cannot_train(client):
    d = client.get("/api/predict/model-status?code=sh000001").json()["data"]
    assert d["can_train"] is False


def test_frontend_wires_model_preparation(client):
    js = client.get("/static/p1.js").text
    for marker in ("/api/predict/train", "/api/predict/train/status",
                   "/api/predict/model-status", "renderModelMissing",
                   "checkModelStatus", "startTraining", "pollTraining",
                   "predict-train-btn"):
        assert marker in js, f"p1.js 缺少 {marker}"

    css = client.get("/static/style.css").text
    assert ".model-missing" in css

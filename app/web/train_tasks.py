"""AI 预测模型训练的进程内后台任务

Web 侧预测固定 auto_train=False（不隐式训练）；缺模型时用户点「准备模型」，
这里在后台线程调用 PredictorService.train()，前端轮询状态，完成后自动重预测。

训练本身没有可细分的进度回调，所以用阶段 + 心跳式提示，不伪造百分比。
训练一旦开始不可中断（会写模型文件），因此不提供取消接口。
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime
from typing import Callable, Optional

from app.models.stock import is_index_code, normalize_stock_code

logger = logging.getLogger(__name__)


class TrainTask:
    def __init__(self, code: str, use_dl: bool):
        self.id = uuid.uuid4().hex[:12]
        self.code = code
        self.use_dl = use_dl
        self.status = "running"          # running / done / failed
        self.phase = "starting"          # starting / training / done / failed
        self.message = "正在准备训练数据…"
        self.error = ""
        self.result: Optional[dict] = None
        self.started_at = datetime.now().isoformat(timespec="seconds")
        self.finished_at: Optional[str] = None
        self.thread: Optional[threading.Thread] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "code": self.code,
            "use_dl": self.use_dl,
            "status": self.status,
            "phase": self.phase,
            "message": self.message,
            "error": self.error,
            "result": self.result,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class TrainTaskManager:
    """同一时刻只允许一个训练任务；保留最近 20 个状态"""

    MAX_KEEP = 20

    def __init__(self, service_factory: Optional[Callable] = None):
        self._tasks: dict[str, TrainTask] = {}
        self._lock = threading.Lock()
        self._current: Optional[str] = None
        self._service_factory = service_factory

    @staticmethod
    def validate_code(code: str) -> str:
        norm = normalize_stock_code((code or "").strip())
        if not norm:
            raise ValueError("请填股票代码")
        if is_index_code(norm):
            raise ValueError(f"指数不参与模型训练：{norm}")
        return norm

    def _make_service(self):
        if self._service_factory:
            return self._service_factory()
        from app.ai.predictor_service import PredictorService

        return PredictorService()

    def start(self, code: str, use_dl: bool = False) -> dict:
        norm_code = self.validate_code(code)
        with self._lock:
            if self._current:
                current = self._tasks.get(self._current)
                if current and current.status == "running":
                    return {
                        "task_id": current.id,
                        "already_running": True,
                        "running_code": current.code,
                    }

            task = TrainTask(code=norm_code, use_dl=use_dl)
            self._tasks[task.id] = task
            self._current = task.id
            if len(self._tasks) > self.MAX_KEEP:
                oldest = sorted(self._tasks.values(), key=lambda t: t.started_at)[0]
                self._tasks.pop(oldest.id, None)

            thread = threading.Thread(
                target=self._run, args=(task,), daemon=True,
                name=f"train-{task.id}",
            )
            task.thread = thread
            thread.start()
        return {"task_id": task.id, "already_running": False}

    def _run(self, task: TrainTask) -> None:
        try:
            task.phase = "training"
            task.message = (
                f"正在训练 {task.code} 的 XGBoost / RandomForest 模型"
                + ("与 LSTM" if task.use_dl else "")
                + "（首次需拉取历史行情，可能几分钟）…"
            )
            svc = self._make_service()
            result = svc.train(task.code, use_dl=task.use_dl, dl_arch="lstm")
            task.result = result
            task.status = "done"
            task.phase = "done"
            task.message = f"{task.code} 模型训练完成"
            logger.info(f"训练任务 {task.id} 完成: {task.code}")
        except Exception as e:
            task.status = "failed"
            task.phase = "failed"
            task.error = str(e)
            task.message = f"训练失败：{e}"
            logger.warning(f"训练任务 {task.id} 失败: {e}")
        finally:
            task.finished_at = datetime.now().isoformat(timespec="seconds")
            with self._lock:
                if self._current == task.id:
                    self._current = None

    def get(self, task_id: str) -> Optional[dict]:
        with self._lock:
            task = self._tasks.get(task_id)
            return task.to_dict() if task else None

    def current(self) -> Optional[dict]:
        with self._lock:
            if not self._current:
                return None
            task = self._tasks.get(self._current)
            return task.to_dict() if task else None


TRAIN_TASKS = TrainTaskManager()

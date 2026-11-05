"""全市场摘选的进程内后台任务管理

不引入 Celery/Redis：Web 服务是单机单用户，一个 daemon 线程 + 状态字典即可。
任务状态只在进程内保存，服务重启后历史结果仍可从 screen_runs 表读取。

两阶段进度：
    预筛  0~40%（批量 quote）
    评估 40~95%（候选 K 线 + 条件）
    落库 95~100%
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime
from typing import Callable, Optional

from app.config import get_config

logger = logging.getLogger(__name__)


class ScanTask:
    def __init__(self, pool: str, force: bool, top: int, exclude_star=None):
        self.id = uuid.uuid4().hex[:12]
        self.pool = pool
        self.force = force
        self.top = top
        self.exclude_star = exclude_star
        self.status = "running"          # running / done / failed / cancelled
        self.phase = "starting"          # starting / prefilter / screen / saving
        self.progress = 0
        self.processed = 0
        self.total = 0
        self.found = 0
        self.message = "正在启动…"
        self.error = ""
        self.result: Optional[dict] = None
        self.cancel_event = threading.Event()
        self.started_at = datetime.now().isoformat(timespec="seconds")
        self.finished_at: Optional[str] = None
        self.thread: Optional[threading.Thread] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "pool": self.pool,
            "exclude_star": self.exclude_star,
            "status": self.status,
            "phase": self.phase,
            "progress": self.progress,
            "processed": self.processed,
            "total": self.total,
            "found": self.found,
            "message": self.message,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "result": self.result,
        }


class ScanTaskManager:
    """同一时刻只允许一个扫描任务；保留最近 20 个任务状态"""

    MAX_KEEP = 20

    def __init__(self, service_factory: Optional[Callable] = None):
        self._tasks: dict[str, ScanTask] = {}
        self._lock = threading.Lock()
        self._current: Optional[str] = None
        self._service_factory = service_factory

    def _make_service(self, top: int, exclude_star=None):
        factory = self._service_factory
        if factory:
            return factory(top)
        from app.services.market_scan_service import MarketScanService

        cfg = dict(get_config().get("market_scan", {}) or {})
        if top > 0:
            cfg["top_n"] = top
        if exclude_star is not None:
            cfg["exclude_star"] = bool(exclude_star)
        return MarketScanService(config=cfg)

    def start(
        self, pool: str = "", force: bool = False, top: int = 0, exclude_star=None
    ) -> dict:
        with self._lock:
            if self._current:
                current = self._tasks.get(self._current)
                if current and current.status == "running":
                    return {"task_id": current.id, "already_running": True}

            task = ScanTask(
                pool=pool, force=force, top=top, exclude_star=exclude_star
            )
            self._tasks[task.id] = task
            self._current = task.id
            # 只保留最近若干个任务状态
            if len(self._tasks) > self.MAX_KEEP:
                oldest = sorted(self._tasks.values(), key=lambda t: t.started_at)[0]
                self._tasks.pop(oldest.id, None)

            thread = threading.Thread(
                target=self._run, args=(task,), daemon=True, name=f"scan-{task.id}",
            )
            task.thread = thread
            thread.start()
        return {"task_id": task.id, "already_running": False}

    def _run(self, task: ScanTask) -> None:
        from app.services.market_scan_service import ScanCancelled

        def prefilter_cb(done: int, total: int, found: int):
            task.phase = "prefilter"
            task.processed, task.total, task.found = done, total, found
            task.progress = min(40, round(done / max(1, total) * 40))
            task.message = f"预筛行情 {done}/{total}，通过 {found} 只"

        def screen_cb(done: int, total: int, found: int):
            task.phase = "screen"
            task.processed, task.total, task.found = done, total, found
            task.progress = min(95, 40 + round(done / max(1, total) * 55))
            task.message = f"条件评估 {done}/{total}，命中 {found} 只"

        try:
            svc = self._make_service(task.top, task.exclude_star)
            task.message = "开始扫描…"
            result = svc.run(
                pool=task.pool or None,
                force=task.force,
                save=True,
                prefilter_cb=prefilter_cb,
                screen_cb=screen_cb,
                cancel_event=task.cancel_event,
            )
            task.phase = "saving"
            task.progress = 98
            task.result = result
            task.status = "done"
            task.progress = 100
            task.phase = "done"
            task.message = (
                f"完成：命中 {result.get('hit_count', 0)} 只"
                + ("（复用今日缓存）" if result.get("cached") else "")
            )
        except ScanCancelled as e:
            task.status = "cancelled"
            task.phase = "cancelled"
            task.message = str(e) or "已取消"
            logger.info(f"扫描任务 {task.id} 已取消")
        except Exception as e:
            task.status = "failed"
            task.phase = "failed"
            task.error = str(e)
            task.message = f"扫描失败：{e}"
            logger.warning(f"扫描任务 {task.id} 失败: {e}")
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

    def cancel(self, task_id: str) -> dict:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return {"cancelled": False, "error": "任务不存在"}
            if task.status != "running":
                return {"cancelled": False, "error": f"任务已结束（{task.status}）"}
        task.cancel_event.set()
        task.message = "正在取消（等待当前批次结束）…"
        return {"cancelled": True, "task_id": task_id}


SCAN_TASKS = ScanTaskManager()

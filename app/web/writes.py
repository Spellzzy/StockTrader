"""Web 写操作守卫：二次确认 + 幂等

设计要点:
    1. `confirm` 必须为 true，否则直接拒绝（前端必须勾选「确认执行」）
    2. 每个请求带前端生成的 client_id；重复提交返回首次结果，不重复执行
    3. 同一个 client_id 换了 payload -> 拒绝，避免误复用
    4. 业务执行结果落 web_writes 表，进程重启后幂等依然有效
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.database import session_scope
from app.models.web_write import WebWriteRecord

logger = logging.getLogger(__name__)


class WriteRejected(Exception):
    """未确认 / 参数不合法"""


class WriteConflict(Exception):
    """幂等键冲突或上一次仍在处理中"""


def _hash(payload: dict) -> str:
    body = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _mark(client_id: str, status: str, result: Any, scope=None) -> None:
    ctx = scope or session_scope
    with ctx() as session:
        record = session.execute(
            select(WebWriteRecord).where(WebWriteRecord.client_id == client_id)
        ).scalar_one_or_none()
        if record:
            record.status = status
            record.result_json = json.dumps(result, ensure_ascii=False, default=str)
            record.updated_at = datetime.now()


def execute_write(
    *,
    client_id: str,
    endpoint: str,
    payload: dict,
    fn: Callable[[], Any],
    scope: Callable | None = None,
) -> dict:
    """执行一个受保护的写操作

    Args:
        client_id: 前端生成的幂等键
        endpoint: 写操作标识
        payload: 完整请求体（用于哈希校验）
        fn: 真正的业务函数（同步）

    Returns:
        {"cached": bool, "result": ...}
    """
    if not payload.get("confirm"):
        raise WriteRejected("写操作需要显式确认（请勾选「确认执行」）")
    if not client_id or len(client_id) < 8:
        raise WriteRejected("缺少有效的幂等键 client_id")

    digest = _hash({k: v for k, v in payload.items() if k != "confirm"})
    ctx = scope or session_scope

    with ctx() as session:
        existing = session.execute(
            select(WebWriteRecord).where(WebWriteRecord.client_id == client_id)
        ).scalar_one_or_none()

        if existing:
            if existing.payload_hash != digest:
                raise WriteConflict("同一幂等键对应了不同的请求内容")
            if existing.status == "done":
                return {
                    "cached": True,
                    "result": json.loads(existing.result_json or "{}"),
                }
            if existing.status == "pending":
                raise WriteConflict("上一次请求仍在处理中，请勿重复提交")
            # failed：允许用同一个 client_id 重试
            existing.status = "pending"
        else:
            try:
                session.add(WebWriteRecord(
                    client_id=client_id,
                    endpoint=endpoint,
                    payload_hash=digest,
                    status="pending",
                ))
                session.flush()
            except IntegrityError:
                session.rollback()
                raise WriteConflict("并发提交，请稍后重试")

    try:
        result = fn()
    except Exception as e:
        _mark(client_id, "failed", {"error": str(e)}, scope=ctx)
        logger.warning(f"写操作失败 [{endpoint}] {client_id}: {e}")
        raise

    _mark(client_id, "done", result, scope=ctx)
    return {"cached": False, "result": result}

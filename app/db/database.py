"""数据库连接管理"""

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.config import get_db_path
from app.models.base import Base

# 全局引擎和会话工厂
_engine = None
_SessionFactory = None


def get_engine():
    """获取数据库引擎（单例）"""
    global _engine
    if _engine is None:
        db_path = get_db_path()
        # 确保目录存在
        os.makedirs(Path(db_path).parent, exist_ok=True)
        _engine = create_engine(
            f"sqlite:///{db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )
    return _engine


def get_session_factory():
    """获取会话工厂（单例）"""
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine())
    return _SessionFactory


def get_session() -> Session:
    """获取一个新的数据库会话"""
    factory = get_session_factory()
    return factory()


@contextmanager
def session_scope() -> Iterator[Session]:
    """会话作用域：自动提交 / 回滚 / 关闭

    Usage:
        with session_scope() as session:
            session.add(obj)
    """
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ensure_alert_cooldown_column(engine=None):
    """幂等地为 alerts 表补上 cooldown_minutes 列

    P2 引入 Alembic 之后，这类补列逻辑统一交给迁移管理。
    """
    from sqlalchemy import inspect, text

    engine = engine or get_engine()
    columns = {c["name"] for c in inspect(engine).get_columns("alerts")}
    if "cooldown_minutes" in columns:
        return False

    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE alerts ADD COLUMN cooldown_minutes INTEGER"))
    return True


def ensure_portfolio_override_columns(engine=None):
    """幂等为 portfolio 表补上手工校正列

    create_all 不会给已存在的表加列，而用户库通常不是新建的，
    所以运行时必须显式补列（与 alerts.cooldown_minutes 同一套做法）。
    """
    from sqlalchemy import inspect, text

    engine = engine or get_engine()
    columns = {c["name"] for c in inspect(engine).get_columns("portfolio")}
    statements = []
    if "manual_override" not in columns:
        statements.append("ALTER TABLE portfolio ADD COLUMN manual_override BOOLEAN DEFAULT 0")
    if "override_note" not in columns:
        statements.append("ALTER TABLE portfolio ADD COLUMN override_note TEXT")
    if "override_at" not in columns:
        statements.append("ALTER TABLE portfolio ADD COLUMN override_at DATETIME")

    if not statements:
        return False
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
    return True


def init_db():
    """初始化数据库（创建所有表）"""
    # 导入所有模型以确保它们注册到 Base
    import app.models  # noqa: F401
    engine = get_engine()
    Base.metadata.create_all(engine)
    ensure_alert_cooldown_column(engine)
    ensure_portfolio_override_columns(engine)

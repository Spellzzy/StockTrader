"""数据库连接管理"""

import os
from pathlib import Path
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


def init_db():
    """初始化数据库（创建所有表）"""
    # 导入所有模型以确保它们注册到 Base
    import app.models  # noqa: F401
    engine = get_engine()
    Base.metadata.create_all(engine)
    ensure_alert_cooldown_column(engine)

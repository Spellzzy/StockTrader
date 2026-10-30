"""Alembic 环境配置

数据库地址优先取 config.yaml 的 database.path，其次用 alembic.ini 里的值，
保证迁移和运行时用的是同一个库。

常用命令:
    alembic revision --autogenerate -m "说明"   # 生成迁移
    alembic upgrade head                        # 升级
    alembic current                             # 查看当前版本
    alembic stamp head                          # 已有库标记为最新（不执行迁移）
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

import app.models  # noqa: F401  确保全部 ORM 模型注册
from app.models.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    try:
        from app.config import get_db_path

        path = get_db_path()
    except Exception:
        path = None

    if not path:
        return config.get_main_option("sqlalchemy.url")
    return f"sqlite:///{path}"


def run_migrations_offline() -> None:
    """离线模式：只生成 SQL，不连库"""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # SQLite 需要 batch 模式才能做 ALTER
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：连库执行"""
    engine = create_engine(_database_url(), connect_args={"check_same_thread": False})

    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

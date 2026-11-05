"""全市场摘选扫描记录"""

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ScreenRun(Base):
    """一次全市场摘选的结果快照

    同一天 + 同一参数哈希只保留一条，日报/定时脚本可直接复用，
    避免重复跑几十分钟的全市场扫描。
    """

    __tablename__ = "screen_runs"
    __table_args__ = (
        UniqueConstraint("run_date", "params_hash", name="uq_screen_runs_date_params"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    pool: Mapped[str] = mapped_column(String(64), nullable=False)
    params_hash: Mapped[str] = mapped_column(String(32), nullable=False)
    universe_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scanned_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    top_n: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    result_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)

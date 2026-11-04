"""Web 写操作幂等日志"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WebWriteRecord(Base):
    """记录每个 client_id 的写操作结果

    同一个 client_id 重复提交时直接返回首次结果，避免网络重试/双击造成
    重复下单、重复录入交易。
    """

    __tablename__ = "web_writes"
    __table_args__ = (UniqueConstraint("client_id", name="uq_web_writes_client_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True, comment="前端生成的幂等键"
    )
    endpoint: Mapped[str] = mapped_column(String(80), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", comment="pending / done / failed"
    )
    result_json: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )

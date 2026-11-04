"""订单与订单事件 ORM 模型"""

from datetime import datetime

from sqlalchemy import String, Float, Integer, DateTime, Text, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class OrderRecord(Base):
    """订单表

    client_order_id 唯一索引是幂等的关键：同一信号重复提交只会命中同一行。
    """

    __tablename__ = "orders"
    __table_args__ = (UniqueConstraint("client_order_id", name="uq_orders_client_order_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_order_id: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True, comment="幂等键"
    )

    code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=True)
    side: Mapped[str] = mapped_column(String(10), nullable=False, comment="buy / sell")
    price: Mapped[float] = mapped_column(Float, nullable=False, comment="委托价")
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, comment="委托量(股)")

    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True, default="created")
    filled_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    filled_price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    strategy: Mapped[str] = mapped_column(String(50), nullable=True, comment="信号来源策略")
    bar_date: Mapped[str] = mapped_column(String(20), nullable=True, comment="信号 K 线日期")
    broker: Mapped[str] = mapped_column(String(30), nullable=False, default="manual")
    dry_run: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="True=草稿，未真实提交"
    )
    note: Mapped[str] = mapped_column(Text, nullable=True)

    submitted_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )

    def __repr__(self) -> str:
        return f"<Order({self.client_order_id}, {self.side} {self.code} x{self.quantity}, {self.status})>"


class OrderEventRecord(Base):
    """订单状态变更审计"""

    __tablename__ = "order_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_order_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    from_status: Mapped[str] = mapped_column(String(24), nullable=True)
    to_status: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)

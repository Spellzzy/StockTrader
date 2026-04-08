"""股票信息模型"""

from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Stock(Base):
    """股票基本信息表（本地缓存）"""
    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 基本信息
    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True, comment="股票代码(含前缀)")
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="股票名称")
    market: Mapped[str] = mapped_column(String(10), nullable=False, comment="市场: A/HK/US")
    market_name: Mapped[str] = mapped_column(String(50), nullable=True, comment="板块名(上海主板/深圳创业板等)")

    # 行业信息
    industry: Mapped[str] = mapped_column(String(50), nullable=True, comment="所属行业")
    sector: Mapped[str] = mapped_column(String(50), nullable=True, comment="所属板块")

    # 关注/标记
    is_watched: Mapped[bool] = mapped_column(default=False, comment="是否在自选列表")
    watch_note: Mapped[str] = mapped_column(Text, nullable=True, comment="自选备注")

    # 元数据
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self) -> str:
        return f"<Stock(code={self.code}, name={self.name}, market={self.market})>"

    @staticmethod
    def parse_market(code: str) -> str:
        """根据代码前缀判断市场类型"""
        if code.startswith("sh") or code.startswith("sz"):
            return "A"
        elif code.startswith("hk"):
            return "HK"
        elif code.startswith("us"):
            return "US"
        else:
            return "A"

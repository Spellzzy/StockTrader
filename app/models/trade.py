"""交易记录模型"""

from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, Text, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
import enum

from app.models.base import Base


class TradeAction(str, enum.Enum):
    """交易动作"""
    BUY = "buy"
    SELL = "sell"


class MarketType(str, enum.Enum):
    """市场类型"""
    A_SHARE = "A"       # A股（沪深）
    HK_SHARE = "HK"    # 港股
    US_SHARE = "US"     # 美股


class Trade(Base):
    """交易记录表"""
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 股票信息
    stock_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True, comment="股票代码(含市场前缀: sh600519)")
    stock_name: Mapped[str] = mapped_column(String(50), nullable=True, comment="股票名称")
    market: Mapped[str] = mapped_column(String(10), nullable=False, default="A", comment="市场类型: A/HK/US")

    # 交易信息
    action: Mapped[str] = mapped_column(String(10), nullable=False, comment="交易动作: buy/sell")
    price: Mapped[float] = mapped_column(Float, nullable=False, comment="成交价格")
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, comment="成交数量(股)")
    amount: Mapped[float] = mapped_column(Float, nullable=False, comment="成交金额")
    commission: Mapped[float] = mapped_column(Float, nullable=True, default=0.0, comment="手续费")
    tax: Mapped[float] = mapped_column(Float, nullable=True, default=0.0, comment="印花税")

    # 交易时间
    trade_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, comment="交易时间")

    # 交易理由与备注
    reason: Mapped[str] = mapped_column(Text, nullable=True, comment="交易理由")
    strategy: Mapped[str] = mapped_column(String(50), nullable=True, comment="所用策略")
    tags: Mapped[str] = mapped_column(String(200), nullable=True, comment="标签(逗号分隔)")
    note: Mapped[str] = mapped_column(Text, nullable=True, comment="备注")

    # 关联信息（卖出时可关联买入记录）
    related_trade_id: Mapped[int] = mapped_column(Integer, nullable=True, comment="关联的交易ID(卖出关联买入)")

    # 盈亏信息（卖出时自动计算）
    profit: Mapped[float] = mapped_column(Float, nullable=True, comment="盈亏金额")
    profit_rate: Mapped[float] = mapped_column(Float, nullable=True, comment="盈亏比例(%)")
    holding_days: Mapped[int] = mapped_column(Integer, nullable=True, comment="持仓天数")

    # 元数据
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self) -> str:
        return (
            f"<Trade(id={self.id}, {self.action.upper()} {self.stock_code} "
            f"{self.stock_name or ''} @ {self.price} x {self.quantity})>"
        )

    @property
    def net_amount(self) -> float:
        """净成交金额（扣除手续费和税）"""
        fees = (self.commission or 0) + (self.tax or 0)
        if self.action == TradeAction.BUY.value:
            return self.amount + fees
        else:
            return self.amount - fees

"""持仓记录模型"""

from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PortfolioRecord(Base):
    """持仓记录表（根据交易记录自动维护）"""
    __tablename__ = "portfolio"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 股票信息
    stock_code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True, comment="股票代码")
    stock_name: Mapped[str] = mapped_column(String(50), nullable=True, comment="股票名称")
    market: Mapped[str] = mapped_column(String(10), nullable=False, comment="市场类型")

    # 持仓信息
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="当前持仓数量(股)")
    avg_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, comment="平均成本价")
    total_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, comment="总成本")

    # 首次买入信息
    first_buy_time: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="首次买入时间")
    first_buy_price: Mapped[float] = mapped_column(Float, nullable=True, comment="首次买入价格")

    # 累计盈亏（已平仓部分）
    realized_profit: Mapped[float] = mapped_column(Float, default=0.0, comment="已实现盈亏")
    total_commission: Mapped[float] = mapped_column(Float, default=0.0, comment="累计手续费")
    total_tax: Mapped[float] = mapped_column(Float, default=0.0, comment="累计税费")

    # 交易次数
    buy_count: Mapped[int] = mapped_column(Integer, default=0, comment="买入次数")
    sell_count: Mapped[int] = mapped_column(Integer, default=0, comment="卖出次数")

    # 备注
    note: Mapped[str] = mapped_column(Text, nullable=True, comment="备注")

    # 元数据
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self) -> str:
        return (
            f"<Portfolio({self.stock_code} {self.stock_name or ''} "
            f"qty={self.quantity} avg_cost={self.avg_cost:.2f})>"
        )

    @property
    def is_holding(self) -> bool:
        """是否仍有持仓"""
        return self.quantity > 0

    @property
    def market_value(self) -> float:
        """持仓市值（需传入当前价计算，这里返回成本市值）"""
        return self.quantity * self.avg_cost

    def calc_unrealized_profit(self, current_price: float) -> float:
        """计算未实现盈亏"""
        if self.quantity <= 0:
            return 0.0
        return (current_price - self.avg_cost) * self.quantity

    def calc_unrealized_profit_rate(self, current_price: float) -> float:
        """计算未实现盈亏比例(%)"""
        if self.avg_cost <= 0 or self.quantity <= 0:
            return 0.0
        return (current_price - self.avg_cost) / self.avg_cost * 100

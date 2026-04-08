"""预警规则模型"""

from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column
import enum

from app.models.base import Base


class AlertConditionType(str, enum.Enum):
    """预警条件类型"""
    PRICE_ABOVE = "price_above"          # 价格高于
    PRICE_BELOW = "price_below"          # 价格低于
    CHANGE_ABOVE = "change_above"        # 涨幅超过 (%)
    CHANGE_BELOW = "change_below"        # 跌幅超过 (%)
    VOLUME_ABOVE = "volume_above"        # 成交量超过 (万手)
    RSI_ABOVE = "rsi_above"              # RSI 超买
    RSI_BELOW = "rsi_below"              # RSI 超卖
    MACD_CROSS = "macd_cross"            # MACD 金叉
    MACD_DEAD = "macd_dead"              # MACD 死叉
    KDJ_CROSS = "kdj_cross"             # KDJ 金叉
    BOLL_UPPER = "boll_upper"            # 突破布林上轨
    BOLL_LOWER = "boll_lower"            # 跌破布林下轨
    MA_BULL = "ma_bull"                  # 均线多头排列
    TURNOVER_ABOVE = "turnover_above"    # 换手率超过 (%)


class Alert(Base):
    """预警规则表"""
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 股票信息
    stock_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True, comment="股票代码")
    stock_name: Mapped[str] = mapped_column(String(50), nullable=True, comment="股票名称")

    # 预警条件
    condition_type: Mapped[str] = mapped_column(String(30), nullable=False, comment="条件类型")
    threshold: Mapped[float] = mapped_column(Float, nullable=True, comment="阈值 (价格/百分比等)")
    condition_desc: Mapped[str] = mapped_column(String(200), nullable=True, comment="条件描述(人类可读)")

    # 状态
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    is_triggered: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否已触发")
    trigger_count: Mapped[int] = mapped_column(Integer, default=0, comment="触发次数")
    last_triggered_at: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="最后触发时间")

    # 设置
    repeat: Mapped[bool] = mapped_column(Boolean, default=False, comment="触发后是否继续监控(可重复触发)")
    note: Mapped[str] = mapped_column(Text, nullable=True, comment="备注")

    # 元数据
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self) -> str:
        status = "✅" if self.is_active else "⏸️"
        return f"<Alert({status} {self.stock_code} {self.condition_desc})>"

    @property
    def status_text(self) -> str:
        """状态文字"""
        if not self.is_active:
            return "已暂停"
        if self.is_triggered and not self.repeat:
            return "已触发"
        return "监控中"


class AlertHistory(Base):
    """预警触发历史表"""
    __tablename__ = "alert_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 关联预警规则
    alert_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True, comment="预警规则ID")
    stock_code: Mapped[str] = mapped_column(String(20), nullable=False, comment="股票代码")
    stock_name: Mapped[str] = mapped_column(String(50), nullable=True, comment="股票名称")

    # 触发信息
    condition_type: Mapped[str] = mapped_column(String(30), nullable=False, comment="条件类型")
    condition_desc: Mapped[str] = mapped_column(String(200), nullable=True, comment="条件描述")
    trigger_value: Mapped[float] = mapped_column(Float, nullable=True, comment="触发时的实际值")
    threshold: Mapped[float] = mapped_column(Float, nullable=True, comment="设定阈值")
    message: Mapped[str] = mapped_column(Text, nullable=True, comment="触发消息")

    # 触发时的行情快照
    price: Mapped[float] = mapped_column(Float, nullable=True, comment="触发时价格")
    change_percent: Mapped[float] = mapped_column(Float, nullable=True, comment="触发时涨跌幅")
    volume: Mapped[float] = mapped_column(Float, nullable=True, comment="触发时成交量")

    # 元数据
    triggered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="触发时间")

    def __repr__(self) -> str:
        return f"<AlertHistory(alert_id={self.alert_id}, {self.stock_code} {self.condition_desc})>"

"""通知渠道抽象基类"""

from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


class NotificationLevel(Enum):
    """通知级别"""
    INFO = "info"
    WARNING = "warning"
    ALERT = "alert"       # 预警触发
    TRADE = "trade"       # 交易成交


@dataclass
class NotificationMessage:
    """通知消息体"""
    title: str
    content: str
    level: NotificationLevel = NotificationLevel.ALERT
    stock_code: str = ""
    stock_name: str = ""
    price: Optional[float] = None
    change_percent: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def markdown(self) -> str:
        """生成 Markdown 格式消息"""
        lines = [f"## {self.title}", ""]

        if self.stock_code:
            lines.append(f"**股票**: {self.stock_name or ''} ({self.stock_code})")

        lines.append(f"**详情**: {self.content}")

        if self.price is not None:
            lines.append(f"**当前价**: {self.price:.2f}")
        if self.change_percent is not None:
            sign = "+" if self.change_percent >= 0 else ""
            lines.append(f"**涨跌幅**: {sign}{self.change_percent:.2f}%")

        lines.append(f"**时间**: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        lines.append("---")
        lines.append("*Stock Trader AI · 预警推送*")
        return "\n".join(lines)

    @property
    def plain_text(self) -> str:
        """生成纯文本格式消息"""
        emoji_map = {
            NotificationLevel.ALERT: "🚨",
            NotificationLevel.WARNING: "⚠️",
            NotificationLevel.TRADE: "💰",
            NotificationLevel.INFO: "ℹ️",
        }
        emoji = emoji_map.get(self.level, "📢")

        lines = [f"{emoji} {self.title}", ""]

        if self.stock_code:
            lines.append(f"股票: {self.stock_name or ''} ({self.stock_code})")

        lines.append(f"详情: {self.content}")

        if self.price is not None:
            lines.append(f"当前价: {self.price:.2f}")
        if self.change_percent is not None:
            sign = "+" if self.change_percent >= 0 else ""
            lines.append(f"涨跌幅: {sign}{self.change_percent:.2f}%")

        lines.append(f"时间: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        lines.append("--- Stock Trader AI · 预警推送 ---")
        return "\n".join(lines)


class NotificationChannel(ABC):
    """通知渠道抽象基类

    所有渠道只需实现 name 属性和 send() 方法。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """渠道名称"""
        ...

    @abstractmethod
    async def send(self, message: NotificationMessage) -> bool:
        """发送通知

        Args:
            message: 通知消息体

        Returns:
            True=发送成功, False=发送失败
        """
        ...

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.name}>"

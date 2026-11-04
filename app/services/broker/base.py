"""券商通道抽象

这一层只定义契约，不碰数据库、不碰行情、不连券商。
所有通道（人工 / 模拟盘 / 影子 / 未来的 QMT）都实现同一组方法，
上层 OrderService 因此完全不关心用的是哪家通道。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from app.domain.order import Order, OrderStatus


class BrokerError(Exception):
    """券商通道异常"""


@dataclass
class BrokerResult:
    """统一的通道返回值"""

    ok: bool
    client_order_id: str = ""
    broker_order_id: str = ""
    status: Optional[OrderStatus] = None
    filled_quantity: int = 0
    filled_price: float = 0.0
    message: str = ""
    raw: dict = field(default_factory=dict)


class Broker(ABC):
    """券商通道接口

    实现约定:
        1. `submit()` 必须接受 dry_run，且 dry_run=True 时绝不产生真实委托
        2. 网络超时 / 回报丢失一律返回 UNKNOWN，禁止抛异常后由上层盲目重试
        3. `query_*` 只读，不得有副作用
    """

    name: str = "base"

    @abstractmethod
    def submit(self, order: Order, dry_run: bool = True) -> BrokerResult:
        """提交委托"""

    @abstractmethod
    def cancel(self, order: Order) -> BrokerResult:
        """撤单"""

    @abstractmethod
    def query_order(self, order: Order) -> BrokerResult:
        """查询委托状态"""

    def query_positions(self) -> list[dict]:
        """查询持仓（人工通道无远端数据，返回空）"""
        return []

    def query_account(self) -> dict:
        """查询账户资金"""
        return {}

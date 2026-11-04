"""影子通道：真实行情 + 假成交

用于验证「信号 → 订单 → 风控 → 状态机 → 写库」整条链路，
不发任何真实委托，也不连券商。所有成交都在内存里立即完成。
"""

from __future__ import annotations

from app.domain.order import Order, OrderStatus
from app.services.broker.base import Broker, BrokerResult


class MockBroker(Broker):
    """影子通道（开发/测试用）"""

    name = "mock"

    def __init__(self, fail_on: str = ""):
        self.submitted: list[Order] = []
        self.cancelled: list[Order] = []
        self.fail_on = fail_on  # 设为某个 client_order_id 可模拟提交失败

    def submit(self, order: Order, dry_run: bool = True) -> BrokerResult:
        self.submitted.append(order)

        if self.fail_on == order.client_order_id:
            return BrokerResult(
                ok=False,
                client_order_id=order.client_order_id,
                status=OrderStatus.UNKNOWN,
                message="模拟：提交超时，委托状态不明，禁止重试，请先对账",
            )

        return BrokerResult(
            ok=True,
            client_order_id=order.client_order_id,
            broker_order_id=f"MOCK-{order.client_order_id[:8]}",
            status=OrderStatus.FILLED if not dry_run else OrderStatus.SUBMITTED,
            filled_quantity=0 if dry_run else order.quantity,
            filled_price=0.0 if dry_run else order.price,
            message="影子成交" if not dry_run else "影子提交（未成交）",
        )

    def cancel(self, order: Order) -> BrokerResult:
        self.cancelled.append(order)
        return BrokerResult(
            ok=True,
            client_order_id=order.client_order_id,
            status=OrderStatus.CANCELLED,
            message="影子撤单",
        )

    def query_order(self, order: Order) -> BrokerResult:
        return BrokerResult(
            ok=True,
            client_order_id=order.client_order_id,
            status=order.status,
            message="影子通道状态来自本地",
        )

    def query_positions(self) -> list[dict]:
        return []

    def query_account(self) -> dict:
        return {"cash": 0.0, "note": "影子账户"}

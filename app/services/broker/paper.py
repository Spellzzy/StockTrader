"""模拟盘通道：把现有 PaperBroker 包装成 Broker 接口"""

from __future__ import annotations

from app.domain.order import Order, OrderStatus
from app.services.broker.base import Broker, BrokerResult


class PaperBrokerAdapter(Broker):
    """用模拟盘撮合规则充当券商通道"""

    name = "paper"

    def __init__(self, paper_broker=None):
        if paper_broker is None:
            from app.services.paper_broker import PaperBroker

            paper_broker = PaperBroker()
        self.paper = paper_broker

    def submit(self, order: Order, dry_run: bool = True) -> BrokerResult:
        if dry_run:
            return BrokerResult(
                ok=True,
                client_order_id=order.client_order_id,
                status=OrderStatus.SUBMITTED,
                message="模拟盘 dry-run，未撮合",
            )

        try:
            if order.side.value == "buy":
                filled = self.paper.buy(order.code, order.price, quantity=order.quantity)
            else:
                filled = self.paper.sell(
                    order.code, order.price, quantity=order.quantity, allow_same_day=True
                )
        except Exception as e:
            return BrokerResult(
                ok=False,
                client_order_id=order.client_order_id,
                status=OrderStatus.REJECTED,
                message=f"模拟盘拒单: {e}",
            )

        return BrokerResult(
            ok=True,
            client_order_id=order.client_order_id,
            broker_order_id=f"PAPER-{filled.id}",
            status=OrderStatus.FILLED,
            filled_quantity=filled.quantity,
            filled_price=filled.price,
            message="模拟盘成交",
        )

    def cancel(self, order: Order) -> BrokerResult:
        return BrokerResult(
            ok=True,
            client_order_id=order.client_order_id,
            status=OrderStatus.CANCELLED,
            message="模拟盘即时成交，无需撤单",
        )

    def query_order(self, order: Order) -> BrokerResult:
        return BrokerResult(
            ok=True, client_order_id=order.client_order_id, status=order.status
        )

    def query_positions(self) -> list[dict]:
        return [
            {"code": p.code, "quantity": p.quantity, "avg_cost": p.avg_cost}
            for p in self.paper.positions()
        ]

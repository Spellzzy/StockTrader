"""信号 → 订单编排（纯函数）

把策略/选股产生的信号翻译成订单草稿，在这里完成去重与整手处理。
不放数据库、不放行情请求，方便用历史 K 线做「纸面回放」。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from app.domain.order import (
    LOT_SIZE,
    Order,
    OrderSide,
    OrderStatus,
    make_client_order_id,
)


@dataclass(frozen=True)
class Signal:
    """一条交易信号"""

    code: str
    side: str                     # buy / sell
    price: float                  # 参考价（当前价 / 次日开盘价）
    strategy: str = "manual"
    bar_date: str = ""            # 信号所在 K 线日期，参与幂等键
    name: str = ""
    quantity: int = 0             # 0 = 用 default_quantity
    score: float = 0.0
    reason: str = ""


@dataclass
class PlanResult:
    orders: list[Order] = field(default_factory=list)
    duplicates: int = 0
    skipped: list[str] = field(default_factory=list)

    @property
    def total_amount(self) -> float:
        return sum(o.amount for o in self.orders)


def plan_orders(
    signals: Iterable[Signal],
    default_quantity: int = LOT_SIZE,
    broker: str = "manual",
) -> PlanResult:
    """把信号列表翻译成订单，同一幂等键只保留第一条

    Args:
        signals: 信号列表
        default_quantity: 信号未指定数量时的默认股数（向下取整到整手）
        broker: 通道名
    """
    result = PlanResult()
    seen: set[str] = set()
    lots = max(1, int(default_quantity) // LOT_SIZE) * LOT_SIZE

    for sig in signals:
        side_raw = str(sig.side).lower()
        if side_raw not in ("buy", "sell", "1", "-1"):
            result.skipped.append(f"{sig.code}: 未知方向 {sig.side}")
            continue

        side = OrderSide.SELL if side_raw in ("sell", "-1") else OrderSide.BUY
        price = float(sig.price)
        if price <= 0:
            result.skipped.append(f"{sig.code}: 价格无效 {price}")
            continue

        quantity = int(sig.quantity or lots)
        quantity = max(LOT_SIZE, quantity // LOT_SIZE * LOT_SIZE)

        # seq 固定为 0：幂等键必须跨进程重启保持稳定，不能依赖信号在列表里的位置
        dedupe_key = f"{sig.code}|{side.value}|{sig.strategy}|{sig.bar_date}"
        oid = make_client_order_id(sig.code, side.value, sig.strategy, sig.bar_date, 0)
        if dedupe_key in seen:
            result.duplicates += 1
            continue
        seen.add(dedupe_key)

        result.orders.append(
            Order(
                client_order_id=oid,
                code=sig.code,
                name=sig.name,
                side=side,
                price=price,
                quantity=quantity,
                strategy=sig.strategy,
                bar_date=sig.bar_date,
                broker=broker,
                status=OrderStatus.CREATED,
                note=sig.reason,
                dry_run=True,
            )
        )

    return result

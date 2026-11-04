"""人工确认通道（默认通道）

不连券商、不存账号密码、不自动下单：只把待执行委托写成草稿文件，
由人在券商 App/客户端里自己下单，再用 `stock-ai order fill` 回填成交。

这是零合规风险、零外部依赖的执行层，也是接任何真实通道之前必须先跑通的一层。
"""

from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from app.domain.order import Order, OrderStatus
from app.services.broker.base import Broker, BrokerResult


class ManualBroker(Broker):
    """人工确认通道"""

    name = "manual"

    def __init__(self, draft_dir: str = "./data/orders"):
        self.draft_dir = Path(draft_dir)

    # ==================== 草稿 ====================

    def render_draft(self, orders: Iterable[Order], stamp: str | None = None) -> dict:
        """把订单写成 CSV + Markdown 两份草稿

        Returns:
            {"csv": path, "markdown": path}
        """
        orders = list(orders)
        self.draft_dir.mkdir(parents=True, exist_ok=True)
        stamp = stamp or date.today().strftime("%Y%m%d")

        csv_path = self.draft_dir / f"orders_{stamp}.csv"
        md_path = self.draft_dir / f"orders_{stamp}.md"

        headers = [
            "client_order_id", "code", "name", "side", "price", "quantity",
            "amount", "strategy", "bar_date", "status", "broker", "note",
        ]
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for o in orders:
                writer.writerow([
                    o.client_order_id, o.code, o.name, o.side.value, o.price,
                    o.quantity, round(o.amount, 2), o.strategy, o.bar_date,
                    o.status.value, o.broker, o.note,
                ])

        lines = [
            f"# 待执行委托草稿（{datetime.now():%Y-%m-%d %H:%M}）",
            "",
            "> 本文件仅供参考，不构成投资建议。请人工核对后在券商客户端下单，",
            "> 成交后执行 `stock-ai order fill <订单ID> --price <成交价>` 回填。",
            "",
            f"共 {len(orders)} 笔，合计金额 {sum(o.amount for o in orders):,.2f} 元",
            "",
            "| 序号 | 幂等键 | 代码 | 方向 | 价格 | 数量 | 金额 | 策略 |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for i, o in enumerate(orders, 1):
            lines.append(
                f"| {i} | `{o.client_order_id}` | {o.code} | "
                f"{'买入' if o.side.value == 'buy' else '卖出'} | "
                f"{o.price:.2f} | {o.quantity} | {o.amount:,.2f} | {o.strategy} |"
            )
        lines += ["", "## 执行检查清单", ""]
        lines += [
            "- [ ] 已核对代码、方向、价格、数量",
            "- [ ] 已确认当日累计金额未超风控上限",
            "- [ ] 已在券商客户端完成下单",
            "- [ ] 已回填成交并跑 `stock-ai order reconcile`",
            "",
        ]
        md_path.write_text("\n".join(lines), encoding="utf-8")

        return {"csv": str(csv_path), "markdown": str(md_path)}

    # ==================== 接口实现 ====================

    def submit(self, order: Order, dry_run: bool = True) -> BrokerResult:
        """人工通道的"提交"= 生成草稿并置为待人工执行，永远不产生真实委托"""
        files = self.render_draft([order])
        return BrokerResult(
            ok=True,
            client_order_id=order.client_order_id,
            status=OrderStatus.PENDING_REVIEW,
            message=(
                "已生成人工执行草稿（未向券商提交任何委托）: "
                f"{files['markdown']}"
            ),
            raw=files,
        )

    def cancel(self, order: Order) -> BrokerResult:
        return BrokerResult(
            ok=True,
            client_order_id=order.client_order_id,
            status=OrderStatus.CANCELLED,
            message="人工通道无需远端撤单，只需不执行该草稿",
        )

    def query_order(self, order: Order) -> BrokerResult:
        return BrokerResult(
            ok=True,
            client_order_id=order.client_order_id,
            status=None,
            message="人工通道无远端委托状态，请用 order fill 回填成交或 order reconcile 对账",
        )

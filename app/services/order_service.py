"""订单服务：风控、幂等、状态推进、超时、重启恢复、对账

设计原则:
    1. 默认拒绝真实提交（broker.enabled=False → 只能 dry-run）
    2. 状态不明（UNKNOWN）绝不重下，只能靠对账恢复
    3. 成交回报是唯一写 trades 表的入口，保证与手工录入口径一致
    4. 每次状态变更都写 order_events 审计
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.domain.order import (
    InvalidTransition,
    Order,
    OrderSide,
    OrderStatus,
    RiskLimits,
    is_trading_session,
    make_client_order_id,
    transition,
)
from app.models.order import OrderEventRecord, OrderRecord

logger = logging.getLogger(__name__)

# 允许被超时逻辑处理的"未完成"状态
OPEN_STATUSES = (
    OrderStatus.PENDING_REVIEW.value,
    OrderStatus.SUBMITTED.value,
    OrderStatus.PARTIALLY_FILLED.value,
)


class OrderRejected(Exception):
    """风控或开关拒绝了订单"""


class OrderNotFound(Exception):
    """订单不存在"""


def _to_domain(rec: OrderRecord) -> Order:
    return Order(
        client_order_id=rec.client_order_id,
        code=rec.code,
        name=rec.name or "",
        side=OrderSide(rec.side),
        price=rec.price,
        quantity=rec.quantity,
        strategy=rec.strategy or "",
        bar_date=rec.bar_date or "",
        status=OrderStatus(rec.status),
        filled_quantity=rec.filled_quantity or 0,
        filled_price=rec.filled_price or 0.0,
        broker=rec.broker or "manual",
        dry_run=bool(rec.dry_run),
        note=rec.note or "",
        created_at=rec.created_at or datetime.now(),
        updated_at=rec.updated_at or datetime.now(),
    )


def _sync(rec: OrderRecord, order: Order) -> None:
    rec.status = order.status.value
    rec.filled_quantity = order.filled_quantity
    rec.filled_price = order.filled_price
    rec.dry_run = order.dry_run
    rec.updated_at = datetime.now()


class OrderService:
    """订单服务"""

    def __init__(
        self,
        session: Optional[Session] = None,
        broker=None,
        cfg: Optional[dict] = None,
        calendar=None,
    ):
        if cfg is None:
            from app.config import get_config

            cfg = get_config()
        if calendar is None:
            from app.domain.calendar import get_calendar

            calendar = get_calendar()
        if broker is None:
            from app.services.broker import get_broker

            broker = get_broker(cfg=cfg)

        self._session = session
        self.cfg = cfg
        self.broker = broker
        self.calendar = calendar
        self.limits = RiskLimits.from_config(cfg)

    @property
    def session(self) -> Session:
        if self._session is None:
            from app.db.database import get_session

            self._session = get_session()
        return self._session

    # ==================== 查询 ====================

    def get(self, client_order_id: str) -> Optional[Order]:
        rec = self.session.execute(
            select(OrderRecord).where(OrderRecord.client_order_id == client_order_id)
        ).scalar_one_or_none()
        return _to_domain(rec) if rec else None

    def _get_record(self, client_order_id: str) -> OrderRecord:
        rec = self.session.execute(
            select(OrderRecord).where(OrderRecord.client_order_id == client_order_id)
        ).scalar_one_or_none()
        if rec is None:
            raise OrderNotFound(f"订单不存在: {client_order_id}")
        return rec

    def list_orders(self, status: str = "", limit: int = 50) -> list[Order]:
        stmt = select(OrderRecord).order_by(OrderRecord.created_at.desc()).limit(limit)
        if status:
            stmt = stmt.where(OrderRecord.status == status)
        return [_to_domain(r) for r in self.session.execute(stmt).scalars().all()]

    def events(self, client_order_id: str) -> list[OrderEventRecord]:
        return list(
            self.session.execute(
                select(OrderEventRecord)
                .where(OrderEventRecord.client_order_id == client_order_id)
                .order_by(OrderEventRecord.at)
            ).scalars().all()
        )

    # ==================== 创建（幂等） ====================

    def create_order(
        self,
        code: str,
        side: str,
        price: float,
        quantity: int,
        strategy: str = "manual",
        bar_date: str = "",
        name: str = "",
        note: str = "",
    ) -> tuple[Order, bool]:
        """创建订单；已存在同幂等键的订单直接返回，不再重复创建

        Returns:
            (订单, 是否新建)
        """
        side_value = OrderSide(side).value
        oid = make_client_order_id(code, side_value, strategy, bar_date, 0)
        existing = self.get(oid)
        if existing:
            return existing, False

        order = Order(
            client_order_id=oid,
            code=code,
            name=name,
            side=OrderSide(side),
            price=float(price),
            quantity=int(quantity),
            strategy=strategy,
            bar_date=bar_date or datetime.now().strftime("%Y%m%d"),
            broker=self.broker.name,
            note=note,
        )
        order.validate_shape()

        rec = OrderRecord(
            client_order_id=order.client_order_id,
            code=order.code,
            name=order.name,
            side=order.side.value,
            price=order.price,
            quantity=order.quantity,
            status=order.status.value,
            filled_quantity=0,
            filled_price=0.0,
            strategy=order.strategy,
            bar_date=order.bar_date,
            broker=order.broker,
            dry_run=True,
            note=order.note,
        )
        self.session.add(rec)
        self._event(order.client_order_id, None, OrderStatus.CREATED, "信号生成")
        self.session.commit()
        logger.info(f"订单创建: {oid} {order.side.value} {code} x{quantity} @ {price}")
        return order, True

    def create_from_plan(self, orders: list[Order]) -> tuple[int, int]:
        """批量落库一批编排好的订单，返回 (新建数, 重复数)"""
        created = duplicated = 0
        for order in orders:
            _, is_new = self.create_order(
                code=order.code,
                side=order.side.value,
                price=order.price,
                quantity=order.quantity,
                strategy=order.strategy,
                bar_date=order.bar_date,
                name=order.name,
                note=order.note,
            )
            created += int(is_new)
            duplicated += int(not is_new)
        return created, duplicated

    # ==================== 风控 ====================

    def risk_check(
        self,
        order: Order,
        now: Optional[datetime] = None,
        enforce_session: bool = True,
        total_equity: float = 0.0,
    ) -> list[str]:
        """返回违规原因列表（空 = 通过）"""
        now = now or datetime.now()
        violations = self.limits.check_static(
            order, now, calendar=self.calendar, enforce_session=enforce_session
        )

        # 当日已创建/已提交订单金额
        today_start = datetime.combine(now.date(), datetime.min.time())
        daily_amount = float(
            self.session.execute(
                select(func.coalesce(func.sum(OrderRecord.price * OrderRecord.quantity), 0.0)).where(
                    OrderRecord.created_at >= today_start,
                    OrderRecord.status.notin_([
                        OrderStatus.CANCELLED.value,
                        OrderStatus.REJECTED.value,
                        OrderStatus.EXPIRED.value,
                    ]),
                )
            ).scalar_one()
        )

        # 持仓（只读 DB，不查行情）
        from app.services.portfolio_service import PortfolioService

        try:
            positions = PortfolioService(session=self.session).get_portfolio()
        except Exception as e:
            logger.warning(f"持仓读取失败，跳过持仓类风控: {e}")
            positions = []

        bought_today = False
        if order.side == OrderSide.SELL:
            from app.models.trade import Trade

            bought_today = (
                self.session.execute(
                    select(func.count(Trade.id)).where(
                        Trade.stock_code == order.code,
                        Trade.action == "buy",
                        Trade.trade_time >= today_start,
                    )
                ).scalar_one()
                > 0
            )

        violations += self.limits.check_portfolio(
            order,
            positions=positions,
            daily_amount=daily_amount,
            bought_today=bought_today,
            total_equity=total_equity,
        )
        return violations

    # ==================== 提交 ====================

    def submit(
        self,
        client_order_id: str,
        confirmed: bool = False,
        dry_run: bool = True,
        now: Optional[datetime] = None,
        enforce_session: bool = True,
    ) -> dict:
        """提交订单（默认 dry-run，默认不真实下单）

        Args:
            confirmed: 人工二次确认（真实提交时必填）
            dry_run: True = 只出草稿/影子提交，不产生真实委托
        """
        now = now or datetime.now()
        rec = self._get_record(client_order_id)
        order = _to_domain(rec)

        if order.is_terminal:
            return {"ok": False, "reason": f"订单已终结: {order.status.value}"}
        if order.status == OrderStatus.UNKNOWN:
            # 最危险的场景：提交超时后不知道券商有没有收到，重下 = 重复成交
            return {
                "ok": False,
                "reason": "订单状态不明，禁止重新提交；请对账后用 order fill 或 order cancel 处理",
            }

        # 开关：真实提交必须显式打开 broker.enabled + 人工确认
        if not dry_run:
            if not self.limits.enabled:
                raise OrderRejected(
                    "kill switch 未打开: broker.enabled=false，拒绝真实提交"
                )
            if self.limits.require_confirmation and not confirmed:
                raise OrderRejected("真实提交需要人工二次确认 (--yes)")
            violations = self.risk_check(
                order, now=now, enforce_session=enforce_session
            )
            if violations:
                self._move(order, OrderStatus.REJECTED, "风控拒绝: " + "; ".join(violations))
                self._persist(rec, order)
                raise OrderRejected("; ".join(violations))

        if not dry_run and not is_trading_session(now, self.calendar):
            raise OrderRejected(f"{now:%H:%M} 不在交易时段，拒绝真实提交")

        result = self.broker.submit(order, dry_run=dry_run)

        if result.status is not None:
            try:
                order = self._move(order, result.status, result.message)
            except InvalidTransition as e:
                logger.error(f"通道返回非法状态: {e}")
                order = self._move(order, OrderStatus.UNKNOWN, str(e))

        order.filled_quantity = max(order.filled_quantity, result.filled_quantity)
        order.filled_price = result.filled_price or order.filled_price
        order.dry_run = dry_run
        rec.submitted_at = now
        _sync(rec, order)
        self.session.commit()

        return {
            "ok": result.ok,
            "status": order.status.value,
            "message": result.message,
            "dry_run": dry_run,
            "broker": self.broker.name,
            "raw": result.raw,
        }

    # ==================== 成交回填 ====================

    def fill(
        self,
        client_order_id: str,
        price: float,
        quantity: int = 0,
        write_trade: bool = True,
    ) -> dict:
        """回填成交（人工通道的主要入口），并写 trades 表 + 推送 + 重建持仓"""
        rec = self._get_record(client_order_id)
        order = _to_domain(rec)

        if order.is_terminal:
            raise OrderRejected(f"订单已终结: {order.status.value}，不能回填")

        filled_qty = int(quantity or order.remaining_quantity)
        if filled_qty <= 0 or filled_qty % 100 != 0 or filled_qty > order.remaining_quantity:
            raise OrderRejected(
                f"成交量 {filled_qty} 不合法（须为整手且不超过剩余 {order.remaining_quantity}）"
            )
        if price <= 0:
            raise OrderRejected("成交价必须大于 0")

        order.filled_quantity += filled_qty
        order.filled_price = float(price)
        new_status = (
            OrderStatus.FILLED if order.remaining_quantity == 0
            else OrderStatus.PARTIALLY_FILLED
        )
        order = self._move(order, new_status, f"成交回填 {filled_qty}股 @ {price}")
        _sync(rec, order)
        self.session.commit()

        trade_id = None
        if write_trade:
            from app.services.trade_service import TradeService

            trade = TradeService(session=self.session).add_trade(
                stock_code=order.code,
                action=order.side.value,
                price=order.filled_price,
                quantity=filled_qty,
                stock_name=order.name,
                strategy=order.strategy,
                note=f"order:{order.client_order_id}",
            )
            trade_id = trade.id

            from app.services.portfolio_service import PortfolioService

            try:
                PortfolioService(session=self.session).rebuild_portfolio()
            except Exception as e:
                logger.warning(f"持仓重算失败（成交已记录）: {e}")

        return {
            "ok": True,
            "status": order.status.value,
            "filled_quantity": filled_qty,
            "filled_price": order.filled_price,
            "trade_id": trade_id,
        }

    # ==================== 撤单 / 超时 / 恢复 ====================

    def cancel(self, client_order_id: str, reason: str = "人工撤单") -> Order:
        rec = self._get_record(client_order_id)
        order = _to_domain(rec)
        if order.is_terminal:
            raise OrderRejected(f"订单已终结: {order.status.value}")

        try:
            self.broker.cancel(order)
        except Exception as e:
            logger.warning(f"通道撤单失败（本地仍置为已撤）: {e}")

        order = self._move(order, OrderStatus.CANCELLED, reason)
        _sync(rec, order)
        self.session.commit()
        return order

    def expire_stale(self, now: Optional[datetime] = None) -> list[str]:
        """超时未成交自动撤单/过期"""
        now = now or datetime.now()
        deadline = now - timedelta(minutes=self.limits.timeout_minutes)
        expired: list[str] = []

        records = self.session.execute(
            select(OrderRecord).where(OrderRecord.status.in_(OPEN_STATUSES))
        ).scalars().all()

        for rec in records:
            if (rec.created_at or now) > deadline:
                continue
            order = _to_domain(rec)
            if order.status == OrderStatus.SUBMITTED and not order.dry_run:
                # 真实委托超时 → 状态不明，禁止重下，等对账
                order = self._move(order, OrderStatus.UNKNOWN, "真实委托超时，状态不明")
            else:
                order = self._move(order, OrderStatus.EXPIRED, "草稿超时未执行")
                try:
                    self.broker.cancel(order)
                except Exception:
                    pass
            _sync(rec, order)
            expired.append(order.client_order_id)

        if expired:
            self.session.commit()
        return expired

    def recover_on_startup(self, now: Optional[datetime] = None) -> list[str]:
        """进程重启恢复：把遗留的 SUBMITTED 真实委托标记为 UNKNOWN

        绝不在启动时自动重新提交——那会造成重复成交。
        """
        now = now or datetime.now()
        deadline = now - timedelta(minutes=self.limits.timeout_minutes)
        recovered: list[str] = []

        records = self.session.execute(
            select(OrderRecord).where(
                OrderRecord.status == OrderStatus.SUBMITTED.value,
                OrderRecord.dry_run.is_(False),
            )
        ).scalars().all()

        for rec in records:
            if (rec.submitted_at or rec.created_at or now) > deadline:
                continue
            order = _to_domain(rec)
            order = self._move(order, OrderStatus.UNKNOWN, "重启恢复：委托状态不明，等待对账")
            _sync(rec, order)
            recovered.append(order.client_order_id)

        if recovered:
            self.session.commit()
        return recovered

    # ==================== 对账 ====================

    def reconcile(self) -> dict:
        """对比 FILLED 订单与 trades 表，找出缺失/多余的成交记录

        Manual 通道下这就是「人工回填一致性检查」；接了券商通道后可换成
        券商回报与本地订单的比对。
        """
        from app.models.trade import Trade

        filled = self.session.execute(
            select(OrderRecord).where(
                OrderRecord.status.in_([OrderStatus.FILLED.value, OrderStatus.ARCHIVED.value])
            )
        ).scalars().all()

        missing_trades: list[str] = []
        for rec in filled:
            marker = f"order:{rec.client_order_id}"
            count = self.session.execute(
                select(func.count(Trade.id)).where(Trade.note.like(f"%{marker}%"))
            ).scalar_one()
            if count == 0:
                missing_trades.append(rec.client_order_id)

        linked_trades = self.session.execute(
            select(func.count(Trade.id)).where(Trade.note.like("order:%"))
        ).scalar_one()

        unknown = self.session.execute(
            select(func.count(OrderRecord.id)).where(
                OrderRecord.status == OrderStatus.UNKNOWN.value
            )
        ).scalar_one()

        return {
            "filled_orders": len(filled),
            "order_linked_trades": int(linked_trades),
            "missing_trades": missing_trades,
            "unknown_orders": int(unknown),
            "ok": not missing_trades and unknown == 0,
        }

    # ==================== 内部 ====================

    def _move(self, order: Order, dst: OrderStatus, reason: str = "") -> Order:
        src = order.status
        transition(src, dst)
        self._event(order.client_order_id, src, dst, reason)
        order.status = dst
        order.updated_at = datetime.now()
        return order

    def _event(
        self,
        oid: str,
        src: Optional[OrderStatus],
        dst: OrderStatus,
        reason: str = "",
    ) -> None:
        self.session.add(
            OrderEventRecord(
                client_order_id=oid,
                from_status=src.value if src else None,
                to_status=dst.value,
                reason=reason,
            )
        )

    def _persist(self, rec: OrderRecord, order: Order) -> None:
        _sync(rec, order)
        self.session.commit()

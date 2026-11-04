"""订单领域层（纯逻辑，无 IO）

真实下单最容易出事故的地方不是"怎么调券商接口"，而是：
    - 网络超时后盲目重试 → 重复成交
    - 状态乱跳（已撤单又回填成交）
    - 风控规则散落在各处、没法单测
    - 进程重启后丢失未完成订单

所以把状态机、幂等键、风控规则全部放在这一层，不依赖数据库、行情或券商 SDK。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, time
from enum import Enum
from typing import Iterable, Optional

LOT_SIZE = 100

# A 股连续竞价时段（含集合竞价尾段先不做，避免误判）
TRADING_SESSIONS = (
    (time(9, 30), time(11, 30)),
    (time(13, 0), time(15, 0)),
)


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    CREATED = "created"                  # 信号生成，尚未人工确认
    PENDING_REVIEW = "pending_review"    # 已生成草稿，等人在券商端执行
    SUBMITTED = "submitted"              # 已提交券商（Manual 通道不会到此状态）
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"                    # 全部成交
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"                  # 超时未成交
    UNKNOWN = "unknown"                  # 回报丢失，必须靠对账恢复，禁止重下
    ARCHIVED = "archived"                # 已对账归档


TERMINAL_STATUSES = frozenset({
    OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED,
    OrderStatus.EXPIRED, OrderStatus.ARCHIVED,
})

ALLOWED_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.CREATED: frozenset({
        OrderStatus.PENDING_REVIEW, OrderStatus.SUBMITTED, OrderStatus.FILLED,
        OrderStatus.CANCELLED, OrderStatus.REJECTED, OrderStatus.EXPIRED,
        OrderStatus.UNKNOWN,
    }),
    OrderStatus.PENDING_REVIEW: frozenset({
        OrderStatus.SUBMITTED, OrderStatus.FILLED, OrderStatus.CANCELLED,
        OrderStatus.EXPIRED, OrderStatus.UNKNOWN,
    }),
    OrderStatus.SUBMITTED: frozenset({
        OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED, OrderStatus.CANCELLED,
        OrderStatus.REJECTED, OrderStatus.EXPIRED, OrderStatus.UNKNOWN,
    }),
    OrderStatus.PARTIALLY_FILLED: frozenset({
        OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.EXPIRED,
        OrderStatus.UNKNOWN,
    }),
    OrderStatus.UNKNOWN: frozenset({
        OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED,
        OrderStatus.ARCHIVED,
    }),
    OrderStatus.FILLED: frozenset({OrderStatus.ARCHIVED}),
    OrderStatus.CANCELLED: frozenset(),
    OrderStatus.REJECTED: frozenset(),
    OrderStatus.EXPIRED: frozenset(),
    OrderStatus.ARCHIVED: frozenset(),
}


class InvalidTransition(Exception):
    """非法状态跃迁"""


class OrderValidationError(Exception):
    """订单形状不合法（整手 / 价格 / 数量 / 方向）"""


def can_transition(src: OrderStatus, dst: OrderStatus) -> bool:
    return dst in ALLOWED_TRANSITIONS.get(src, frozenset())


def transition(src: OrderStatus, dst: OrderStatus) -> OrderStatus:
    if not can_transition(src, dst):
        raise InvalidTransition(f"不允许从 {src.value} 跃迁到 {dst.value}")
    return dst


def make_client_order_id(
    code: str, side: str, strategy: str, bar_date: str, seq: int = 0
) -> str:
    """幂等键：同一信号在同一根 K 线上只会产生一张订单

    用短哈希而非长字符串，方便放进券商委托备注，也避免暴露策略细节。
    """
    raw = f"{code}|{side}|{strategy}|{bar_date}|{seq}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def is_trading_session(now: datetime, calendar=None) -> bool:
    """是否处于交易日 + 连续竞价时段

    Args:
        calendar: 交易日历对象（需实现 is_trading_day）；不传则只判断周末
        now: 可注入，便于测试
    """
    if calendar is not None and not calendar.is_trading_day(now.date()):
        return False

    current = now.time()
    return any(start <= current <= end for start, end in TRADING_SESSIONS)


@dataclass
class Order:
    """订单（纯数据）"""

    client_order_id: str
    code: str
    side: OrderSide
    price: float
    quantity: int
    strategy: str = ""
    bar_date: str = ""
    name: str = ""
    status: OrderStatus = OrderStatus.CREATED
    filled_quantity: int = 0
    filled_price: float = 0.0
    broker: str = "manual"
    dry_run: bool = True
    note: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    @property
    def amount(self) -> float:
        return self.price * self.quantity

    @property
    def remaining_quantity(self) -> int:
        return max(0, self.quantity - self.filled_quantity)

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    def validate_shape(self) -> None:
        """整手 / 价格 / 数量 / 方向，违反直接抛异常"""
        if self.side not in (OrderSide.BUY, OrderSide.SELL):
            raise OrderValidationError(f"无效方向: {self.side}")
        if self.price <= 0:
            raise OrderValidationError("委托价必须大于 0")
        if self.quantity <= 0 or self.quantity % LOT_SIZE != 0:
            raise OrderValidationError(f"委托数量必须为 {LOT_SIZE} 的整数倍")
        if not self.client_order_id:
            raise OrderValidationError("缺少幂等键 client_order_id")
        if self.filled_quantity > self.quantity:
            raise OrderValidationError("成交量不能超过委托量")


@dataclass
class OrderEvent:
    """状态变更事件（审计留痕）"""

    client_order_id: str
    from_status: Optional[OrderStatus]
    to_status: OrderStatus
    reason: str = ""
    at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class RiskLimits:
    """风控限额（不可变，从配置构造）"""

    enabled: bool = False                 # kill switch，默认关闭真实提交
    whitelist: tuple[str, ...] = ()       # 空 = 不限制
    max_order_amount: float = 50_000.0    # 单笔上限（元）
    max_daily_amount: float = 100_000.0   # 单日累计上限（元）
    max_positions: int = 10               # 最大持仓只数
    max_position_ratio: float = 0.3       # 单票占总资产上限
    timeout_minutes: int = 30             # 未成交超时撤单
    require_confirmation: bool = True     # 必须人工二次确认

    @classmethod
    def from_config(cls, cfg: Optional[dict] = None) -> "RiskLimits":
        cfg = cfg or {}
        broker_cfg = cfg.get("broker", {}) or {}
        risk_cfg = cfg.get("risk", {}) or {}
        whitelist = tuple(risk_cfg.get("whitelist") or ())

        return cls(
            enabled=bool(broker_cfg.get("enabled", False)),
            whitelist=whitelist,
            max_order_amount=float(risk_cfg.get("max_order_amount", 50_000.0)),
            max_daily_amount=float(risk_cfg.get("max_daily_amount", 100_000.0)),
            max_positions=int(risk_cfg.get("max_positions", 10)),
            max_position_ratio=float(risk_cfg.get("max_position_ratio", 0.3)),
            timeout_minutes=int(risk_cfg.get("timeout_minutes", 30)),
            require_confirmation=bool(risk_cfg.get("require_confirmation", True)),
        )

    # ==================== 纯逻辑校验 ====================

    def check_static(
        self,
        order: Order,
        now: datetime,
        calendar=None,
        enforce_session: bool = True,
    ) -> list[str]:
        """不依赖持仓/数据库的静态规则，返回违规原因列表（空 = 通过）"""
        violations: list[str] = []

        try:
            order.validate_shape()
        except OrderValidationError as e:
            violations.append(str(e))

        if self.whitelist and order.code not in self.whitelist:
            violations.append(f"{order.code} 不在白名单内")

        if order.amount > self.max_order_amount:
            violations.append(
                f"单笔金额 {order.amount:,.0f} 超过上限 {self.max_order_amount:,.0f}"
            )

        if enforce_session and not is_trading_session(now, calendar):
            violations.append(f"{now:%Y-%m-%d %H:%M} 不在交易时段")

        return violations

    def check_portfolio(
        self,
        order: Order,
        positions: Iterable,
        daily_amount: float = 0.0,
        bought_today: bool = False,
        total_equity: float = 0.0,
    ) -> list[str]:
        """依赖持仓/当日统计的规则，仍然是纯函数"""
        violations: list[str] = []

        if daily_amount + order.amount > self.max_daily_amount:
            violations.append(
                f"当日累计 {daily_amount + order.amount:,.0f} 超过上限 {self.max_daily_amount:,.0f}"
            )

        positions = list(positions)
        if order.side == OrderSide.BUY and len(positions) >= self.max_positions:
            violations.append(f"持仓 {len(positions)} 只已达上限 {self.max_positions}")

        if order.side == OrderSide.SELL and bought_today:
            violations.append(f"T+1 限制: {order.code} 当日买入不可卖出")

        if (
            order.side == OrderSide.BUY
            and total_equity > 0
            and order.amount / total_equity > self.max_position_ratio
        ):
            violations.append(
                f"单票仓位 {order.amount / total_equity:.1%} 超过上限 {self.max_position_ratio:.1%}"
            )

        return violations

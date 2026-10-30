"""模拟盘（Paper Trading）

不涉及真实资金，也不连券商：按回测同款的撮合与费率规则记一笔虚拟交易，
用来验证策略从「信号」到「持仓/盈亏」的闭环。

与回测的区别：
- 回测跑历史 K 线，模拟盘用当前价手工/程序下单
- 两者共用 FeeModel（佣金、最低佣金、印花税）和整手（100 股）约束

规则:
    1. 买入按 100 股整手，资金不足则拒绝
    2. 卖出受 T+1 约束（当天买入的不能当天卖）
    3. 卖出数量不能超过持仓
    4. A 股卖出收印花税，佣金有最低 5 元

数据存在 data/paper_account.json，方便直接查看和重置。
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from app.domain.calendar import get_calendar
from app.domain.fees import FeeModel

logger = logging.getLogger(__name__)

LOT_SIZE = 100


class PaperTradeError(Exception):
    """模拟盘下单失败"""


@dataclass
class PaperOrder:
    """模拟盘成交记录"""

    id: int
    code: str
    name: str = ""
    side: str = ""            # buy / sell
    price: float = 0.0
    quantity: int = 0
    amount: float = 0.0
    commission: float = 0.0
    tax: float = 0.0
    realized_profit: float = 0.0   # 卖出时相对成本价的盈亏
    trade_date: str = ""
    note: str = ""

    @property
    def net_amount(self) -> float:
        """净金额（买入为支出，卖出为收入）"""
        fees = self.commission + self.tax
        return self.amount + fees if self.side == "buy" else self.amount - fees


@dataclass
class PaperPosition:
    """模拟盘持仓"""

    code: str
    name: str = ""
    quantity: int = 0
    avg_cost: float = 0.0
    realized_profit: float = 0.0
    last_buy_date: str = ""


@dataclass
class PaperAccount:
    """模拟盘账户"""

    initial_cash: float = 100_000.0
    cash: float = 100_000.0
    orders: list = field(default_factory=list)
    positions: dict = field(default_factory=dict)
    next_order_id: int = 1


class PaperBroker:
    """模拟盘交易"""

    def __init__(
        self,
        data_path: Optional[str] = None,
        fee_model: Optional[FeeModel] = None,
        initial_cash: Optional[float] = None,
    ):
        from app.config import get_config

        cfg = get_config()
        self.data_path = Path(data_path) if data_path else Path(cfg.get("data_dir", "./data")) / "paper_account.json"
        self.fee_model = fee_model or FeeModel.from_config(cfg)
        self.default_initial_cash = float(
            initial_cash if initial_cash is not None
            else cfg.get("paper", {}).get("initial_cash", 100_000.0)
        )
        self.account = self._load()

    # ==================== 持久化 ====================

    def _load(self) -> PaperAccount:
        if not self.data_path.exists():
            return PaperAccount(
                initial_cash=self.default_initial_cash,
                cash=self.default_initial_cash,
            )
        try:
            raw = json.loads(self.data_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"模拟盘数据读取失败，使用空账户: {e}")
            return PaperAccount(
                initial_cash=self.default_initial_cash,
                cash=self.default_initial_cash,
            )

        account = PaperAccount(
            initial_cash=float(raw.get("initial_cash", self.default_initial_cash)),
            cash=float(raw.get("cash", self.default_initial_cash)),
            next_order_id=int(raw.get("next_order_id", 1)),
        )
        account.orders = [PaperOrder(**o) for o in raw.get("orders", [])]
        account.positions = {c: PaperPosition(**p) for c, p in raw.get("positions", {}).items()}
        return account

    def _save(self) -> None:
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "initial_cash": self.account.initial_cash,
            "cash": self.account.cash,
            "next_order_id": self.account.next_order_id,
            "orders": [asdict(o) for o in self.account.orders],
            "positions": {c: asdict(p) for c, p in self.account.positions.items()},
            "updated_at": datetime.now().isoformat(),
        }
        self.data_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ==================== 下单 ====================

    def buy(
        self,
        code: str,
        price: float,
        quantity: int = 0,
        amount: float = 0.0,
        name: str = "",
        note: str = "",
        trade_date: Optional[date] = None,
    ) -> PaperOrder:
        """买入

        Args:
            code: 股票代码
            price: 成交价
            quantity: 股数（不传则按 amount 折算整手）
            amount: 想投入的金额（quantity 为空时生效）
            name: 股票名称
            note: 备注
            trade_date: 成交日期，默认今天
        """
        if price <= 0:
            raise PaperTradeError("成交价必须大于 0")

        if quantity <= 0:
            if amount <= 0:
                raise PaperTradeError("需指定 quantity 或 amount")
            quantity = int(amount / price / LOT_SIZE) * LOT_SIZE

        quantity = int(quantity / LOT_SIZE) * LOT_SIZE
        if quantity < LOT_SIZE:
            raise PaperTradeError(f"买入数量不足 1 手（{LOT_SIZE} 股）")

        gross = quantity * price
        commission = self.fee_model.commission(gross)
        cost = gross + commission
        if cost > self.account.cash:
            raise PaperTradeError(
                f"资金不足: 需要 {cost:,.2f} 元，可用 {self.account.cash:,.2f} 元"
            )

        day = (trade_date or date.today()).isoformat()
        order = PaperOrder(
            id=self.account.next_order_id,
            code=code,
            name=name,
            side="buy",
            price=price,
            quantity=quantity,
            amount=gross,
            commission=commission,
            trade_date=day,
            note=note,
        )
        self.account.next_order_id += 1
        self.account.cash -= cost

        position = self.account.positions.get(code) or PaperPosition(code=code, name=name)
        position.name = position.name or name
        total_cost = position.avg_cost * position.quantity + gross
        position.quantity += quantity
        position.avg_cost = total_cost / position.quantity if position.quantity else 0.0
        position.last_buy_date = day
        self.account.positions[code] = position

        self.account.orders.append(order)
        self._save()
        return order

    def sell(
        self,
        code: str,
        price: float,
        quantity: int = 0,
        name: str = "",
        note: str = "",
        trade_date: Optional[date] = None,
        allow_same_day: bool = False,
    ) -> PaperOrder:
        """卖出

        Args:
            code: 股票代码
            price: 成交价
            quantity: 股数，0 表示全部卖出
            allow_same_day: 跳过 T+1 检查（仅用于回灌历史数据）
        """
        if price <= 0:
            raise PaperTradeError("成交价必须大于 0")

        position = self.account.positions.get(code)
        if not position or position.quantity <= 0:
            raise PaperTradeError(f"没有 {code} 的持仓")

        if quantity <= 0:
            quantity = position.quantity
        quantity = int(quantity / LOT_SIZE) * LOT_SIZE
        if quantity <= 0:
            raise PaperTradeError(f"卖出数量不足 1 手（{LOT_SIZE} 股）")
        if quantity > position.quantity:
            raise PaperTradeError(
                f"持仓不足: 持有 {position.quantity} 股，想卖 {quantity} 股"
            )

        day = (trade_date or date.today()).isoformat()
        if not allow_same_day and position.last_buy_date == day:
            raise PaperTradeError(f"T+1 限制: {code} 当日买入，不能当天卖出")

        gross = quantity * price
        commission = self.fee_model.commission(gross)
        tax = self.fee_model.tax(gross, action="sell")
        realized = (price - position.avg_cost) * quantity - commission - tax

        order = PaperOrder(
            id=self.account.next_order_id,
            code=code,
            name=name or position.name,
            side="sell",
            price=price,
            quantity=quantity,
            amount=gross,
            commission=commission,
            tax=tax,
            realized_profit=realized,
            trade_date=day,
            note=note,
        )
        self.account.next_order_id += 1
        self.account.cash += gross - commission - tax

        position.quantity -= quantity
        position.realized_profit += realized
        if position.quantity <= 0:
            position.quantity = 0
            position.avg_cost = 0.0

        self.account.orders.append(order)
        self._save()
        return order

    # ==================== 查询 ====================

    def positions(self, include_empty: bool = False) -> list[PaperPosition]:
        items = list(self.account.positions.values())
        if not include_empty:
            items = [p for p in items if p.quantity > 0]
        return items

    def orders(self, limit: int = 50) -> list[PaperOrder]:
        return list(self.account.orders[-limit:])

    def summary(self, prices: Optional[dict] = None) -> dict:
        """账户总览

        Args:
            prices: {code: 现价}，不传则市值按成本计
        """
        prices = prices or {}
        market_value = 0.0
        unrealized = 0.0

        for position in self.positions():
            price = float(prices.get(position.code, 0) or 0)
            value = position.quantity * (price if price > 0 else position.avg_cost)
            market_value += value
            if price > 0:
                unrealized += (price - position.avg_cost) * position.quantity

        realized = sum(p.realized_profit for p in self.account.positions.values())
        equity = self.account.cash + market_value
        initial = self.account.initial_cash

        return {
            "initial_cash": initial,
            "cash": self.account.cash,
            "market_value": market_value,
            "equity": equity,
            "total_return": (equity - initial) / initial * 100 if initial else 0.0,
            "realized_profit": realized,
            "unrealized_profit": unrealized,
            "position_count": len(self.positions()),
            "order_count": len(self.account.orders),
            "next_trading_day": get_calendar().next_trading_day().isoformat(),
        }

    def reset(self, initial_cash: Optional[float] = None) -> None:
        """重置账户"""
        cash = float(initial_cash if initial_cash is not None else self.default_initial_cash)
        self.account = PaperAccount(initial_cash=cash, cash=cash)
        self._save()

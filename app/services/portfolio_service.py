"""持仓管理服务"""

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.models.portfolio import PortfolioRecord
from app.models.stock import Stock, normalize_stock_code
from app.models.trade import Trade
from app.data.stock_data_client import StockDataClient


class PortfolioService:
    """持仓管理服务（根据交易记录自动计算）"""

    def __init__(self, session: Optional[Session] = None):
        self._session = session
        self._client = StockDataClient()

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = get_session()
        return self._session

    def rebuild_portfolio(self, force: bool = False):
        """根据交易记录重建所有持仓（全量重算）

        Args:
            force: True 时清掉所有手工校正标记并按交易记录全量重算
                   （默认 False：保留 manual_override=True 的行，不覆盖手工校正）
        """
        existing = self.session.execute(select(PortfolioRecord)).scalars().all()

        # 手工锁定的行是"第二套真相"，重建时必须绕开，否则校正会被悄悄抹掉
        locked_codes: set[str] = set()
        for p in existing:
            if p.manual_override and not force:
                locked_codes.add(p.stock_code)
                continue
            self.session.delete(p)

        # 查询所有交易记录（按时间排序）
        trades = (
            self.session.execute(
                select(Trade).order_by(Trade.trade_time)
            )
            .scalars()
            .all()
        )

        # 按股票代码分组
        stock_trades: dict[str, list[Trade]] = {}
        for t in trades:
            if t.stock_code not in stock_trades:
                stock_trades[t.stock_code] = []
            stock_trades[t.stock_code].append(t)

        # 逐只股票计算持仓
        for code, code_trades in stock_trades.items():
            if code in locked_codes:
                continue  # 手工校正的行保持原样
            record = PortfolioRecord(
                stock_code=code,
                stock_name=code_trades[0].stock_name or "",
                market=code_trades[0].market or "A",
                quantity=0,
                avg_cost=0.0,
                total_cost=0.0,
                realized_profit=0.0,
                total_commission=0.0,
                total_tax=0.0,
                buy_count=0,
                sell_count=0,
            )

            for t in code_trades:
                record.total_commission += t.commission or 0
                record.total_tax += t.tax or 0

                if t.action == "buy":
                    # 加权平均成本
                    new_total_cost = record.total_cost + t.amount
                    new_qty = record.quantity + t.quantity
                    record.avg_cost = new_total_cost / new_qty if new_qty > 0 else 0
                    record.total_cost = new_total_cost
                    record.quantity = new_qty
                    record.buy_count += 1

                    if record.first_buy_time is None:
                        record.first_buy_time = t.trade_time
                        record.first_buy_price = t.price

                elif t.action == "sell":
                    # 计算已实现盈亏
                    sell_profit = (t.price - record.avg_cost) * t.quantity
                    sell_profit -= (t.commission or 0) + (t.tax or 0)
                    record.realized_profit += sell_profit

                    record.quantity -= t.quantity
                    record.total_cost = record.avg_cost * record.quantity
                    record.sell_count += 1

                    if record.stock_name == "" and t.stock_name:
                        record.stock_name = t.stock_name

            self.session.add(record)

        self.session.commit()

    def get_portfolio(self, include_cleared: bool = False) -> list[PortfolioRecord]:
        """获取持仓列表

        Args:
            include_cleared: 是否包含已清仓的记录

        Returns:
            持仓记录列表
        """
        stmt = select(PortfolioRecord)
        if not include_cleared:
            stmt = stmt.where(PortfolioRecord.quantity > 0)
        return list(self.session.execute(stmt).scalars().all())

    def get_holding(self, stock_code: str) -> Optional[PortfolioRecord]:
        """获取单只股票的持仓"""
        return self.session.execute(
            select(PortfolioRecord).where(PortfolioRecord.stock_code == stock_code)
        ).scalar_one_or_none()

    # ==================== 手工校正（两套真相） ====================

    def update_holding(
        self,
        stock_code: str,
        quantity: Optional[int] = None,
        avg_cost: Optional[float] = None,
        stock_name: Optional[str] = None,
        reason: str = "",
    ) -> dict:
        """手工校正一条持仓：改数量 / 成本价 / 名称，并锁定该行

        锁定后 `rebuild_portfolio()` 会跳过它，校正值不会被交易记录覆盖。
        校正前后值与理由写入 override_note，另有 Web 层 web_writes 幂等日志。
        """
        code = normalize_stock_code(stock_code)
        if quantity is not None and quantity < 0:
            raise ValueError("持仓数量不能为负")
        if avg_cost is not None and avg_cost < 0:
            raise ValueError("成本价不能为负")

        record = self.get_holding(code)
        created = record is None
        if record is None:
            if quantity is None or avg_cost is None:
                raise ValueError(
                    f"没有 {code} 的持仓记录；手工新增必须同时提供 quantity 与 avg_cost"
                )
            record = PortfolioRecord(
                stock_code=code,
                stock_name=stock_name or "",
                market=Stock.parse_market(code),
                quantity=0, avg_cost=0.0, total_cost=0.0,
                realized_profit=0.0, total_commission=0.0, total_tax=0.0,
                buy_count=0, sell_count=0,
            )
            self.session.add(record)

        before = {
            "quantity": record.quantity,
            "avg_cost": record.avg_cost,
            "total_cost": record.total_cost,
            "stock_name": record.stock_name,
        }
        changes = []
        if quantity is not None and quantity != record.quantity:
            changes.append(f"数量 {record.quantity}→{quantity}")
            record.quantity = quantity
        if avg_cost is not None and avg_cost != record.avg_cost:
            changes.append(f"成本 {record.avg_cost:.2f}→{avg_cost:.2f}")
            record.avg_cost = avg_cost
        if stock_name is not None and stock_name != record.stock_name:
            changes.append(f"名称 {record.stock_name or ''}→{stock_name}")
            record.stock_name = stock_name

        # total_cost 必须与 quantity * avg_cost 保持一致，否则汇总会自相矛盾
        record.total_cost = record.quantity * record.avg_cost
        record.manual_override = True
        record.override_at = datetime.now()
        record.override_note = (
            f"{record.override_at:%Y-%m-%d %H:%M} | "
            f"{'手工新增' if created else '; '.join(changes) or '仅锁定'} | "
            f"理由: {reason or '未填写'}"
        )
        self.session.commit()

        return {
            "stock_code": code,
            "created": created,
            "before": before,
            "after": {
                "quantity": record.quantity,
                "avg_cost": record.avg_cost,
                "total_cost": record.total_cost,
                "stock_name": record.stock_name,
            },
            "manual_override": True,
            "override_note": record.override_note,
        }

    def unlock_holding(self, stock_code: str) -> dict:
        """解除手工锁定，并立即按交易记录恢复派生值"""
        code = normalize_stock_code(stock_code)
        record = self.get_holding(code)
        if not record:
            raise ValueError(f"没有 {code} 的持仓记录")

        record.manual_override = False
        record.override_note = (
            f"{datetime.now():%Y-%m-%d %H:%M} | 已解除锁定，按交易记录重建"
        )
        self.session.commit()
        self.rebuild_portfolio()

        restored = self.get_holding(code)
        return {
            "stock_code": code,
            "restored": {
                "quantity": restored.quantity if restored else 0,
                "avg_cost": restored.avg_cost if restored else 0.0,
            },
        }

    def clear_holding(self, stock_code: str, reason: str = "") -> dict:
        """手工清仓：数量置 0 并锁定该行（保留成本与已实现盈亏供追溯）"""
        if not self.get_holding(normalize_stock_code(stock_code)):
            raise ValueError(f"没有 {stock_code} 的持仓记录，无法清仓")

        result = self.update_holding(
            stock_code, quantity=0, reason=f"手工清仓；{reason or '未填写理由'}"
        )
        result["cleared"] = True
        return result

    def locked_codes(self) -> list[str]:
        """返回所有被手工锁定的股票代码"""
        records = self.session.execute(
            select(PortfolioRecord.stock_code).where(
                PortfolioRecord.manual_override.is_(True)
            )
        ).scalars().all()
        return list(records)

    def get_portfolio_with_market_data(self, include_cleared: bool = False) -> list[dict]:
        """获取持仓列表 + 实时行情数据

        Args:
            include_cleared: 是否包含数量为 0 的已清仓记录。已清仓行不需要
                实时行情，所以只为有持仓的代码发起请求，避免无谓开销。
        """
        holdings = self.get_portfolio(include_cleared=include_cleared)
        if not holdings:
            return []

        codes = [h.stock_code for h in holdings if h.quantity > 0]
        quotes = {}
        if codes:
            try:
                quotes = self._client.quote(*codes)
            except Exception:
                quotes = {}

        result = []
        for h in holdings:
            data = {
                "stock_code": h.stock_code,
                "stock_name": h.stock_name,
                "market": h.market,
                "quantity": h.quantity,
                "avg_cost": h.avg_cost,
                "total_cost": h.total_cost,
                "buy_count": h.buy_count,
                "sell_count": h.sell_count,
                "realized_profit": h.realized_profit,
                "first_buy_time": h.first_buy_time,
                "manual_override": bool(h.manual_override),
                "override_note": h.override_note,
                "override_at": h.override_at,
                "is_cleared": h.quantity <= 0,
            }

            if data["is_cleared"]:
                data.update({
                    "current_price": 0, "market_value": 0,
                    "unrealized_profit": 0, "unrealized_profit_rate": 0,
                    "change_percent": 0,
                })
                result.append(data)
                continue

            # 尝试获取实时价格
            quote_data = quotes.get(h.stock_code, {})
            # 如果持仓记录没有名称，从行情数据中补充
            if not data["stock_name"] and quote_data.get("name"):
                data["stock_name"] = quote_data["name"]
                # 同时更新数据库中的持仓记录
                try:
                    h.stock_name = quote_data["name"]
                    self.session.commit()
                except Exception:
                    pass
            current_price = quote_data.get("price", 0)
            if current_price and current_price > 0:
                data["current_price"] = current_price
                data["market_value"] = current_price * h.quantity
                data["unrealized_profit"] = h.calc_unrealized_profit(current_price)
                data["unrealized_profit_rate"] = h.calc_unrealized_profit_rate(current_price)
                data["change_percent"] = quote_data.get("change_percent", 0)
            else:
                data["current_price"] = 0
                data["market_value"] = h.quantity * h.avg_cost
                data["unrealized_profit"] = 0
                data["unrealized_profit_rate"] = 0
                data["change_percent"] = 0

            result.append(data)

        return result

    def get_total_summary(self) -> dict:
        """获取持仓总览"""
        holdings = self.get_portfolio_with_market_data()
        all_records = self.get_portfolio(include_cleared=True)

        total_cost = sum(h["total_cost"] for h in holdings)
        total_market_value = sum(h["market_value"] for h in holdings)
        total_unrealized = sum(h["unrealized_profit"] for h in holdings)
        total_realized = sum(r.realized_profit for r in all_records)

        return {
            "holding_count": len(holdings),
            "total_stock_count": len(all_records),
            "total_cost": total_cost,
            "total_market_value": total_market_value,
            "total_unrealized_profit": total_unrealized,
            "total_unrealized_profit_rate": (
                total_unrealized / total_cost * 100 if total_cost > 0 else 0
            ),
            "total_realized_profit": total_realized,
            "total_profit": total_unrealized + total_realized,
            "holdings": holdings,
        }

"""持仓管理服务"""

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.models.portfolio import PortfolioRecord
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

    def rebuild_portfolio(self):
        """根据交易记录重建所有持仓（全量重算）"""
        # 清除现有持仓
        existing = self.session.execute(select(PortfolioRecord)).scalars().all()
        for p in existing:
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

    def get_portfolio_with_market_data(self) -> list[dict]:
        """获取持仓列表 + 实时行情数据"""
        holdings = self.get_portfolio()
        if not holdings:
            return []

        # 批量获取实时行情
        codes = [h.stock_code for h in holdings]
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
            }

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

"""交易记录服务 - CRUD + CSV导入导出"""

import csv
import io
from datetime import datetime
from typing import Optional
from pathlib import Path

from sqlalchemy import select, desc, and_
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.models.trade import Trade
from app.models.stock import normalize_stock_code, Stock


class TradeService:
    """交易记录 CRUD 服务"""

    def __init__(self, session: Optional[Session] = None):
        self._session = session

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = get_session()
        return self._session

    def add_trade(
        self,
        stock_code: str,
        action: str,
        price: float,
        quantity: int,
        stock_name: str = "",
        market: str = "",
        commission: float = 0.0,
        tax: float = 0.0,
        reason: str = "",
        strategy: str = "",
        tags: str = "",
        note: str = "",
        trade_time: Optional[datetime] = None,
    ) -> Trade:
        """添加一笔交易记录

        Args:
            stock_code: 股票代码 (如 600519 或 sh600519，自动补全前缀)
            action: buy 或 sell
            price: 成交价格
            quantity: 成交数量（股）
            stock_name: 股票名称
            market: 市场类型 (自动根据代码推断)
            commission: 手续费
            tax: 印花税
            reason: 交易理由
            strategy: 策略名称
            tags: 标签（逗号分隔）
            note: 备注
            trade_time: 交易时间（默认当前时间）

        Returns:
            创建的 Trade 对象
        """
        # 自动补全代码前缀
        stock_code = normalize_stock_code(stock_code)

        # 自动判断市场
        if not market:
            market = Stock.parse_market(stock_code)

        # 自动查询股票名称（如果未提供）
        if not stock_name:
            try:
                from app.data.stock_data_client import StockDataClient
                client = StockDataClient()
                quote_data = client.quote(stock_code)
                stock_name = quote_data.get(stock_code, {}).get("name", "")
            except Exception:
                pass  # 查询失败不影响交易记录

        # 计算成交金额
        amount = price * quantity

        # A股印花税自动计算（卖出时千分之一）
        if tax == 0.0 and action == "sell" and market == "A":
            tax = amount * 0.001

        # A股手续费自动计算（万分之三，最低5元）
        if commission == 0.0 and market == "A":
            commission = max(amount * 0.0003, 5.0)

        trade = Trade(
            stock_code=stock_code,
            stock_name=stock_name,
            market=market,
            action=action,
            price=price,
            quantity=quantity,
            amount=amount,
            commission=commission,
            tax=tax,
            trade_time=trade_time or datetime.now(),
            reason=reason,
            strategy=strategy,
            tags=tags,
            note=note,
        )

        # 如果是卖出，尝试匹配买入记录计算盈亏
        if action == "sell":
            self._calc_sell_profit(trade)

        self.session.add(trade)
        self.session.commit()
        self.session.refresh(trade)
        return trade

    def _calc_sell_profit(self, sell_trade: Trade):
        """计算卖出盈亏（基于平均成本法）"""
        # 查询同股票的所有买入记录
        buys = self.session.execute(
            select(Trade)
            .where(
                and_(
                    Trade.stock_code == sell_trade.stock_code,
                    Trade.action == "buy",
                )
            )
            .order_by(Trade.trade_time)
        ).scalars().all()

        sells = self.session.execute(
            select(Trade)
            .where(
                and_(
                    Trade.stock_code == sell_trade.stock_code,
                    Trade.action == "sell",
                )
            )
            .order_by(Trade.trade_time)
        ).scalars().all()

        # 计算平均成本
        total_buy_qty = sum(t.quantity for t in buys)
        total_buy_amount = sum(t.amount for t in buys)
        total_sell_qty = sum(t.quantity for t in sells)

        remaining_qty = total_buy_qty - total_sell_qty
        if remaining_qty <= 0 or total_buy_qty <= 0:
            return

        avg_cost = total_buy_amount / total_buy_qty
        sell_trade.profit = (sell_trade.price - avg_cost) * sell_trade.quantity
        sell_trade.profit -= (sell_trade.commission or 0) + (sell_trade.tax or 0)
        sell_trade.profit_rate = (
            (sell_trade.price - avg_cost) / avg_cost * 100 if avg_cost > 0 else 0
        )

        # 计算持仓天数
        if buys:
            first_buy = buys[0]
            sell_trade.holding_days = (
                sell_trade.trade_time - first_buy.trade_time
            ).days

    def list_trades(
        self,
        stock_code: str = "",
        action: str = "",
        market: str = "",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Trade]:
        """查询交易记录列表

        Args:
            stock_code: 按股票代码过滤
            action: 按动作过滤 (buy/sell)
            market: 按市场过滤 (A/HK/US)
            start_date: 开始日期
            end_date: 结束日期
            limit: 每页数量
            offset: 偏移量

        Returns:
            交易记录列表
        """
        stmt = select(Trade).order_by(desc(Trade.trade_time))

        if stock_code:
            stmt = stmt.where(Trade.stock_code == stock_code)
        if action:
            stmt = stmt.where(Trade.action == action)
        if market:
            stmt = stmt.where(Trade.market == market)
        if start_date:
            stmt = stmt.where(Trade.trade_time >= start_date)
        if end_date:
            stmt = stmt.where(Trade.trade_time <= end_date)

        stmt = stmt.limit(limit).offset(offset)
        return list(self.session.execute(stmt).scalars().all())

    def get_trade(self, trade_id: int) -> Optional[Trade]:
        """根据ID获取交易记录"""
        return self.session.get(Trade, trade_id)

    def delete_trade(self, trade_id: int) -> bool:
        """删除交易记录"""
        trade = self.session.get(Trade, trade_id)
        if trade:
            self.session.delete(trade)
            self.session.commit()
            return True
        return False

    def update_trade(self, trade_id: int, **kwargs) -> Optional[Trade]:
        """更新交易记录"""
        trade = self.session.get(Trade, trade_id)
        if not trade:
            return None
        for key, value in kwargs.items():
            if hasattr(trade, key):
                setattr(trade, key, value)
        trade.updated_at = datetime.now()
        self.session.commit()
        self.session.refresh(trade)
        return trade

    def export_csv(self, filepath: str = "", **filter_kwargs) -> str:
        """导出交易记录为 CSV

        Args:
            filepath: 导出文件路径（为空则返回CSV字符串）
            **filter_kwargs: 传递给 list_trades 的过滤参数

        Returns:
            CSV 字符串或文件路径
        """
        trades = self.list_trades(limit=10000, **filter_kwargs)
        headers = [
            "ID", "日期", "股票代码", "股票名称", "市场", "买卖",
            "价格", "数量", "金额", "手续费", "印花税",
            "盈亏", "盈亏率(%)", "持仓天数", "理由", "策略", "标签", "备注",
        ]

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)

        for t in trades:
            writer.writerow([
                t.id,
                t.trade_time.strftime("%Y-%m-%d %H:%M:%S"),
                t.stock_code,
                t.stock_name or "",
                t.market,
                "买入" if t.action == "buy" else "卖出",
                f"{t.price:.4f}",
                t.quantity,
                f"{t.amount:.2f}",
                f"{t.commission or 0:.2f}",
                f"{t.tax or 0:.2f}",
                f"{t.profit:.2f}" if t.profit is not None else "",
                f"{t.profit_rate:.2f}" if t.profit_rate is not None else "",
                t.holding_days or "",
                t.reason or "",
                t.strategy or "",
                t.tags or "",
                t.note or "",
            ])

        csv_str = output.getvalue()
        output.close()

        if filepath:
            Path(filepath).parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
                f.write(csv_str)
            return filepath

        return csv_str

    def import_csv(self, filepath: str) -> int:
        """从 CSV 文件导入交易记录

        CSV 格式要求：日期,股票代码,股票名称,买卖(buy/sell),价格,数量
        可选列：手续费,印花税,理由,策略,标签,备注

        Args:
            filepath: CSV 文件路径

        Returns:
            导入的记录数
        """
        count = 0
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # 解析日期
                trade_time_str = row.get("日期") or row.get("date") or row.get("trade_time", "")
                trade_time = None
                if trade_time_str:
                    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d"]:
                        try:
                            trade_time = datetime.strptime(trade_time_str, fmt)
                            break
                        except ValueError:
                            continue

                # 解析买卖
                action_raw = row.get("买卖") or row.get("action") or row.get("买卖方向", "")
                action = "buy" if action_raw in ["buy", "买入", "买", "B"] else "sell"

                code = row.get("股票代码") or row.get("stock_code") or row.get("code", "")
                name = row.get("股票名称") or row.get("stock_name") or row.get("name", "")
                price = float(row.get("价格") or row.get("price") or 0)
                quantity = int(float(row.get("数量") or row.get("quantity") or row.get("amount", 0)))

                if not code or price <= 0 or quantity <= 0:
                    continue

                self.add_trade(
                    stock_code=code,
                    action=action,
                    price=price,
                    quantity=quantity,
                    stock_name=name,
                    commission=float(row.get("手续费") or row.get("commission", 0)),
                    tax=float(row.get("印花税") or row.get("tax", 0)),
                    reason=row.get("理由") or row.get("reason", ""),
                    strategy=row.get("策略") or row.get("strategy", ""),
                    tags=row.get("标签") or row.get("tags", ""),
                    note=row.get("备注") or row.get("note", ""),
                    trade_time=trade_time,
                )
                count += 1

        return count

    def get_stock_trades_summary(self, stock_code: str) -> dict:
        """获取单只股票的交易汇总"""
        trades = self.list_trades(stock_code=stock_code, limit=10000)
        if not trades:
            return {}

        buys = [t for t in trades if t.action == "buy"]
        sells = [t for t in trades if t.action == "sell"]

        total_buy_amount = sum(t.amount for t in buys)
        total_sell_amount = sum(t.amount for t in sells)
        total_buy_qty = sum(t.quantity for t in buys)
        total_sell_qty = sum(t.quantity for t in sells)

        return {
            "stock_code": stock_code,
            "stock_name": trades[0].stock_name if trades else "",
            "trade_count": len(trades),
            "buy_count": len(buys),
            "sell_count": len(sells),
            "total_buy_amount": total_buy_amount,
            "total_sell_amount": total_sell_amount,
            "total_buy_qty": total_buy_qty,
            "total_sell_qty": total_sell_qty,
            "remaining_qty": total_buy_qty - total_sell_qty,
            "avg_buy_price": total_buy_amount / total_buy_qty if total_buy_qty > 0 else 0,
            "realized_profit": sum(t.profit or 0 for t in sells),
            "first_trade_time": min(t.trade_time for t in trades),
            "last_trade_time": max(t.trade_time for t in trades),
        }

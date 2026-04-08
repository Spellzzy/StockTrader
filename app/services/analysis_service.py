"""统计分析服务 - 胜率、盈亏比、最大回撤、夏普比率等"""

import math
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict

import pandas as pd
import numpy as np
from sqlalchemy import select, desc, and_
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.models.trade import Trade


class AnalysisService:
    """交易统计分析服务"""

    def __init__(self, session: Optional[Session] = None):
        self._session = session

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = get_session()
        return self._session

    def get_trades_df(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        market: str = "",
    ) -> pd.DataFrame:
        """获取交易记录 DataFrame"""
        stmt = select(Trade).order_by(Trade.trade_time)
        conditions = []
        if start_date:
            conditions.append(Trade.trade_time >= start_date)
        if end_date:
            conditions.append(Trade.trade_time <= end_date)
        if market:
            conditions.append(Trade.market == market)
        if conditions:
            stmt = stmt.where(and_(*conditions))

        trades = list(self.session.execute(stmt).scalars().all())
        if not trades:
            return pd.DataFrame()

        data = []
        for t in trades:
            data.append({
                "id": t.id,
                "trade_time": t.trade_time,
                "stock_code": t.stock_code,
                "stock_name": t.stock_name or "",
                "market": t.market,
                "action": t.action,
                "price": t.price,
                "quantity": t.quantity,
                "amount": t.amount,
                "commission": t.commission or 0,
                "tax": t.tax or 0,
                "profit": t.profit,
                "profit_rate": t.profit_rate,
                "holding_days": t.holding_days,
                "reason": t.reason or "",
                "strategy": t.strategy or "",
                "tags": t.tags or "",
            })

        return pd.DataFrame(data)

    def summary(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        market: str = "",
    ) -> dict:
        """生成交易统计摘要

        Returns:
            {
                total_trades, buy_count, sell_count,
                win_count, loss_count, win_rate,
                total_profit, total_loss, profit_loss_ratio,
                avg_profit, avg_loss, max_profit, max_loss,
                total_commission, total_tax, net_profit,
                avg_holding_days, max_holding_days,
                stocks_traded, active_period,
            }
        """
        df = self.get_trades_df(start_date, end_date, market)
        if df.empty:
            return {"total_trades": 0, "message": "没有交易记录"}

        sells = df[df["action"] == "sell"]
        buys = df[df["action"] == "buy"]

        # 盈亏统计（基于卖出记录）
        sells_with_profit = sells[sells["profit"].notna()]
        wins = sells_with_profit[sells_with_profit["profit"] > 0]
        losses = sells_with_profit[sells_with_profit["profit"] < 0]
        evens = sells_with_profit[sells_with_profit["profit"] == 0]

        win_count = len(wins)
        loss_count = len(losses)
        total_closed = len(sells_with_profit)
        win_rate = win_count / total_closed * 100 if total_closed > 0 else 0

        total_profit = wins["profit"].sum() if not wins.empty else 0
        total_loss = abs(losses["profit"].sum()) if not losses.empty else 0
        avg_profit = wins["profit"].mean() if not wins.empty else 0
        avg_loss = abs(losses["profit"].mean()) if not losses.empty else 0

        # 盈亏比
        profit_loss_ratio = avg_profit / avg_loss if avg_loss > 0 else float("inf")

        # 费用
        total_commission = df["commission"].sum()
        total_tax = df["tax"].sum()

        # 净盈亏
        net_profit = total_profit - total_loss - total_commission - total_tax

        # 持仓天数
        holding_days = sells_with_profit["holding_days"].dropna()
        avg_holding = holding_days.mean() if not holding_days.empty else 0
        max_holding = holding_days.max() if not holding_days.empty else 0

        # 交易过的股票
        stocks_traded = df["stock_code"].nunique()

        # 活跃期间
        date_range = ""
        if not df.empty:
            min_date = df["trade_time"].min()
            max_date = df["trade_time"].max()
            date_range = f"{min_date.strftime('%Y-%m-%d')} ~ {max_date.strftime('%Y-%m-%d')}"

        return {
            "total_trades": len(df),
            "buy_count": len(buys),
            "sell_count": len(sells),
            "closed_count": total_closed,
            "win_count": win_count,
            "loss_count": loss_count,
            "even_count": len(evens),
            "win_rate": round(win_rate, 2),
            "total_profit": round(total_profit, 2),
            "total_loss": round(total_loss, 2),
            "profit_loss_ratio": round(profit_loss_ratio, 2),
            "avg_profit": round(avg_profit, 2),
            "avg_loss": round(avg_loss, 2),
            "max_profit": round(wins["profit"].max(), 2) if not wins.empty else 0,
            "max_loss": round(abs(losses["profit"].min()), 2) if not losses.empty else 0,
            "total_commission": round(total_commission, 2),
            "total_tax": round(total_tax, 2),
            "net_profit": round(net_profit, 2),
            "avg_holding_days": round(avg_holding, 1),
            "max_holding_days": int(max_holding) if not math.isnan(max_holding) else 0,
            "stocks_traded": stocks_traded,
            "active_period": date_range,
        }

    def daily_pnl(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """计算每日盈亏曲线

        Returns:
            DataFrame: date, daily_pnl, cumulative_pnl
        """
        df = self.get_trades_df(start_date, end_date)
        if df.empty:
            return pd.DataFrame()

        sells = df[df["action"] == "sell"].copy()
        if sells.empty:
            return pd.DataFrame()

        sells["date"] = sells["trade_time"].dt.date
        daily = sells.groupby("date").agg(
            daily_pnl=("profit", lambda x: x.fillna(0).sum()),
            trade_count=("id", "count"),
        ).reset_index()

        daily["cumulative_pnl"] = daily["daily_pnl"].cumsum()
        daily["date"] = pd.to_datetime(daily["date"])
        return daily

    def stock_pnl_ranking(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """按股票统计盈亏排名

        Returns:
            DataFrame: stock_code, stock_name, trade_count, total_profit, win_rate
        """
        df = self.get_trades_df(start_date, end_date)
        if df.empty:
            return pd.DataFrame()

        sells = df[df["action"] == "sell"]
        if sells.empty:
            return pd.DataFrame()

        result = []
        for code, group in sells.groupby("stock_code"):
            profits = group["profit"].dropna()
            wins = profits[profits > 0]
            total = len(profits)
            result.append({
                "stock_code": code,
                "stock_name": group["stock_name"].iloc[0],
                "trade_count": total,
                "total_profit": round(profits.sum(), 2),
                "avg_profit": round(profits.mean(), 2) if total > 0 else 0,
                "win_rate": round(len(wins) / total * 100, 1) if total > 0 else 0,
            })

        ranking = pd.DataFrame(result)
        return ranking.sort_values("total_profit", ascending=False).reset_index(drop=True)

    def strategy_analysis(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """按策略分析盈亏

        Returns:
            DataFrame: strategy, trade_count, total_profit, win_rate, avg_profit
        """
        df = self.get_trades_df(start_date, end_date)
        if df.empty:
            return pd.DataFrame()

        sells = df[(df["action"] == "sell") & (df["strategy"] != "")]
        if sells.empty:
            return pd.DataFrame()

        result = []
        for strategy, group in sells.groupby("strategy"):
            profits = group["profit"].dropna()
            wins = profits[profits > 0]
            total = len(profits)
            result.append({
                "strategy": strategy,
                "trade_count": total,
                "total_profit": round(profits.sum(), 2),
                "avg_profit": round(profits.mean(), 2) if total > 0 else 0,
                "win_rate": round(len(wins) / total * 100, 1) if total > 0 else 0,
                "max_profit": round(profits.max(), 2) if total > 0 else 0,
                "max_loss": round(profits.min(), 2) if total > 0 else 0,
            })

        return pd.DataFrame(result).sort_values("total_profit", ascending=False).reset_index(drop=True)

    def monthly_summary(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """按月统计交易

        Returns:
            DataFrame: month, trade_count, profit, win_rate
        """
        df = self.get_trades_df(start_date, end_date)
        if df.empty:
            return pd.DataFrame()

        sells = df[df["action"] == "sell"].copy()
        if sells.empty:
            return pd.DataFrame()

        sells["month"] = sells["trade_time"].dt.to_period("M")

        result = []
        for month, group in sells.groupby("month"):
            profits = group["profit"].dropna()
            wins = profits[profits > 0]
            total = len(profits)
            result.append({
                "month": str(month),
                "trade_count": total,
                "total_profit": round(profits.sum(), 2),
                "win_count": len(wins),
                "loss_count": total - len(wins),
                "win_rate": round(len(wins) / total * 100, 1) if total > 0 else 0,
                "avg_profit": round(profits.mean(), 2) if total > 0 else 0,
            })

        return pd.DataFrame(result)

    def max_drawdown(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict:
        """计算最大回撤

        Returns:
            {max_drawdown, max_drawdown_rate, peak_date, trough_date, recovery_date}
        """
        daily = self.daily_pnl(start_date, end_date)
        if daily.empty:
            return {"max_drawdown": 0, "max_drawdown_rate": 0}

        cumulative = daily["cumulative_pnl"].values
        peak = cumulative[0]
        max_dd = 0
        peak_idx = 0
        trough_idx = 0

        for i, val in enumerate(cumulative):
            if val > peak:
                peak = val
                peak_idx = i
            dd = peak - val
            if dd > max_dd:
                max_dd = dd
                trough_idx = i

        peak_date = daily.iloc[peak_idx]["date"] if peak_idx < len(daily) else None
        trough_date = daily.iloc[trough_idx]["date"] if trough_idx < len(daily) else None
        max_dd_rate = max_dd / peak * 100 if peak > 0 else 0

        return {
            "max_drawdown": round(max_dd, 2),
            "max_drawdown_rate": round(max_dd_rate, 2),
            "peak_date": peak_date.strftime("%Y-%m-%d") if peak_date is not None else "",
            "trough_date": trough_date.strftime("%Y-%m-%d") if trough_date is not None else "",
        }

    def holding_days_distribution(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict:
        """持仓天数分布"""
        df = self.get_trades_df(start_date, end_date)
        if df.empty:
            return {}

        sells = df[df["action"] == "sell"]
        days = sells["holding_days"].dropna()
        if days.empty:
            return {}

        bins = [0, 1, 3, 7, 14, 30, 60, 90, 180, 365, float("inf")]
        labels = [
            "当日", "1-3天", "3-7天", "1-2周", "2周-1月",
            "1-2月", "2-3月", "3-6月", "6月-1年", "1年以上",
        ]

        counts = pd.cut(days, bins=bins, labels=labels, right=True).value_counts()
        return {k: int(v) for k, v in counts.items() if v > 0}

"""回测引擎 — 基于历史K线数据模拟交易，评估策略表现

核心流程:
    1. 获取历史 K 线数据
    2. 计算技术指标 (FeatureEngine)
    3. 策略生成信号 (Strategy.generate_signals)
    4. 按信号模拟交易 (买入/卖出/持仓)
    5. 计算绩效指标 (胜率/收益率/最大回撤/夏普比率等)
    6. 输出回测报告 + 图表

用法:
    svc = BacktestService()
    result = svc.run("sh600519", strategy="macd_cross", days=180)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

from app.ai.feature_engine import FeatureEngine
from app.services.market_service import MarketService
from app.services.strategy import BaseStrategy, get_strategy

logger = logging.getLogger(__name__)


@dataclass
class TradeRecord:
    """单笔回测交易记录"""
    entry_date: str
    entry_price: float
    exit_date: str = ""
    exit_price: float = 0.0
    quantity: int = 100
    direction: str = "long"  # long / short
    profit: float = 0.0
    profit_rate: float = 0.0
    holding_days: int = 0
    exit_reason: str = ""  # signal / stop_loss / take_profit / timeout / end


@dataclass
class BacktestResult:
    """回测结果"""
    # 基本信息
    code: str = ""
    strategy_name: str = ""
    strategy_desc: str = ""
    period: str = "day"
    start_date: str = ""
    end_date: str = ""
    total_days: int = 0

    # 初始参数
    initial_capital: float = 100000.0
    commission_rate: float = 0.0003  # 手续费率 0.03%
    tax_rate: float = 0.001  # 印花税 0.1% (卖出收取)
    stop_loss: float = 0.0  # 止损比例 (0=不止损)
    take_profit: float = 0.0  # 止盈比例 (0=不止盈)

    # 绩效指标
    total_return: float = 0.0  # 总收益率 (%)
    annual_return: float = 0.0  # 年化收益率 (%)
    benchmark_return: float = 0.0  # 基准收益率 (买入持有)
    excess_return: float = 0.0  # 超额收益 (策略 - 基准)
    max_drawdown: float = 0.0  # 最大回撤 (%)
    max_drawdown_amount: float = 0.0  # 最大回撤金额
    sharpe_ratio: float = 0.0  # 夏普比率
    calmar_ratio: float = 0.0  # 卡玛比率 (年化收益/最大回撤)
    win_rate: float = 0.0  # 胜率 (%)
    profit_loss_ratio: float = 0.0  # 盈亏比
    total_trades: int = 0  # 总交易次数
    win_count: int = 0
    loss_count: int = 0
    avg_profit: float = 0.0  # 平均盈利 (%)
    avg_loss: float = 0.0  # 平均亏损 (%)
    max_profit: float = 0.0  # 单笔最大盈利 (%)
    max_loss: float = 0.0  # 单笔最大亏损 (%)
    avg_holding_days: float = 0.0  # 平均持仓天数
    total_commission: float = 0.0  # 总手续费
    total_tax: float = 0.0  # 总印花税

    # 资金曲线
    final_capital: float = 0.0
    net_profit: float = 0.0

    # 详细数据
    trades: list = field(default_factory=list)  # TradeRecord 列表
    equity_curve: Optional[pd.DataFrame] = None  # 权益曲线 DataFrame
    signals_df: Optional[pd.DataFrame] = None  # 信号数据

    def to_dict(self) -> dict:
        """转为可序列化的字典"""
        d = {}
        for k, v in self.__dict__.items():
            if k in ("equity_curve", "signals_df"):
                continue
            if k == "trades":
                d[k] = [t.__dict__ for t in v]
            else:
                d[k] = v
        return d


class BacktestService:
    """回测引擎"""

    def __init__(self):
        self.market = MarketService()
        self.feature_engine = FeatureEngine()

    def run(
        self,
        code: str,
        strategy: str = "macd_cross",
        days: int = 180,
        period: str = "day",
        initial_capital: float = 100000.0,
        commission_rate: float = 0.0003,
        tax_rate: float = 0.001,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        position_size: float = 1.0,
        **strategy_kwargs,
    ) -> BacktestResult:
        """运行回测

        Args:
            code: 股票代码
            strategy: 策略名称
            days: 回测天数 (K线数量)
            period: K线周期
            initial_capital: 初始资金
            commission_rate: 手续费率
            tax_rate: 印花税率 (卖出)
            stop_loss: 止损比例 (如 0.05 = 5%，0 = 不止损)
            take_profit: 止盈比例 (如 0.1 = 10%，0 = 不止盈)
            position_size: 仓位比例 (0~1, 每次买入使用可用资金的比例)
            **strategy_kwargs: 策略额外参数

        Returns:
            BacktestResult 回测结果
        """
        result = BacktestResult(
            code=code,
            strategy_name=strategy,
            period=period,
            initial_capital=initial_capital,
            commission_rate=commission_rate,
            tax_rate=tax_rate,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

        # 1. 获取历史数据 (多拉一些用于指标计算的预热期)
        fetch_count = min(days + 80, 2000)
        logger.info(f"回测 {code}: 获取 {fetch_count} 条 {period} K线...")
        df = self.market.get_kline_df(code, period, fetch_count, adjust="qfq")

        if df.empty or len(df) < 60:
            logger.error(f"数据不足: 获取到 {len(df)} 条, 至少需要 60 条")
            return result

        # 2. 计算技术指标
        logger.info("计算技术指标...")
        df = self.feature_engine.build_features(df, dropna=True)

        if df.empty:
            logger.error("特征计算后数据为空")
            return result

        # 截取回测区间 (取最后 days 条)
        if len(df) > days:
            df = df.tail(days).reset_index(drop=True)

        # 3. 生成策略信号
        logger.info(f"运行策略: {strategy}...")
        strat = get_strategy(strategy, **strategy_kwargs)
        result.strategy_desc = strat.description
        df = strat.generate_signals(df)

        # 4. 模拟交易
        logger.info("模拟交易...")
        self._simulate_trades(df, result, position_size)

        # 5. 计算绩效
        logger.info("计算绩效指标...")
        self._calculate_metrics(df, result)

        result.signals_df = df

        logger.info(f"回测完成: 总收益 {result.total_return:.2f}%, "
                     f"胜率 {result.win_rate:.1f}%, "
                     f"最大回撤 {result.max_drawdown:.2f}%")

        return result

    def _simulate_trades(
        self,
        df: pd.DataFrame,
        result: BacktestResult,
        position_size: float = 1.0,
    ):
        """按信号模拟交易，生成权益曲线"""
        capital = result.initial_capital
        position = 0  # 持仓股数
        entry_price = 0.0
        entry_date = ""
        entry_idx = 0
        total_commission = 0.0
        total_tax = 0.0
        trades = []

        # 每日权益
        equity_data = []
        buy_commission = 0.0  # 当前持仓的买入手续费 (用于计算单笔利润)

        for idx, (i, row) in enumerate(df.iterrows()):
            price = row["close"]
            date_str = row["date"].strftime("%Y-%m-%d") if hasattr(row["date"], "strftime") else str(row["date"])[:10]
            signal = row.get("signal", 0)

            # 持仓时检查止损/止盈
            if position > 0 and entry_price > 0:
                change_pct = (price - entry_price) / entry_price

                # 止损
                if result.stop_loss > 0 and change_pct <= -result.stop_loss:
                    signal = -1  # 强制卖出
                    exit_reason = "stop_loss"
                # 止盈
                elif result.take_profit > 0 and change_pct >= result.take_profit:
                    signal = -1  # 强制卖出
                    exit_reason = "take_profit"
                else:
                    exit_reason = "signal"
            else:
                exit_reason = "signal"

            # 执行交易
            if signal == 1 and position == 0:
                # 买入
                available = capital * position_size
                quantity = int(available / price / 100) * 100  # 按手（100股）取整
                if quantity >= 100:
                    cost = quantity * price
                    commission = max(cost * result.commission_rate, 5.0)  # 最低5元
                    total_commission += commission
                    capital -= (cost + commission)
                    position = quantity
                    entry_price = price
                    entry_date = date_str
                    entry_idx = idx
                    buy_commission = commission  # 记录买入手续费

            elif signal == -1 and position > 0:
                # 卖出
                revenue = position * price
                commission = max(revenue * result.commission_rate, 5.0)
                tax = revenue * result.tax_rate
                total_commission += commission
                total_tax += tax
                capital += (revenue - commission - tax)

                # 记录交易
                profit = (price - entry_price) * position - buy_commission - commission - tax
                profit_rate = (price - entry_price) / entry_price * 100 if entry_price > 0 else 0
                holding_days = idx - entry_idx

                trade = TradeRecord(
                    entry_date=entry_date,
                    entry_price=entry_price,
                    exit_date=date_str,
                    exit_price=price,
                    quantity=position,
                    profit=round(profit, 2),
                    profit_rate=round(profit_rate, 2),
                    holding_days=holding_days,
                    exit_reason=exit_reason,
                )
                trades.append(trade)

                position = 0
                entry_price = 0.0

            # 计算当日总权益 (现金 + 持仓市值)
            equity = capital + position * price
            equity_data.append({
                "date": row["date"],
                "close": price,
                "equity": equity,
                "capital": capital,
                "position": position,
                "position_value": position * price,
                "signal": signal,
            })

        # 如果最后一天还有持仓，强制平仓
        if position > 0:
            last_row = df.iloc[-1]
            price = last_row["close"]
            date_str = last_row["date"].strftime("%Y-%m-%d") if hasattr(last_row["date"], "strftime") else str(last_row["date"])[:10]
            revenue = position * price
            commission = max(revenue * result.commission_rate, 5.0)
            tax = revenue * result.tax_rate
            total_commission += commission
            total_tax += tax
            capital += (revenue - commission - tax)

            profit = (price - entry_price) * position - buy_commission - commission - tax
            profit_rate = (price - entry_price) / entry_price * 100 if entry_price > 0 else 0

            trade = TradeRecord(
                entry_date=entry_date,
                entry_price=entry_price,
                exit_date=date_str,
                exit_price=price,
                quantity=position,
                profit=round(profit, 2),
                profit_rate=round(profit_rate, 2),
                holding_days=len(df) - entry_idx - 1,
                exit_reason="end",
            )
            trades.append(trade)

            # 更新最后一天权益
            if equity_data:
                equity_data[-1]["equity"] = capital
                equity_data[-1]["position"] = 0
                equity_data[-1]["position_value"] = 0

        result.trades = trades
        result.total_commission = round(total_commission, 2)
        result.total_tax = round(total_tax, 2)
        result.final_capital = round(capital, 2)
        result.net_profit = round(capital - result.initial_capital, 2)

        # 构建权益曲线 DataFrame
        if equity_data:
            result.equity_curve = pd.DataFrame(equity_data)

    def _calculate_metrics(self, df: pd.DataFrame, result: BacktestResult):
        """计算绩效指标"""
        trades = result.trades
        initial = result.initial_capital

        if not df.empty:
            result.start_date = df.iloc[0]["date"].strftime("%Y-%m-%d") if hasattr(df.iloc[0]["date"], "strftime") else str(df.iloc[0]["date"])[:10]
            result.end_date = df.iloc[-1]["date"].strftime("%Y-%m-%d") if hasattr(df.iloc[-1]["date"], "strftime") else str(df.iloc[-1]["date"])[:10]
            result.total_days = len(df)

        # 总收益率
        result.total_return = round((result.final_capital - initial) / initial * 100, 2)

        # 年化收益率 (按250个交易日)
        if result.total_days > 0:
            years = result.total_days / 250
            if years > 0:
                if result.final_capital > 0 and initial > 0:
                    result.annual_return = round(
                        ((result.final_capital / initial) ** (1 / years) - 1) * 100, 2
                    )

        # 基准收益 (买入持有)
        if not df.empty:
            first_close = df.iloc[0]["close"]
            last_close = df.iloc[-1]["close"]
            result.benchmark_return = round((last_close - first_close) / first_close * 100, 2)
            result.excess_return = round(result.total_return - result.benchmark_return, 2)

        # 交易统计
        result.total_trades = len(trades)
        if trades:
            profits = [t.profit_rate for t in trades]
            wins = [p for p in profits if p > 0]
            losses = [p for p in profits if p < 0]

            result.win_count = len(wins)
            result.loss_count = len(losses)
            result.win_rate = round(len(wins) / len(trades) * 100, 1) if trades else 0

            result.avg_profit = round(np.mean(wins), 2) if wins else 0
            result.avg_loss = round(np.mean(losses), 2) if losses else 0
            result.max_profit = round(max(profits), 2) if profits else 0
            result.max_loss = round(min(profits), 2) if profits else 0

            # 盈亏比
            avg_win = abs(np.mean(wins)) if wins else 0
            avg_loss_abs = abs(np.mean(losses)) if losses else 0
            result.profit_loss_ratio = round(avg_win / avg_loss_abs, 2) if avg_loss_abs > 0 else float("inf")

            # 平均持仓天数
            holding_days = [t.holding_days for t in trades if t.holding_days > 0]
            result.avg_holding_days = round(np.mean(holding_days), 1) if holding_days else 0

        # 最大回撤
        if result.equity_curve is not None and not result.equity_curve.empty:
            equity = result.equity_curve["equity"].values
            peak = np.maximum.accumulate(equity)
            drawdown = (peak - equity) / peak * 100
            result.max_drawdown = round(np.max(drawdown), 2)
            result.max_drawdown_amount = round(np.max(peak - equity), 2)

            # 夏普比率 (无风险利率按3%年化)
            if len(equity) > 1:
                daily_returns = np.diff(equity) / equity[:-1]
                if np.std(daily_returns) > 0:
                    risk_free_daily = 0.03 / 250
                    excess_returns = daily_returns - risk_free_daily
                    result.sharpe_ratio = round(
                        np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(250), 2
                    )

            # 卡玛比率
            if result.max_drawdown > 0:
                result.calmar_ratio = round(result.annual_return / result.max_drawdown, 2)

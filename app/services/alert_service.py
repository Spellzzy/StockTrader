"""预警监控服务 - 规则管理 + 条件匹配引擎"""

import time
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import select, and_

from app.db.database import get_session
from app.models.alert import Alert, AlertHistory, AlertConditionType
from app.services.market_service import MarketService
from app.ai.feature_engine import FeatureEngine


class AlertService:
    """预警监控服务

    功能:
        1. CRUD 管理预警规则
        2. 条件匹配引擎（检测当前行情是否满足预警条件）
        3. 触发记录 + 历史查询
    """

    def __init__(self):
        self.session = get_session()
        self.market = MarketService()
        self.feature_engine = FeatureEngine()

    # ==================== CRUD ====================

    def add_alert(
        self,
        stock_code: str,
        condition_type: str,
        threshold: Optional[float] = None,
        repeat: bool = False,
        note: str = "",
    ) -> Alert:
        """添加预警规则

        Args:
            stock_code: 股票代码 (如 sh600519)
            condition_type: 条件类型 (price_above, rsi_below, macd_cross 等)
            threshold: 阈值 (价格/百分比，MACD金叉等信号类无需阈值)
            repeat: 触发后是否继续监控（可重复触发）
            note: 备注

        Returns:
            创建的 Alert 对象
        """
        # 验证条件类型
        try:
            ctype = AlertConditionType(condition_type)
        except ValueError:
            valid_types = [t.value for t in AlertConditionType]
            raise ValueError(
                f"无效的条件类型: {condition_type}\n"
                f"支持的类型: {', '.join(valid_types)}"
            )

        # 查询股票名称
        stock_name = ""
        try:
            quote_data = self.market.get_quote(stock_code)
            stock_name = quote_data.get(stock_code, {}).get("name", "")
        except Exception:
            pass

        # 生成人类可读描述
        condition_desc = self._build_condition_desc(ctype, threshold)

        alert = Alert(
            stock_code=stock_code,
            stock_name=stock_name,
            condition_type=condition_type,
            threshold=threshold,
            condition_desc=condition_desc,
            is_active=True,
            repeat=repeat,
            note=note,
        )

        self.session.add(alert)
        self.session.commit()
        self.session.refresh(alert)
        return alert

    def list_alerts(
        self,
        stock_code: str = "",
        active_only: bool = False,
    ) -> List[Alert]:
        """查询预警规则列表

        Args:
            stock_code: 按股票代码过滤
            active_only: 仅显示启用的

        Returns:
            预警规则列表
        """
        stmt = select(Alert).order_by(Alert.created_at.desc())

        if stock_code:
            stmt = stmt.where(Alert.stock_code == stock_code)
        if active_only:
            stmt = stmt.where(Alert.is_active == True)

        return list(self.session.execute(stmt).scalars().all())

    def get_alert(self, alert_id: int) -> Optional[Alert]:
        """根据 ID 获取预警规则"""
        return self.session.get(Alert, alert_id)

    def delete_alert(self, alert_id: int) -> bool:
        """删除预警规则"""
        alert = self.session.get(Alert, alert_id)
        if alert:
            self.session.delete(alert)
            self.session.commit()
            return True
        return False

    def toggle_alert(self, alert_id: int) -> Optional[Alert]:
        """启用/暂停预警规则"""
        alert = self.session.get(Alert, alert_id)
        if not alert:
            return None
        alert.is_active = not alert.is_active
        alert.updated_at = datetime.now()
        self.session.commit()
        self.session.refresh(alert)
        return alert

    def reset_alert(self, alert_id: int) -> Optional[Alert]:
        """重置预警（清除已触发状态，重新监控）"""
        alert = self.session.get(Alert, alert_id)
        if not alert:
            return None
        alert.is_triggered = False
        alert.is_active = True
        alert.updated_at = datetime.now()
        self.session.commit()
        self.session.refresh(alert)
        return alert

    # ==================== 条件匹配引擎 ====================

    def check_alerts(self, verbose: bool = False) -> List[dict]:
        """检测所有活跃预警，返回触发列表

        Args:
            verbose: 是否输出详细信息

        Returns:
            触发的预警列表 [{alert, trigger_value, message}, ...]
        """
        # 获取所有活跃且未触发（或可重复触发）的预警
        stmt = select(Alert).where(
            Alert.is_active == True,
            # 未触发 或 可重复触发
            ((Alert.is_triggered == False) | (Alert.repeat == True)),
        )
        alerts = list(self.session.execute(stmt).scalars().all())

        if not alerts:
            return []

        # 按股票分组，减少 API 请求
        code_alerts = {}
        for alert in alerts:
            code_alerts.setdefault(alert.stock_code, []).append(alert)

        triggered_list = []

        for stock_code, alert_group in code_alerts.items():
            try:
                # 获取行情数据
                quote_data = self.market.get_quote(stock_code)
                quote = quote_data.get(stock_code, {})

                if not quote or not quote.get("price"):
                    continue

                # 判断是否需要技术指标
                need_technical = any(
                    a.condition_type in (
                        "rsi_above", "rsi_below",
                        "macd_cross", "macd_dead",
                        "kdj_cross",
                        "boll_upper", "boll_lower",
                        "ma_bull",
                    )
                    for a in alert_group
                )

                tech_data = {}
                if need_technical:
                    tech_data = self._get_technical_snapshot(stock_code)

                # 逐条检测
                for alert in alert_group:
                    result = self._evaluate_condition(alert, quote, tech_data)
                    if result["triggered"]:
                        # 记录触发
                        trigger_info = self._record_trigger(alert, quote, result)
                        triggered_list.append(trigger_info)

            except Exception as e:
                if verbose:
                    print(f"  ⚠️ {stock_code} 检测异常: {e}")

        return triggered_list

    def _evaluate_condition(
        self,
        alert: Alert,
        quote: dict,
        tech_data: dict,
    ) -> dict:
        """评估单条预警条件

        Args:
            alert: 预警规则
            quote: 实时行情数据
            tech_data: 技术指标快照

        Returns:
            {"triggered": bool, "value": float, "message": str}
        """
        ctype = alert.condition_type
        threshold = alert.threshold
        price = quote.get("price", 0)
        change_pct = quote.get("change_percent", 0)
        volume = quote.get("volume", 0)
        turnover = quote.get("turnover", 0)

        # 价格类条件
        if ctype == "price_above":
            triggered = price > threshold
            return {
                "triggered": triggered,
                "value": price,
                "message": f"价格 {price:.2f} 突破 {threshold:.2f}" if triggered else "",
            }

        elif ctype == "price_below":
            triggered = price < threshold
            return {
                "triggered": triggered,
                "value": price,
                "message": f"价格 {price:.2f} 跌破 {threshold:.2f}" if triggered else "",
            }

        elif ctype == "change_above":
            triggered = change_pct > threshold
            return {
                "triggered": triggered,
                "value": change_pct,
                "message": f"涨幅 {change_pct:+.2f}% 超过 {threshold:.2f}%" if triggered else "",
            }

        elif ctype == "change_below":
            triggered = change_pct < -abs(threshold)
            return {
                "triggered": triggered,
                "value": change_pct,
                "message": f"跌幅 {change_pct:+.2f}% 超过 -{abs(threshold):.2f}%" if triggered else "",
            }

        elif ctype == "volume_above":
            vol_wan = volume / 10000  # 转为万手
            triggered = vol_wan > threshold
            return {
                "triggered": triggered,
                "value": vol_wan,
                "message": f"成交量 {vol_wan:.1f}万手 超过 {threshold:.1f}万手" if triggered else "",
            }

        elif ctype == "turnover_above":
            triggered = turnover > threshold
            return {
                "triggered": triggered,
                "value": turnover,
                "message": f"换手率 {turnover:.2f}% 超过 {threshold:.2f}%" if triggered else "",
            }

        # RSI 类条件
        elif ctype == "rsi_above":
            rsi = tech_data.get("rsi6", 50)
            triggered = rsi > threshold
            return {
                "triggered": triggered,
                "value": rsi,
                "message": f"RSI(6) = {rsi:.1f} 超买（>{threshold:.0f}）" if triggered else "",
            }

        elif ctype == "rsi_below":
            rsi = tech_data.get("rsi6", 50)
            triggered = rsi < threshold
            return {
                "triggered": triggered,
                "value": rsi,
                "message": f"RSI(6) = {rsi:.1f} 超卖（<{threshold:.0f}）" if triggered else "",
            }

        # MACD 类条件
        elif ctype == "macd_cross":
            macd_cross = tech_data.get("macd_cross", 0)
            triggered = macd_cross == 1
            dif = tech_data.get("macd_dif", 0)
            dea = tech_data.get("macd_dea", 0)
            return {
                "triggered": triggered,
                "value": macd_cross,
                "message": f"MACD 金叉! DIF={dif:.3f} 上穿 DEA={dea:.3f}" if triggered else "",
            }

        elif ctype == "macd_dead":
            macd_cross = tech_data.get("macd_cross", 0)
            triggered = macd_cross == -1
            dif = tech_data.get("macd_dif", 0)
            dea = tech_data.get("macd_dea", 0)
            return {
                "triggered": triggered,
                "value": macd_cross,
                "message": f"MACD 死叉! DIF={dif:.3f} 下穿 DEA={dea:.3f}" if triggered else "",
            }

        # KDJ 金叉
        elif ctype == "kdj_cross":
            k = tech_data.get("kdj_k", 50)
            d = tech_data.get("kdj_d", 50)
            k_prev = tech_data.get("kdj_k_prev", 50)
            d_prev = tech_data.get("kdj_d_prev", 50)
            triggered = k > d and k_prev <= d_prev
            return {
                "triggered": triggered,
                "value": k,
                "message": f"KDJ 金叉! K={k:.1f} 上穿 D={d:.1f}" if triggered else "",
            }

        # 布林带
        elif ctype == "boll_upper":
            upper = tech_data.get("boll_upper", 0)
            triggered = price > upper and upper > 0
            return {
                "triggered": triggered,
                "value": price,
                "message": f"突破布林上轨! 价格 {price:.2f} > 上轨 {upper:.2f}" if triggered else "",
            }

        elif ctype == "boll_lower":
            lower = tech_data.get("boll_lower", 0)
            triggered = price < lower and lower > 0
            return {
                "triggered": triggered,
                "value": price,
                "message": f"跌破布林下轨! 价格 {price:.2f} < 下轨 {lower:.2f}" if triggered else "",
            }

        # 均线多头排列
        elif ctype == "ma_bull":
            ma_bull = tech_data.get("ma_bull", 0)
            triggered = ma_bull == 1
            return {
                "triggered": triggered,
                "value": ma_bull,
                "message": f"均线多头排列! MA5 > MA10 > MA20" if triggered else "",
            }

        return {"triggered": False, "value": 0, "message": ""}

    def _get_technical_snapshot(self, stock_code: str) -> dict:
        """获取技术指标快照（最后一根K线的指标值）

        Args:
            stock_code: 股票代码

        Returns:
            技术指标字典
        """
        try:
            df = self.market.get_kline_df(stock_code, period="day", count=80)
            if df.empty or len(df) < 30:
                return {}

            df = self.feature_engine.build_features(df, dropna=True)
            if df.empty:
                return {}

            last = df.iloc[-1]
            prev = df.iloc[-2] if len(df) >= 2 else last

            return {
                "rsi6": float(last.get("rsi6", 50)),
                "rsi12": float(last.get("rsi12", 50)),
                "macd_dif": float(last.get("macd_dif", 0)),
                "macd_dea": float(last.get("macd_dea", 0)),
                "macd_hist": float(last.get("macd_hist", 0)),
                "macd_cross": int(last.get("macd_cross", 0)),
                "kdj_k": float(last.get("kdj_k", 50)),
                "kdj_d": float(last.get("kdj_d", 50)),
                "kdj_j": float(last.get("kdj_j", 50)),
                "kdj_k_prev": float(prev.get("kdj_k", 50)),
                "kdj_d_prev": float(prev.get("kdj_d", 50)),
                "boll_upper": float(last.get("boll_upper", 0)),
                "boll_mid": float(last.get("boll_mid", 0)),
                "boll_lower": float(last.get("boll_lower", 0)),
                "ma5": float(last.get("ma5", 0)),
                "ma10": float(last.get("ma10", 0)),
                "ma20": float(last.get("ma20", 0)),
                "ma_bull": int(last.get("ma_bull", 0)),
            }

        except Exception:
            return {}

    def _record_trigger(self, alert: Alert, quote: dict, result: dict) -> dict:
        """记录预警触发

        Args:
            alert: 触发的预警规则
            quote: 触发时的行情数据
            result: 评估结果

        Returns:
            触发信息字典
        """
        now = datetime.now()

        # 创建触发历史
        history = AlertHistory(
            alert_id=alert.id,
            stock_code=alert.stock_code,
            stock_name=alert.stock_name,
            condition_type=alert.condition_type,
            condition_desc=alert.condition_desc,
            trigger_value=result.get("value"),
            threshold=alert.threshold,
            message=result.get("message", ""),
            price=quote.get("price"),
            change_percent=quote.get("change_percent"),
            volume=quote.get("volume"),
            triggered_at=now,
        )
        self.session.add(history)

        # 更新预警状态
        alert.is_triggered = True
        alert.trigger_count += 1
        alert.last_triggered_at = now
        alert.updated_at = now

        # 如果不可重复触发，则停用
        if not alert.repeat:
            alert.is_active = False

        self.session.commit()

        return {
            "alert": alert,
            "history": history,
            "trigger_value": result.get("value"),
            "message": result.get("message", ""),
        }

    # ==================== 历史查询 ====================

    def list_history(
        self,
        stock_code: str = "",
        alert_id: Optional[int] = None,
        limit: int = 50,
    ) -> List[AlertHistory]:
        """查询触发历史

        Args:
            stock_code: 按股票代码过滤
            alert_id: 按预警规则 ID 过滤
            limit: 数量限制

        Returns:
            触发历史列表
        """
        stmt = select(AlertHistory).order_by(AlertHistory.triggered_at.desc())

        if stock_code:
            stmt = stmt.where(AlertHistory.stock_code == stock_code)
        if alert_id:
            stmt = stmt.where(AlertHistory.alert_id == alert_id)

        stmt = stmt.limit(limit)
        return list(self.session.execute(stmt).scalars().all())

    # ==================== 实时监控模式 ====================

    def watch_loop(
        self,
        codes: Optional[List[str]] = None,
        interval: int = 30,
        callback=None,
    ):
        """实时看盘循环（阻塞式）

        Args:
            codes: 要监控的股票代码列表（为空则使用自选股）
            interval: 刷新间隔（秒）
            callback: 每轮刷新后的回调 callback(quotes: dict, triggered: list)

        Yields:
            (quotes_dict, triggered_list) 每轮结果
        """
        if not codes:
            from app.services.watchlist_service import WatchlistService
            watched = WatchlistService().list_watched()
            codes = [s.code for s in watched]

        if not codes:
            return

        while True:
            try:
                # 批量获取行情
                quotes = self.market.get_quote(*codes)

                # 检测预警
                triggered = self.check_alerts()

                if callback:
                    callback(quotes, triggered)

                yield quotes, triggered

            except KeyboardInterrupt:
                break
            except Exception as e:
                yield {}, []

            time.sleep(interval)

    # ==================== 辅助方法 ====================

    @staticmethod
    def _build_condition_desc(ctype: AlertConditionType, threshold: Optional[float]) -> str:
        """生成人类可读的条件描述"""
        desc_map = {
            AlertConditionType.PRICE_ABOVE: f"价格突破 {threshold:.2f}" if threshold else "价格突破",
            AlertConditionType.PRICE_BELOW: f"价格跌破 {threshold:.2f}" if threshold else "价格跌破",
            AlertConditionType.CHANGE_ABOVE: f"涨幅超过 {threshold:.2f}%" if threshold else "涨幅超过",
            AlertConditionType.CHANGE_BELOW: f"跌幅超过 {threshold:.2f}%" if threshold else "跌幅超过",
            AlertConditionType.VOLUME_ABOVE: f"成交量超过 {threshold:.1f}万手" if threshold else "放量",
            AlertConditionType.RSI_ABOVE: f"RSI > {threshold:.0f} 超买" if threshold else "RSI超买",
            AlertConditionType.RSI_BELOW: f"RSI < {threshold:.0f} 超卖" if threshold else "RSI超卖",
            AlertConditionType.MACD_CROSS: "MACD 金叉",
            AlertConditionType.MACD_DEAD: "MACD 死叉",
            AlertConditionType.KDJ_CROSS: "KDJ 金叉",
            AlertConditionType.BOLL_UPPER: "突破布林上轨",
            AlertConditionType.BOLL_LOWER: "跌破布林下轨",
            AlertConditionType.MA_BULL: "均线多头排列",
            AlertConditionType.TURNOVER_ABOVE: f"换手率超过 {threshold:.2f}%" if threshold else "换手率异常",
        }
        return desc_map.get(ctype, str(ctype))

    @staticmethod
    def get_condition_types() -> List[dict]:
        """获取所有支持的条件类型及说明"""
        return [
            {"type": "price_above", "name": "价格突破", "need_threshold": True, "unit": "元"},
            {"type": "price_below", "name": "价格跌破", "need_threshold": True, "unit": "元"},
            {"type": "change_above", "name": "涨幅超过", "need_threshold": True, "unit": "%"},
            {"type": "change_below", "name": "跌幅超过", "need_threshold": True, "unit": "%"},
            {"type": "volume_above", "name": "成交量超过", "need_threshold": True, "unit": "万手"},
            {"type": "rsi_above", "name": "RSI 超买", "need_threshold": True, "unit": ""},
            {"type": "rsi_below", "name": "RSI 超卖", "need_threshold": True, "unit": ""},
            {"type": "macd_cross", "name": "MACD 金叉", "need_threshold": False, "unit": ""},
            {"type": "macd_dead", "name": "MACD 死叉", "need_threshold": False, "unit": ""},
            {"type": "kdj_cross", "name": "KDJ 金叉", "need_threshold": False, "unit": ""},
            {"type": "boll_upper", "name": "突破布林上轨", "need_threshold": False, "unit": ""},
            {"type": "boll_lower", "name": "跌破布林下轨", "need_threshold": False, "unit": ""},
            {"type": "ma_bull", "name": "均线多头排列", "need_threshold": False, "unit": ""},
            {"type": "turnover_above", "name": "换手率超过", "need_threshold": True, "unit": "%"},
        ]

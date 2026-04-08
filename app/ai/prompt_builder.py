"""Prompt 组装器 — 将多维数据组装成 LLM 可理解的结构化 Prompt

负责收集和格式化以下数据维度:
    - 技术面: K线数据 + 40+ 技术指标 + ML/DL 预测信号
    - 基本面: 财务数据 (营收、利润、PE/PB)
    - 资金面: 资金流向 (主力/散户)
    - 消息面: 近期新闻
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 系统 Prompt — 定义 LLM 的角色和输出格式
SYSTEM_PROMPT = """你是一位经验丰富的专业股票分析师，擅长技术分析、基本面分析和市场情绪判断。

## 你的职责
根据提供的多维数据，撰写一份简洁、专业的股票分析报告。

## 输出格式要求
你必须严格以 JSON 格式输出，包含以下字段:
{
  "technical_analysis": "技术面分析（100字内，重点看趋势、动量、支撑压力）",
  "fundamental_analysis": "基本面分析（100字内，重点看估值、盈利、增长）",
  "money_flow_analysis": "资金面分析（80字内，主力动向、北向资金等）",
  "news_sentiment": "positive/neutral/negative（消息面情绪判断）",
  "news_summary": "消息面简评（60字内）",
  "short_term_view": "短期操作建议（1-5日，50字内）",
  "mid_term_view": "中期操作建议（1-4周，50字内）",
  "risk_warnings": ["风险提示1", "风险提示2"],
  "confidence": 0-100之间的整数（你对这次分析的信心度）,
  "overall_rating": "强烈看多/看多/中性偏多/中性/中性偏空/看空/强烈看空"
}

## 分析原则
1. 客观理性，不带个人情绪
2. 多空观点兼顾，不盲目乐观或悲观
3. 必须基于提供的数据，不要编造不存在的数据
4. 风险提示要具体，不要泛泛而谈
5. 如果数据不足，在 confidence 中给出较低分值
"""


class PromptBuilder:
    """多维数据组装器 — 构建 LLM 分析所需的 Prompt"""

    def __init__(self):
        from app.services.market_service import MarketService
        self.market_service = MarketService()

    def build_analysis_prompt(
        self,
        code: str,
        prediction_result: Optional[dict] = None,
    ) -> dict:
        """组装完整的分析 Prompt

        Args:
            code: 股票代码
            prediction_result: PredictorService.predict() 的结果（可选）

        Returns:
            {"system": str, "user": str} — 分别是 system prompt 和 user prompt
        """
        sections = []
        sections.append(f"# 股票分析请求: {code}")
        sections.append("")

        # ── 1. 基本信息 ──
        profile_section = self._build_profile_section(code)
        if profile_section:
            sections.append(profile_section)

        # ── 2. 技术面数据 ──
        tech_section = self._build_technical_section(code, prediction_result)
        sections.append(tech_section)

        # ── 3. 基本面数据 ──
        fundamental_section = self._build_fundamental_section(code)
        if fundamental_section:
            sections.append(fundamental_section)

        # ── 4. 资金面数据 ──
        fund_section = self._build_fund_flow_section(code)
        if fund_section:
            sections.append(fund_section)

        # ── 5. 消息面数据 ──
        news_section = self._build_news_section(code)
        if news_section:
            sections.append(news_section)

        # ── 6. ML/DL 预测结果 ──
        if prediction_result:
            pred_section = self._build_prediction_section(prediction_result)
            sections.append(pred_section)

        sections.append("")
        sections.append("请基于以上多维数据，输出 JSON 格式的分析报告。")

        return {
            "system": SYSTEM_PROMPT,
            "user": "\n".join(sections),
        }

    # ==================== 各维度数据构建 ====================

    def _build_profile_section(self, code: str) -> Optional[str]:
        """构建公司简况"""
        try:
            data = self.market_service.get_profile(code)
            if not data or not isinstance(data, dict):
                return None

            # 解析 profile 数据
            info = data.get("data", data)
            if isinstance(info, dict):
                lines = ["## 公司简况"]
                for key in ["name", "industry", "total_capital", "circulating_capital",
                            "listing_date", "province"]:
                    val = info.get(key)
                    if val:
                        label_map = {
                            "name": "名称", "industry": "行业", "total_capital": "总股本",
                            "circulating_capital": "流通股本", "listing_date": "上市日期",
                            "province": "地区",
                        }
                        lines.append(f"- {label_map.get(key, key)}: {val}")
                return "\n".join(lines) if len(lines) > 1 else None
        except Exception as e:
            logger.debug(f"获取公司简况失败: {e}")
        return None

    def _build_technical_section(self, code: str, prediction_result: Optional[dict] = None) -> str:
        """构建技术面数据"""
        from app.ai.feature_engine import FeatureEngine

        lines = ["## 技术面数据"]

        try:
            # 获取 K线 + 技术指标
            df = self.market_service.get_kline_df(code, period="day", count=60, adjust="qfq")
            if df is not None and not df.empty:
                # 最近 5 日 K线摘要
                lines.append("### 近5日K线")
                recent = df.tail(5)
                for _, row in recent.iterrows():
                    date_str = row["date"].strftime("%m-%d") if hasattr(row["date"], "strftime") else str(row["date"])[:5]
                    chg = (row["close"] - row["open"]) / row["open"] * 100 if row["open"] > 0 else 0
                    lines.append(
                        f"  {date_str}: 开{row['open']:.2f} 收{row['close']:.2f} "
                        f"高{row['high']:.2f} 低{row['low']:.2f} "
                        f"涨跌{chg:+.2f}% 量{row['volume']:.0f}"
                    )

                # 计算技术指标
                fe = FeatureEngine()
                feat_df = fe.build_features(df, dropna=True)
                if not feat_df.empty:
                    latest = feat_df.iloc[-1]
                    lines.append("")
                    lines.append("### 技术指标快照（最新）")

                    indicator_groups = {
                        "趋势": ["ma5", "ma10", "ma20", "ma60", "ma_bull", "macd_dif", "macd_dea", "macd_hist", "macd_cross"],
                        "动量": ["rsi6", "rsi12", "rsi24", "kdj_k", "kdj_d", "kdj_j", "roc6", "roc12", "wr14"],
                        "波动": ["boll_upper", "boll_mid", "boll_lower", "boll_pct", "atr", "atr_pct"],
                        "成交量": ["vol_ratio", "obv_change", "vol_ma5", "vol_ma20"],
                        "价格": ["return_1d", "return_3d", "return_5d", "return_10d", "bias5", "bias10", "bias20"],
                    }

                    for group_name, cols in indicator_groups.items():
                        vals = []
                        for col in cols:
                            if col in latest.index:
                                v = latest[col]
                                if isinstance(v, float):
                                    vals.append(f"{col}={v:.2f}")
                                else:
                                    vals.append(f"{col}={v}")
                        if vals:
                            lines.append(f"  {group_name}: {', '.join(vals)}")
        except Exception as e:
            logger.debug(f"获取技术面数据失败: {e}")
            lines.append("  (技术面数据获取失败)")

        return "\n".join(lines)

    def _build_fundamental_section(self, code: str) -> Optional[str]:
        """构建基本面数据"""
        try:
            data = self.market_service.get_finance(code, "summary")
            if not data or not isinstance(data, dict):
                return None

            lines = ["## 基本面数据（财务摘要）"]
            info = data.get("data", data)
            if isinstance(info, dict):
                for key, label in [
                    ("total_revenue", "总营收"),
                    ("net_profit", "净利润"),
                    ("eps", "每股收益"),
                    ("roe", "ROE"),
                    ("pe_ratio", "市盈率"),
                    ("pb_ratio", "市净率"),
                    ("debt_ratio", "资产负债率"),
                    ("gross_margin", "毛利率"),
                    ("net_margin", "净利率"),
                ]:
                    val = info.get(key)
                    if val is not None:
                        lines.append(f"- {label}: {val}")
            elif isinstance(info, list) and len(info) > 0:
                # 有些返回是列表格式
                lines.append(f"  原始数据: {str(info)[:500]}")

            return "\n".join(lines) if len(lines) > 1 else None
        except Exception as e:
            logger.debug(f"获取基本面数据失败: {e}")
        return None

    def _build_fund_flow_section(self, code: str) -> Optional[str]:
        """构建资金面数据"""
        try:
            data = self.market_service.get_fund_flow(code, days=10)
            if not data or not isinstance(data, dict):
                return None

            lines = ["## 资金面数据（近10日资金流向）"]
            info = data.get("data", data)

            if isinstance(info, dict):
                # 尝试提取关键字段
                for key, label in [
                    ("main_net_inflow", "主力净流入"),
                    ("retail_net_inflow", "散户净流入"),
                    ("super_large_net_inflow", "超大单净流入"),
                    ("large_net_inflow", "大单净流入"),
                    ("medium_net_inflow", "中单净流入"),
                    ("small_net_inflow", "小单净流入"),
                ]:
                    val = info.get(key)
                    if val is not None:
                        lines.append(f"- {label}: {val}")

                # 如果有历史数据列表
                history = info.get("list", info.get("history", []))
                if isinstance(history, list) and len(history) > 0:
                    lines.append("  近期明细:")
                    for item in history[:5]:
                        if isinstance(item, dict):
                            date = item.get("date", item.get("trade_date", "?"))
                            main = item.get("main_net_inflow", item.get("主力净流入", "?"))
                            lines.append(f"    {date}: 主力净流入 {main}")
            elif isinstance(info, list) and len(info) > 0:
                lines.append(f"  原始数据: {str(info)[:500]}")

            return "\n".join(lines) if len(lines) > 1 else None
        except Exception as e:
            logger.debug(f"获取资金面数据失败: {e}")
        return None

    def _build_news_section(self, code: str) -> Optional[str]:
        """构建消息面数据"""
        try:
            data = self.market_service.get_news(code, page=1, size=5)
            if not data or not isinstance(data, dict):
                return None

            lines = ["## 消息面（近期新闻）"]
            info = data.get("data", data)

            news_list = []
            if isinstance(info, dict):
                news_list = info.get("list", info.get("news", info.get("items", [])))
            elif isinstance(info, list):
                news_list = info

            if not news_list:
                return None

            for i, news in enumerate(news_list[:5], 1):
                if isinstance(news, dict):
                    title = news.get("title", news.get("headline", ""))
                    date = news.get("date", news.get("publish_time", news.get("time", "")))
                    source = news.get("source", news.get("media", ""))
                    if title:
                        lines.append(f"{i}. [{date}] {title} ({source})")
                elif isinstance(news, str):
                    lines.append(f"{i}. {news}")

            return "\n".join(lines) if len(lines) > 1 else None
        except Exception as e:
            logger.debug(f"获取新闻数据失败: {e}")
        return None

    def _build_prediction_section(self, prediction_result: dict) -> str:
        """构建 ML/DL 预测结果摘要"""
        lines = ["## ML/DL 模型预测结果"]

        combined = prediction_result.get("combined", {})
        if combined:
            lines.append(f"- 综合信号: {combined.get('signal', '?')}")
            lines.append(f"- 综合评分: {combined.get('score', 0):+.1f} (-100~+100)")
            lines.append(f"- 置信度: {combined.get('confidence', 0):.1f}%")
            lines.append(f"- 星级: {'⭐' * combined.get('stars', 0)}")

            factors = combined.get("key_factors", [])
            if factors:
                lines.append(f"- 关键因子: {' | '.join(factors[:5])}")

        # 各模型明细
        for key, label in [("ml_xgb", "XGBoost"), ("ml_rf", "RandomForest"), ("dl", "LSTM")]:
            model_res = prediction_result.get(key)
            if model_res:
                sig = model_res.get("signal", "?")
                conf = model_res.get("confidence", 0)
                acc = model_res.get("model_accuracy", 0)
                lines.append(f"- {label}: {sig} ({conf:.1f}%, 模型准确率 {acc:.1%})")

        return "\n".join(lines)

"""智能日报服务 — 自动分析自选股并生成结论级摘要

核心功能:
    1. 批量 AI 扫描所有自选股 (ML/DL 预测)
    2. 对评分最高/最低的追加 LLM 深度分析
    3. 组装"每日智能简报"（人话结论）
    4. 通过通知渠道推送到手机

使用:
    from app.services.smart_digest import SmartDigestService
    svc = SmartDigestService()
    digest = svc.generate()       # 生成日报
    svc.generate_and_push()       # 生成 + 推送
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)


class SmartDigestService:
    """智能日报服务

    对自选股进行 AI 扫描 + LLM 分析，生成简报并推送。
    """

    # 追加 LLM 分析的数量（Top 看涨 + Top 看跌）
    LLM_TOP_N = 3
    LLM_BOTTOM_N = 2

    def __init__(self):
        self._predictor = None
        self._watchlist = None
        self._notifier = None

    @property
    def predictor(self):
        if self._predictor is None:
            from app.ai.predictor_service import PredictorService
            self._predictor = PredictorService()
        return self._predictor

    @property
    def watchlist(self):
        if self._watchlist is None:
            from app.services.watchlist_service import WatchlistService
            self._watchlist = WatchlistService()
        return self._watchlist

    @property
    def notifier(self):
        if self._notifier is None:
            from app.services.notification import NotificationManager
            self._notifier = NotificationManager()
        return self._notifier

    # ==================== 主入口 ====================

    def generate(
        self,
        use_dl: bool = False,
        use_llm: bool = False,
        top_n: int = 3,
        bottom_n: int = 2,
    ) -> Optional[dict]:
        """生成智能日报

        Args:
            use_dl: 是否使用深度学习模型
            use_llm: 是否对重点股票追加 LLM 分析
            top_n: 追加分析的看涨 Top N
            bottom_n: 追加分析的看跌 Top N

        Returns:
            {
                "date": str,
                "total": int,
                "scan_results": [...],  # AI 扫描结果列表
                "bullish": [...],       # 看涨股票（含可选 LLM 分析）
                "bearish": [...],       # 看跌/风险股票
                "neutral": [...],       # 震荡/中性
                "llm_reports": {...},   # code -> LLM 分析报告
                "summary_text": str,    # 人话摘要（Markdown）
                "plain_text": str,      # 纯文本摘要（用于终端显示）
            }
        """
        # 1. 获取自选股列表
        watched = self.watchlist.list_watched()
        if not watched:
            logger.warning("自选股列表为空")
            return None

        codes = [s.code for s in watched]
        # 构建 code -> name 映射
        code_names = {}
        for s in watched:
            code_names[s.code] = s.name or s.code

        logger.info(f"开始智能扫描 {len(codes)} 只自选股")

        # 2. AI 批量扫描
        scan_results = self.predictor.scan(codes, use_dl=use_dl)
        if not scan_results:
            logger.error("AI 扫描失败，无结果")
            return None

        # 3. 分类：看涨 / 看跌 / 震荡
        bullish = []
        bearish = []
        neutral = []

        for r in scan_results:
            code = r.get("code", "")
            combined = r.get("combined", {})
            signal = combined.get("signal", "震荡")
            item = {
                "code": code,
                "name": code_names.get(code, code),
                "signal": signal,
                "score": combined.get("score", 0),
                "confidence": combined.get("confidence", 0),
                "stars": combined.get("stars", 0),
                "key_factors": combined.get("key_factors", []),
            }

            if signal == "看涨":
                bullish.append(item)
            elif signal == "看跌":
                bearish.append(item)
            else:
                neutral.append(item)

        # 4. 可选 LLM 深度分析（对头部和尾部追加）
        llm_reports = {}
        if use_llm and self.predictor.has_llm:
            llm_targets = []
            # 看涨 Top N
            llm_targets.extend([b["code"] for b in bullish[:top_n]])
            # 看跌 Top N（从分数最低的开始）
            llm_targets.extend([b["code"] for b in bearish[:bottom_n]])

            for code in llm_targets:
                try:
                    logger.info(f"LLM 深度分析: {code}")
                    analysis = self.predictor.analyze(code, use_dl=use_dl)
                    report = analysis.get("report")
                    if report:
                        llm_reports[code] = report
                except Exception as e:
                    logger.error(f"LLM 分析 {code} 失败: {e}")

        # 5. 组装日报
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        digest = {
            "date": date_str,
            "total": len(codes),
            "scan_results": scan_results,
            "bullish": bullish,
            "bearish": bearish,
            "neutral": neutral,
            "llm_reports": llm_reports,
            "summary_text": "",
            "plain_text": "",
        }

        # 生成文本摘要
        digest["summary_text"] = self._build_markdown_digest(digest, code_names)
        digest["plain_text"] = self._build_plain_digest(digest, code_names)

        return digest

    def generate_and_push(
        self,
        use_dl: bool = False,
        use_llm: bool = False,
        top_n: int = 3,
        bottom_n: int = 2,
    ) -> dict:
        """生成日报并推送

        Returns:
            {
                "digest": dict | None,
                "push_results": [(渠道名, 成功, 错误), ...],
            }
        """
        from app.services.notification import NotificationLevel

        digest = self.generate(use_dl=use_dl, use_llm=use_llm,
                               top_n=top_n, bottom_n=bottom_n)
        if not digest:
            return {"digest": None, "push_results": []}

        # 推送
        push_results = []
        if self.notifier.is_enabled:
            push_results = self.notifier.notify(
                title=f"📊 自选股智能日报 ({digest['date']})",
                content=digest["summary_text"],
                level=NotificationLevel.INFO,
            )
        else:
            logger.warning("消息推送未启用或无已配置的渠道")

        return {"digest": digest, "push_results": push_results}

    # ==================== 文本组装 ====================

    def _build_markdown_digest(self, digest: dict, code_names: dict) -> str:
        """组装 Markdown 格式的智能日报"""
        lines = []
        lines.append(f"## 📊 自选股智能日报 ({digest['date']})\n")

        bullish = digest["bullish"]
        bearish = digest["bearish"]
        neutral = digest["neutral"]
        llm_reports = digest["llm_reports"]

        # 看涨区
        if bullish:
            lines.append("### 🟢 重点关注 (AI 看涨)\n")
            for i, item in enumerate(bullish, 1):
                stars = "⭐" * item["stars"]
                lines.append(
                    f"**{i}. {item['name']}** ({item['code']}) {stars}"
                )
                lines.append(
                    f"   信号: 看涨 | 评分: {item['score']:+.1f} | "
                    f"置信度: {item['confidence']:.1f}%"
                )
                if item["key_factors"]:
                    lines.append(f"   关键: {' | '.join(item['key_factors'][:3])}")

                # LLM 分析追加
                report = llm_reports.get(item["code"])
                if report:
                    short = report.get("short_term_view", "")
                    if short:
                        lines.append(f"   💡 建议: {short}")

                lines.append("")

        # 震荡区
        if neutral:
            lines.append("### 🟡 继续持有/观望\n")
            for item in neutral:
                factors_str = f" — {', '.join(item['key_factors'][:2])}" if item["key_factors"] else ""
                lines.append(
                    f"- **{item['name']}** ({item['code']}) — "
                    f"震荡整理中 (评分: {item['score']:+.1f}){factors_str}"
                )
            lines.append("")

        # 看跌区
        if bearish:
            lines.append("### 🔴 风险提示\n")
            for i, item in enumerate(bearish, 1):
                lines.append(
                    f"**{i}. {item['name']}** ({item['code']}) ⚠️"
                )
                lines.append(
                    f"   信号: 看跌 | 评分: {item['score']:+.1f} | "
                    f"置信度: {item['confidence']:.1f}%"
                )
                if item["key_factors"]:
                    lines.append(f"   风险: {' | '.join(item['key_factors'][:3])}")

                report = llm_reports.get(item["code"])
                if report:
                    short = report.get("short_term_view", "")
                    risks = report.get("risk_warnings", [])
                    if short:
                        lines.append(f"   💡 建议: {short}")
                    if risks:
                        lines.append(f"   ⚠️ {risks[0]}")

                lines.append("")

        # 汇总
        total = digest["total"]
        bull_count = len(bullish)
        bear_count = len(bearish)
        neut_count = len(neutral)
        lines.append("---")
        lines.append(
            f"📈 整体: {total}只自选股，"
            f"{bull_count}涨 {neut_count}平 {bear_count}跌"
        )
        lines.append(f"⏰ 生成时间: {digest['date']}")
        lines.append("\n*⚠️ 以上分析仅供参考，不构成投资建议*")

        return "\n".join(lines)

    def _build_plain_digest(self, digest: dict, code_names: dict) -> str:
        """组装纯文本格式的摘要（用于终端 Rich 渲染）"""
        lines = []

        bullish = digest["bullish"]
        bearish = digest["bearish"]
        neutral = digest["neutral"]
        llm_reports = digest["llm_reports"]

        if bullish:
            lines.append("[bold green]🟢 重点关注 (AI 看涨)[/bold green]")
            for i, item in enumerate(bullish, 1):
                stars = "⭐" * item["stars"]
                score_color = "green" if item["score"] > 0 else "red"
                lines.append(
                    f"  {i}. [bold]{item['name']}[/bold] ({item['code']}) {stars}"
                )
                lines.append(
                    f"     [{score_color}]信号: 看涨 | 评分: {item['score']:+.1f}[/{score_color}] | "
                    f"置信度: {item['confidence']:.1f}%"
                )
                if item["key_factors"]:
                    lines.append(f"     关键: {' | '.join(item['key_factors'][:3])}")

                report = llm_reports.get(item["code"])
                if report:
                    short = report.get("short_term_view", "")
                    if short:
                        lines.append(f"     [cyan]💡 {short}[/cyan]")
                lines.append("")

        if neutral:
            lines.append("[bold yellow]🟡 继续持有/观望[/bold yellow]")
            for item in neutral:
                lines.append(
                    f"  - [bold]{item['name']}[/bold] ({item['code']}) — "
                    f"震荡 (评分: {item['score']:+.1f})"
                )
            lines.append("")

        if bearish:
            lines.append("[bold red]🔴 风险提示[/bold red]")
            for i, item in enumerate(bearish, 1):
                lines.append(
                    f"  {i}. [bold]{item['name']}[/bold] ({item['code']}) ⚠️"
                )
                lines.append(
                    f"     [red]信号: 看跌 | 评分: {item['score']:+.1f}[/red] | "
                    f"置信度: {item['confidence']:.1f}%"
                )
                if item["key_factors"]:
                    lines.append(f"     风险: {' | '.join(item['key_factors'][:3])}")

                report = llm_reports.get(item["code"])
                if report:
                    short = report.get("short_term_view", "")
                    if short:
                        lines.append(f"     [cyan]💡 {short}[/cyan]")
                lines.append("")

        # 汇总
        total = digest["total"]
        lines.append(
            f"[dim]📈 整体: {total}只自选股，"
            f"{len(bullish)}涨 {len(neutral)}平 {len(bearish)}跌 | "
            f"⏰ {digest['date']}[/dim]"
        )

        return "\n".join(lines)

    # ==================== 自动预警配置 ====================

    def auto_configure_alerts(self, digest: dict) -> List[dict]:
        """根据 AI 扫描结果自动为高风险股票添加预警

        对看跌且评分较低的股票自动添加预警规则（如果尚未配置）

        Args:
            digest: generate() 返回的日报数据

        Returns:
            新增的预警配置列表
        """
        from app.services.alert_service import AlertService

        alert_svc = AlertService()
        new_alerts = []

        for item in digest.get("bearish", []):
            if item["score"] < -25:
                code = item["code"]
                # 检查是否已有活跃预警
                existing = alert_svc.list_alerts(stock_code=code, active_only=True)
                if not existing:
                    try:
                        # 添加跌幅预警
                        alert = alert_svc.add_alert(
                            stock_code=code,
                            condition="change_below",
                            threshold=-3.0,
                            note=f"[智能日报自动] AI 看跌 评分{item['score']:+.1f}",
                        )
                        new_alerts.append({
                            "code": code,
                            "name": item["name"],
                            "alert_id": alert.id if alert else None,
                            "condition": "change_below",
                            "threshold": -3.0,
                        })
                    except Exception as e:
                        logger.error(f"为 {code} 添加自动预警失败: {e}")

        return new_alerts

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
import math
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger(__name__)


def _finite_number(value):
    """只接受真数字。bool 是 int 的子类，不能当成降权或准确率。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if math.isnan(number):
        return None
    return number


def _quality_number(quality: dict, key: str):
    if key not in quality:
        return None
    return _finite_number(quality.get(key))


def _optional_metric(quality: dict, item: dict, key: str):
    """quality 里有可用数字就用它；显式 null 才回落到条目本身。"""
    if key in quality:
        number = _finite_number(quality.get(key))
        if number is not None:
            return number
        if quality.get(key) is not None:
            return None
    if key in item:
        return _finite_number(item.get(key))
    return None


def _format_count(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}"


def _quality_evidence_lines(quality: dict, item: dict) -> list:
    """有值才追加。弱/强判定、说明和依据不在这里改。"""
    lines = []
    accuracy = _quality_number(quality, "mean_accuracy")
    baseline = _quality_number(quality, "baseline")
    if accuracy is not None and baseline is not None:
        lines.append(f"- 准确率: {accuracy:.1%} · 基线 {baseline:.1%}")
    elif accuracy is not None:
        lines.append(f"- 准确率: {accuracy:.1%}")
    elif baseline is not None:
        lines.append(f"- 基线: {baseline:.1%}")

    factor = _quality_number(quality, "factor")
    if factor is not None:
        lines.append(f"- 降权: {factor:.2f}")

    confidence = _optional_metric(quality, item, "confidence")
    if confidence is not None:
        lines.append(f"- 置信度: {confidence:.1f}%")

    models_used = _optional_metric(quality, item, "models_used")
    if models_used is not None:
        lines.append(f"- 模型数: {_format_count(models_used)}")
    return lines


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
            quality = combined.get("quality")
            if quality is not None:
                item["quality"] = quality
            if combined.get("models_used") is not None:
                item["models_used"] = combined.get("models_used")

            if signal == "看涨":
                bullish.append(item)
            elif signal == "看跌":
                bearish.append(item)
            else:
                neutral.append(item)

        # 3.5 附加今日参考区间（统计口径；可做开关、限量，失败不影响日报）
        self._attach_trade_ranges(bullish + bearish + neutral, codes)

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

        # 5. 读取最近一次全市场摘选（只读快照，绝不在这里重跑扫描）
        try:
            from app.services.market_scan_service import MarketScanService
            market_picks = MarketScanService().latest() or {}
        except Exception as e:
            logger.warning(f"读取全市场摘选结果失败: {e}")
            market_picks = {}

        # 6. 组装日报
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        digest = {
            "market_picks": market_picks,
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


    # ==================== 今日参考区间 ====================

    @staticmethod
    def _attach_trade_ranges(items: list, codes: list) -> None:
        """给日报条目附加今日股价区间与买卖参考价。

        - 一次批量 quote，K 线仍逐只取（有本地缓存）
        - 按信号/评分排序后限量，避免日报因额外计算明显变慢
        - 单只失败只跳过该只，绝不中断日报生成
        """
        from app.config import get_config

        cfg = (get_config().get("digest") or {}).get("trade_range") or {}
        if not cfg.get("enabled", True) or not items:
            return
        max_codes = int(cfg.get("max_codes", 8) or 8)
        if max_codes <= 0:
            max_codes = len(items)

        from app.services.high_forecast_service import HighForecastService
        from app.services.market_service import MarketService

        market = MarketService()
        try:
            quotes = market.get_quote(*codes) or {}
        except Exception as e:
            logger.warning(f"日报区间行情获取失败，跳过: {e}")
            return

        service = HighForecastService(market=market)
        ranked = sorted(
            items,
            key=lambda x: (
                0 if x.get("signal") == "看涨" else 1,
                -abs(float(x.get("score") or 0)),
            ),
        )
        for item in ranked[:max_codes]:
            code = item.get("code")
            if not code:
                continue
            try:
                d = service.forecast(code, quote=quotes.get(code))
                q = d.get("quality") or {}
                item["trade_range"] = {
                    "low": d["day_range"]["low"],
                    "high": d["day_range"]["high"],
                    "buy": d["buy_ref"],
                    "sell": d["sell_ref"],
                    "stop_loss": d["stop_loss_ref"],
                    "stop_loss_pct": d["stop_loss_pct"],
                    "price": d["price"],
                    "prev_close": d["prev_close"],
                    "phase": d["phase"],
                    "as_of": d["as_of"],
                    "sample_days": d["basis"]["sample_days"],
                    "range_coverage": q.get("range_coverage"),
                    "note": "统计参考，非投资建议",
                }
            except Exception as e:
                logger.warning(f"日报区间计算失败 {code}: {e}")

    @staticmethod
    def _append_trade_range(lines: list, item: dict, indent: str) -> None:
        """把区间渲染成两行，措辞保持「参考」而非买卖指令。"""
        r = item.get("trade_range")
        if not isinstance(r, dict):
            return
        lines.append(
            f"{indent}📐 今日参考区间 {float(r['low']):.2f} ~ {float(r['high']):.2f}"
            f" · 买入参考 {float(r['buy']):.2f} · 卖出参考 {float(r['sell']):.2f}"
        )
        stop = r.get("stop_loss")
        stop_pct = r.get("stop_loss_pct")
        # 旧格式日报没有止损字段，静默省略该行
        if isinstance(stop, (int, float)) and isinstance(stop_pct, (int, float)):
            lines.append(
                f"{indent}   低价参考 {float(r['low']):.2f} · "
                f"止损参考 {float(stop):.2f}（较买入价 -{float(stop_pct):.1f}%）"
            )
        cov = r.get("range_coverage")
        extra = f" · 区间回测覆盖率 {float(cov) * 100:.0f}%" if isinstance(cov, (int, float)) else ""
        lines.append(
            f"{indent}   近 {r.get('sample_days', 0)} 日分位数（P25 低点 / P75 高点）{extra}；"
            "统计参考，非投资建议"
        )

    @staticmethod
    def _quality_warning(item: dict) -> Optional[str]:
        """弱模型警示文案；无 quality / 未低于基线则不提示。"""
        quality = item.get("quality")
        if not isinstance(quality, dict) or not quality.get("below_baseline"):
            return None
        note = quality.get("note")
        if isinstance(note, str) and note.strip():
            return note.strip()
        return "弱于基线，勿当强信号"

    @staticmethod
    def _credibility_card(item: dict) -> Optional[str]:
        """看涨/看跌可信摘要。无 quality 不渲染。

        与 ``_quality_warning`` 使用同一套 quality 读取：只认 dict，
        ``below_baseline`` 为真视为弱于基线。弱卡片标题带 ⚠️；
        强卡片只用「优于基线 / 质量正常」，不附加恐吓措辞。
        """
        quality = item.get("quality")
        if not isinstance(quality, dict):
            return None

        below = bool(quality.get("below_baseline"))
        note = quality.get("note")
        if isinstance(note, str) and note.strip():
            note_text = note.strip()
        elif below:
            note_text = "弱于基线，勿当强信号"
        else:
            note_text = "质量正常"

        score = item.get("score", 0) or 0
        stars = item.get("stars") or 0
        try:
            stars = int(stars)
        except (TypeError, ValueError):
            stars = 0
        if stars < 0:
            stars = 0

        lines = [
            "⚠️ 📎 可信摘要" if below else "📎 可信摘要",
            (
                f"- 信号: {item.get('signal', '')} · 评分 {float(score):+.1f} · "
                f"{'⭐' * stars}"
            ),
            f"- 质量: {'弱于基线' if below else '优于基线'}",
            f"- 说明: {note_text}",
        ]
        factors = item.get("key_factors") or []
        if isinstance(factors, (list, tuple)):
            shown = [str(factor).strip() for factor in list(factors)[:3] if str(factor).strip()]
            if shown:
                lines.append("- 依据: " + "、".join(shown))
        lines.extend(_quality_evidence_lines(quality, item))
        return "\n".join(lines)

    def _append_credibility_card(self, lines: list, item: dict, indent: str) -> None:
        card = self._credibility_card(item)
        if not card:
            return
        for line in card.splitlines():
            lines.append(f"{indent}{line}")

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
                self._append_credibility_card(lines, item, "   ")
                self._append_trade_range(lines, item, "   ")

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
                warn = self._quality_warning(item)
                if warn:
                    lines.append(f"  ⚠️ 可信度: {warn}")
                self._append_trade_range(lines, item, "  ")
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
                self._append_credibility_card(lines, item, "   ")
                self._append_trade_range(lines, item, "   ")

                report = llm_reports.get(item["code"])
                if report:
                    short = report.get("short_term_view", "")
                    risks = report.get("risk_warnings", [])
                    if short:
                        lines.append(f"   💡 建议: {short}")
                    if risks:
                        lines.append(f"   ⚠️ {risks[0]}")

                lines.append("")

        # 全市场摘选：只读最近一次扫描快照，不在这里重跑
        picks = digest.get("market_picks") or {}
        if picks.get("run_date"):
            lines.append("### 🔎 今日全市场摘选\n")
            lines.append(
                f"> 池 {picks.get('pool', '-')} {picks.get('universe_count', 0)} 只 → "
                f"预筛 {picks.get('candidate_count', 0)} 只 → "
                f"命中 {picks.get('hit_count', 0)} 只"
                f"（{picks.get('duration_seconds', 0)}s）\n"
            )
            if picks.get("hits"):
                for i, h in enumerate(picks["hits"][:10], 1):
                    reasons = "、".join(str(r[0]) for r in (h.get("matched") or [])[:3])
                    lines.append(
                        f"- **{h.get('name', '')}** ({h['code']}) — "
                        f"命中 {h.get('matched_count', 0)}/{h.get('total_rules', 0)} 条"
                        + (f"：{reasons}" if reasons else "")
                    )
            else:
                lines.append("本次没有股票满足当前条件组合。")
            lines.append("\n*摘选仅为技术面信号，不构成投资建议*\n")

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
                self._append_credibility_card(lines, item, "     ")
                self._append_trade_range(lines, item, "     ")

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
                warn = self._quality_warning(item)
                if warn:
                    lines.append(f"    [yellow]⚠️ 可信度: {warn}[/yellow]")
                self._append_trade_range(lines, item, "    ")
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
                self._append_credibility_card(lines, item, "     ")
                self._append_trade_range(lines, item, "     ")

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

        picks = digest.get("market_picks") or {}
        if picks.get("run_date"):
            lines.append("[bold cyan]🔎 今日全市场摘选[/bold cyan]")
            if picks.get("hits"):
                for i, h in enumerate(picks["hits"][:5], 1):
                    lines.append(
                        f"  {i}. [bold]{h.get('name', '')}[/bold] ({h['code']}) — "
                        f"命中 {h.get('matched_count', 0)} 条"
                    )
            else:
                lines.append(
                    f"  [dim]扫描 {picks.get('candidate_count', 0)} 只候选，本次无命中[/dim]"
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

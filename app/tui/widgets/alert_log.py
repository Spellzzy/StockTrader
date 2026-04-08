"""预警日志面板 Widget (优化版)

功能:
    - RichLog 滚动展示预警触发历史
    - 紧凑单行格式，避免右侧面板截断
    - 新触发的预警高亮显示
    - 支持检测当前预警状态
"""

from __future__ import annotations

from datetime import datetime

from textual.app import ComposeResult
from textual.widgets import Static, RichLog
from textual.widget import Widget

from rich.text import Text


class AlertLog(Widget):
    """预警日志面板"""

    MAX_LOG_LINES = 200  # 最大日志行数

    def compose(self) -> ComposeResult:
        yield Static(" 🔔 预警日志", classes="panel-title")
        yield RichLog(
            id="alert-richlog",
            highlight=True,
            markup=True,
            wrap=False,
            max_lines=self.MAX_LOG_LINES,
        )

    async def load_data(self) -> None:
        """加载预警历史 + 检测当前预警"""
        try:
            services = self.app.services

            # 1. 加载最近触发历史
            history = await services.run_sync(
                services.alert.list_history, limit=20
            )
            self._render_history(history)

            # 2. 检测当前预警（复用行情缓存）
            cache = services.quotes_cache
            if cache:
                triggered = await services.run_sync(
                    services.alert.check_alerts,
                    quotes_cache=cache,
                )
                for item in triggered:
                    self._append_trigger(item)

        except Exception as e:
            try:
                log = self.query_one("#alert-richlog", RichLog)
                if log.is_attached:
                    log.write(Text(f"! 加载失败: {e}", style="yellow"))
            except Exception:
                pass  # 面板尚未挂载，静默忽略

    def _render_history(self, history: list) -> None:
        """渲染历史预警记录 — 紧凑单行格式"""
        log = self.query_one("#alert-richlog", RichLog)
        log.clear()

        if not history:
            log.write(Text("暂无预警记录", style="dim"))
            return

        # 倒序显示（最新的在上面）
        for h in reversed(history):
            time_str = ""
            triggered_at = getattr(h, "triggered_at", None)
            if triggered_at:
                time_str = triggered_at.strftime("%m-%d %H:%M")

            name = getattr(h, "stock_name", "") or ""
            price = getattr(h, "price", None)
            change_pct = getattr(h, "change_percent", None)
            condition_type = getattr(h, "condition_type", "")

            # 条件类型 → 简短图标
            icon = self._condition_icon(condition_type)

            # 价格颜色
            price_color = "red" if (change_pct or 0) >= 0 else "green"

            # 紧凑单行: [04-08 14:51] 🚨 大庆华科 ¥19.36
            line = Text()
            line.append(f"[{time_str}]", style="dim")
            line.append(f" {icon} ", style="bold")
            line.append(f"{name[:4]}", style="bold")  # 名称最多4字

            if price is not None:
                line.append(f" ¥{price:.2f}", style=price_color)

            log.write(line)

    def _append_trigger(self, trigger_info: dict) -> None:
        """追加一条新触发的预警 — 紧凑格式"""
        log = self.query_one("#alert-richlog", RichLog)

        alert = trigger_info.get("alert")
        message = trigger_info.get("message", "")
        now = datetime.now().strftime("%H:%M:%S")

        name = getattr(alert, "stock_name", "") if alert else ""
        condition_type = getattr(alert, "condition_type", "") if alert else ""
        icon = self._condition_icon(condition_type)

        # 简化消息: 取核心部分
        short_msg = self._shorten_message(message)

        line = Text()
        line.append(f"[{now}]", style="dim")
        line.append(f" {icon} ", style="bold yellow")
        line.append(f"{name[:4]}", style="bold")
        line.append(f" {short_msg}", style="white")

        log.write(line)

    def append_notification_result(self, channel: str, success: bool) -> None:
        """追加推送结果日志 — 紧凑格式"""
        log = self.query_one("#alert-richlog", RichLog)
        icon = "✓" if success else "✗"
        style = "green" if success else "red"
        now = datetime.now().strftime("%H:%M:%S")

        line = Text()
        line.append(f"[{now}]", style="dim")
        line.append(f" {icon} {channel}", style=style)
        log.write(line)

    @staticmethod
    def _condition_icon(condition_type: str) -> str:
        """条件类型 → 简短图标"""
        icon_map = {
            "price_above": "↑",
            "price_below": "↓",
            "change_above": "📈",
            "change_below": "📉",
            "volume_above": "📊",
            "rsi_above": "⚡",
            "rsi_below": "⚡",
            "macd_cross": "🔥",
            "macd_dead": "💀",
            "kdj_cross": "⚡",
            "boll_upper": "↗",
            "boll_lower": "↘",
            "ma_bull": "🐂",
            "turnover_above": "🔄",
        }
        return icon_map.get(condition_type, "🚨")

    @staticmethod
    def _shorten_message(message: str) -> str:
        """缩短预警消息"""
        if not message:
            return ""
        # 移除 "价格 xxx 突破 xxx" 中的冗余
        msg = message.replace("价格 ", "¥").replace("突破 ", ">").replace("跌破 ", "<")
        msg = msg.replace("涨幅 ", "").replace("跌幅 ", "")
        msg = msg.replace("成交量 ", "量:").replace("换手率 ", "换:")
        # 限制长度
        if len(msg) > 24:
            msg = msg[:22] + ".."
        return msg

"""通知管理器 — 多渠道分发"""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from app.services.notification.base import (
    NotificationChannel,
    NotificationLevel,
    NotificationMessage,
)


class NotificationManager:
    """通知管理器

    负责:
        1. 从 config.yaml 读取渠道配置，自动初始化已启用的渠道
        2. 并行向所有已启用渠道分发消息
        3. 提供 notify() 同步入口和 async_notify() 异步入口
    """

    def __init__(self, config: Optional[dict] = None):
        """初始化管理器

        Args:
            config: notification 配置段 (来自 config.yaml)
                    若为 None 则自动从全局配置加载
        """
        if config is None:
            from app.config import get_config
            full_config = get_config()
            config = full_config.get("notification", {})

        self._config = config
        self._channels: Dict[str, NotificationChannel] = {}
        self._enabled = config.get("enabled", True)
        self._on_alert = config.get("on_alert", True)
        self._on_trade = config.get("on_trade", False)

        if self._enabled:
            self._init_channels()

    def _init_channels(self):
        """根据配置初始化所有已启用的渠道"""
        channels_config = self._config.get("channels", {})

        # 渠道名 → 模块和类名的映射
        channel_map = {
            "serverchan": ("app.services.notification.serverchan", "ServerChanChannel"),
            "pushplus": ("app.services.notification.pushplus", "PushPlusChannel"),
            "dingtalk": ("app.services.notification.dingtalk", "DingTalkChannel"),
            "feishu": ("app.services.notification.feishu", "FeishuChannel"),
            "telegram": ("app.services.notification.telegram", "TelegramChannel"),
            "email": ("app.services.notification.email_channel", "EmailChannel"),
            "wecom": ("app.services.notification.wecom", "WeComChannel"),
        }

        import importlib
        for ch_name, (module_path, class_name) in channel_map.items():
            ch_config = channels_config.get(ch_name, {})
            if not ch_config.get("enabled", False):
                continue

            try:
                module = importlib.import_module(module_path)
                channel_cls = getattr(module, class_name)
                channel = channel_cls(ch_config)
                self._channels[ch_name] = channel
            except Exception as e:
                print(f"[通知] ⚠️ 初始化渠道 {ch_name} 失败: {e}")

    @property
    def enabled_channels(self) -> List[str]:
        """已启用的渠道列表"""
        return list(self._channels.keys())

    @property
    def is_enabled(self) -> bool:
        """全局推送是否启用"""
        return self._enabled and bool(self._channels)

    def notify(
        self,
        title: str,
        content: str,
        level: NotificationLevel = NotificationLevel.ALERT,
        stock_code: str = "",
        stock_name: str = "",
        price: Optional[float] = None,
        change_percent: Optional[float] = None,
        channel: Optional[str] = None,
    ) -> List[Tuple[str, bool, str]]:
        """同步发送通知 (内部使用 asyncio.run)

        Args:
            title: 通知标题
            content: 通知内容
            level: 通知级别
            stock_code: 股票代码
            stock_name: 股票名称
            price: 当前价格
            change_percent: 涨跌幅
            channel: 指定渠道名(为空则发送到所有渠道)

        Returns:
            [(渠道名, 是否成功, 错误信息), ...]
        """
        if not self._enabled:
            return []

        # 按级别过滤
        if level == NotificationLevel.ALERT and not self._on_alert:
            return []
        if level == NotificationLevel.TRADE and not self._on_trade:
            return []

        msg = NotificationMessage(
            title=title,
            content=content,
            level=level,
            stock_code=stock_code,
            stock_name=stock_name,
            price=price,
            change_percent=change_percent,
            timestamp=datetime.now(),
        )

        # 使用 asyncio 并行发送
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 在已有事件循环中（少见场景），同步回退
                return self._sync_send(msg, channel)
            else:
                return loop.run_until_complete(self.async_notify(msg, channel))
        except RuntimeError:
            # 没有事件循环，创建新的
            return asyncio.run(self.async_notify(msg, channel))

    async def async_notify(
        self,
        message: NotificationMessage,
        channel: Optional[str] = None,
    ) -> List[Tuple[str, bool, str]]:
        """异步并行发送通知

        Args:
            message: 通知消息体
            channel: 指定渠道名(为空则发送到所有渠道)

        Returns:
            [(渠道名, 是否成功, 错误信息), ...]
        """
        if channel:
            channels = {channel: self._channels[channel]} if channel in self._channels else {}
        else:
            channels = self._channels

        if not channels:
            return []

        tasks = []
        for ch_name, ch in channels.items():
            tasks.append(self._send_with_catch(ch_name, ch, message))

        results = await asyncio.gather(*tasks)
        return list(results)

    async def _send_with_catch(
        self,
        name: str,
        channel: NotificationChannel,
        message: NotificationMessage,
    ) -> Tuple[str, bool, str]:
        """带异常捕获的发送"""
        try:
            success = await channel.send(message)
            return (name, success, "" if success else "发送返回失败")
        except Exception as e:
            return (name, False, str(e))

    def _sync_send(
        self,
        message: NotificationMessage,
        channel: Optional[str] = None,
    ) -> List[Tuple[str, bool, str]]:
        """同步降级发送（在已有事件循环运行时，用线程池执行异步代码）"""
        import concurrent.futures

        if channel:
            channels = {channel: self._channels[channel]} if channel in self._channels else {}
        else:
            channels = self._channels

        results = []

        def _run_in_new_loop(ch, msg):
            """在新线程的新事件循环中运行异步 send"""
            new_loop = asyncio.new_event_loop()
            try:
                return new_loop.run_until_complete(ch.send(msg))
            finally:
                new_loop.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(channels) or 1) as pool:
            futures = {}
            for ch_name, ch in channels.items():
                fut = pool.submit(_run_in_new_loop, ch, message)
                futures[ch_name] = fut

            for ch_name, fut in futures.items():
                try:
                    success = fut.result(timeout=30)
                    results.append((ch_name, success, "" if success else "发送返回失败"))
                except Exception as e:
                    results.append((ch_name, False, str(e)))

        return results

    def notify_alert(
        self,
        alert,
        quote: dict,
        trigger_message: str,
    ) -> List[Tuple[str, bool, str]]:
        """预警触发时的快捷通知

        Args:
            alert: Alert 对象
            quote: 行情数据
            trigger_message: 触发描述

        Returns:
            发送结果列表
        """
        return self.notify(
            title=f"预警触发 — {alert.stock_name or alert.stock_code}",
            content=trigger_message,
            level=NotificationLevel.ALERT,
            stock_code=alert.stock_code,
            stock_name=alert.stock_name or "",
            price=quote.get("price"),
            change_percent=quote.get("change_percent"),
        )

    def get_status(self) -> dict:
        """获取通知系统状态"""
        channels_config = self._config.get("channels", {})
        status = {
            "enabled": self._enabled,
            "on_alert": self._on_alert,
            "on_trade": self._on_trade,
            "channels": {},
        }
        for ch_name in ["serverchan", "pushplus", "dingtalk", "feishu",
                         "telegram", "email", "wecom"]:
            ch_conf = channels_config.get(ch_name, {})
            status["channels"][ch_name] = {
                "enabled": ch_conf.get("enabled", False),
                "connected": ch_name in self._channels,
            }
        return status

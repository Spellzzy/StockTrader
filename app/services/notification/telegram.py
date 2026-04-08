"""Telegram Bot 推送渠道

文档: https://core.telegram.org/bots/api
"""

import httpx

from app.services.notification.base import NotificationChannel, NotificationMessage


class TelegramChannel(NotificationChannel):
    """Telegram Bot 推送"""

    def __init__(self, config: dict):
        self._bot_token = config.get("bot_token", "")
        self._chat_id = config.get("chat_id", "")
        if not self._bot_token:
            raise ValueError("Telegram bot_token 未配置")
        if not self._chat_id:
            raise ValueError("Telegram chat_id 未配置")

    @property
    def name(self) -> str:
        return "Telegram"

    async def send(self, message: NotificationMessage) -> bool:
        """通过 Telegram Bot API 发送消息"""
        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": message.markdown,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=payload)
            result = resp.json()
            return result.get("ok", False)

"""PushPlus 推送渠道

官网: https://www.pushplus.plus
免费额度: 200条/天
"""

import httpx

from app.services.notification.base import NotificationChannel, NotificationMessage


class PushPlusChannel(NotificationChannel):
    """PushPlus 微信推送"""

    def __init__(self, config: dict):
        self._token = config.get("token", "")
        if not self._token:
            raise ValueError("PushPlus token 未配置")

    @property
    def name(self) -> str:
        return "PushPlus"

    async def send(self, message: NotificationMessage) -> bool:
        """通过 PushPlus API 发送消息"""
        url = "https://www.pushplus.plus/send"
        payload = {
            "token": self._token,
            "title": message.title,
            "content": message.markdown,
            "template": "markdown",
        }

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            result = resp.json()
            # PushPlus 返回 {"code": 200, "msg": "请求成功", ...}
            return result.get("code") == 200

"""Server酱 (ServerChan) 推送渠道

官网: https://sct.ftqq.com
免费额度: 5条/天
"""

import httpx

from app.services.notification.base import NotificationChannel, NotificationMessage


class ServerChanChannel(NotificationChannel):
    """Server酱微信推送"""

    def __init__(self, config: dict):
        self._send_key = config.get("send_key", "")
        if not self._send_key:
            raise ValueError("Server酱 send_key 未配置")

    @property
    def name(self) -> str:
        return "Server酱"

    async def send(self, message: NotificationMessage) -> bool:
        """通过 Server酱 API 发送消息"""
        url = f"https://sctapi.ftqq.com/{self._send_key}.send"
        data = {
            "title": message.title[:32],  # Server酱标题限32字
            "desp": message.markdown,
        }

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, data=data)
            result = resp.json()
            # Server酱返回 {"code": 0, "message": "success", ...}
            return result.get("code") == 0

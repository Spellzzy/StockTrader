"""企业微信群机器人推送渠道

文档: https://developer.work.weixin.qq.com/document/path/91770
"""

import httpx

from app.services.notification.base import NotificationChannel, NotificationMessage


class WeComChannel(NotificationChannel):
    """企业微信群机器人推送"""

    def __init__(self, config: dict):
        self._webhook = config.get("webhook", "")
        if not self._webhook:
            raise ValueError("企业微信 webhook 未配置")

    @property
    def name(self) -> str:
        return "企业微信"

    async def send(self, message: NotificationMessage) -> bool:
        """通过企业微信 Webhook 发送 Markdown 消息"""
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": message.markdown,
            },
        }

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(self._webhook, json=payload)
            result = resp.json()
            # 企业微信返回 {"errcode": 0, "errmsg": "ok"}
            return result.get("errcode") == 0

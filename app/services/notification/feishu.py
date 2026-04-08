"""飞书群机器人推送渠道

文档: https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot
"""

import hashlib
import hmac
import base64
import time

import httpx

from app.services.notification.base import NotificationChannel, NotificationMessage


class FeishuChannel(NotificationChannel):
    """飞书群机器人推送"""

    def __init__(self, config: dict):
        self._webhook = config.get("webhook", "")
        self._secret = config.get("secret", "")
        if not self._webhook:
            raise ValueError("飞书 webhook 未配置")

    @property
    def name(self) -> str:
        return "飞书"

    def _gen_sign(self) -> tuple:
        """生成签名 (timestamp, sign)"""
        if not self._secret:
            return None, None

        timestamp = str(int(time.time()))
        string_to_sign = f"{timestamp}\n{self._secret}"
        hmac_code = hmac.new(
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        sign = base64.b64encode(hmac_code).decode("utf-8")
        return timestamp, sign

    async def send(self, message: NotificationMessage) -> bool:
        """通过飞书 Webhook 发送富文本消息"""
        timestamp, sign = self._gen_sign()

        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": message.title,
                    },
                    "template": "red" if message.level.value == "alert" else "blue",
                },
                "elements": [
                    {
                        "tag": "markdown",
                        "content": message.markdown,
                    }
                ],
            },
        }

        if timestamp and sign:
            payload["timestamp"] = timestamp
            payload["sign"] = sign

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(self._webhook, json=payload)
            result = resp.json()
            # 飞书返回 {"StatusCode": 0, "StatusMessage": "success"}
            return result.get("StatusCode") == 0 or result.get("code") == 0

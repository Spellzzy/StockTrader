"""钉钉群机器人推送渠道

文档: https://open.dingtalk.com/document/robots/custom-robot-access
"""

import hashlib
import hmac
import base64
import time
import urllib.parse

import httpx

from app.services.notification.base import NotificationChannel, NotificationMessage


class DingTalkChannel(NotificationChannel):
    """钉钉群机器人推送"""

    def __init__(self, config: dict):
        self._webhook = config.get("webhook", "")
        self._secret = config.get("secret", "")
        if not self._webhook:
            raise ValueError("钉钉 webhook 未配置")

    @property
    def name(self) -> str:
        return "钉钉"

    def _sign_url(self) -> str:
        """生成带签名的 webhook URL"""
        if not self._secret:
            return self._webhook

        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{self._secret}"
        hmac_code = hmac.new(
            self._secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        return f"{self._webhook}&timestamp={timestamp}&sign={sign}"

    async def send(self, message: NotificationMessage) -> bool:
        """通过钉钉 Webhook 发送 Markdown 消息"""
        url = self._sign_url()
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": message.title,
                "text": message.markdown,
            },
        }

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            result = resp.json()
            # 钉钉返回 {"errcode": 0, "errmsg": "ok"}
            return result.get("errcode") == 0

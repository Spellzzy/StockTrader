"""邮件 SMTP 推送渠道"""

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.services.notification.base import NotificationChannel, NotificationMessage


class EmailChannel(NotificationChannel):
    """邮件 SMTP 推送"""

    def __init__(self, config: dict):
        self._smtp_host = config.get("smtp_host", "smtp.qq.com")
        self._smtp_port = config.get("smtp_port", 465)
        self._username = config.get("username", "")
        self._password = config.get("password", "")
        self._to = config.get("to", "")
        self._use_ssl = config.get("use_ssl", True)

        if not self._username:
            raise ValueError("邮件 username 未配置")
        if not self._password:
            raise ValueError("邮件 password (SMTP授权码) 未配置")
        if not self._to:
            raise ValueError("邮件收件地址 to 未配置")

    @property
    def name(self) -> str:
        return "邮件"

    async def send(self, message: NotificationMessage) -> bool:
        """通过 SMTP 发送邮件 (用 asyncio.to_thread 避免阻塞事件循环)"""
        import asyncio
        return await asyncio.to_thread(self._send_sync, message)

    def _send_sync(self, message: NotificationMessage) -> bool:
        """同步 SMTP 发送（在线程池中执行）"""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[Stock AI] {message.title}"
        msg["From"] = self._username
        msg["To"] = self._to

        # 纯文本 + HTML 双版本
        text_part = MIMEText(message.plain_text, "plain", "utf-8")
        html_content = self._to_html(message)
        html_part = MIMEText(html_content, "html", "utf-8")

        msg.attach(text_part)
        msg.attach(html_part)

        if self._use_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(self._smtp_host, self._smtp_port, context=context, timeout=10) as server:
                server.login(self._username, self._password)
                server.sendmail(self._username, [self._to], msg.as_string())
        else:
            context = ssl.create_default_context()
            with smtplib.SMTP(self._smtp_host, self._smtp_port, timeout=10) as server:
                server.starttls(context=context)
                server.login(self._username, self._password)
                server.sendmail(self._username, [self._to], msg.as_string())
        return True

    @staticmethod
    def _to_html(message: NotificationMessage) -> str:
        """生成 HTML 邮件正文"""
        chg_color = "#00b894" if (message.change_percent or 0) >= 0 else "#d63031"
        price_html = f"<p>当前价: <strong>{message.price:.2f}</strong></p>" if message.price else ""
        chg_html = ""
        if message.change_percent is not None:
            sign = "+" if message.change_percent >= 0 else ""
            chg_html = f'<p>涨跌幅: <span style="color:{chg_color};font-weight:bold;">{sign}{message.change_percent:.2f}%</span></p>'

        return f"""
        <div style="font-family:Arial,sans-serif;max-width:500px;margin:0 auto;padding:20px;border:1px solid #dfe6e9;border-radius:8px;">
            <h2 style="color:#2d3436;border-bottom:2px solid #0984e3;padding-bottom:8px;">
                {message.title}
            </h2>
            <p><strong>股票:</strong> {message.stock_name or ''} ({message.stock_code})</p>
            <p><strong>详情:</strong> {message.content}</p>
            {price_html}
            {chg_html}
            <p style="color:#636e72;font-size:0.9em;">
                时间: {message.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
            </p>
            <hr style="border:none;border-top:1px solid #dfe6e9;">
            <p style="color:#b2bec3;font-size:0.8em;text-align:center;">
                Stock Trader AI · 预警推送
            </p>
        </div>
        """

"""统一日志配置

- CLI 展示继续走 Rich console，日志只写文件（避免干扰终端输出）
- 日志中的密钥（token / api_key / password / secret / webhook）会自动打码
"""

import logging
import re
from pathlib import Path
from typing import Optional

DEFAULT_LOG_DIR = "./logs"

# 需要打码的字段名
SENSITIVE_FIELDS = (
    "token", "api_key", "apikey", "api-key",
    "password", "secret", "send_key", "webhook",
)

_REDACT_PATTERN = re.compile(
    r"(?i)\b(" + "|".join(SENSITIVE_FIELDS) + r")\b(['\"]?\s*[:=]\s*['\"]?)([^\s,;'\"}\)]+)"
)


def redact(text: str) -> str:
    """把日志文本里的密钥替换为 ***"""
    if not text:
        return text
    return _REDACT_PATTERN.sub(lambda m: f"{m.group(1)}{m.group(2)}***", text)


class SecretRedactor(logging.Filter):
    """日志脱敏过滤器"""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact(str(record.msg))
            if record.args:
                record.args = tuple(
                    redact(str(a)) if isinstance(a, str) else a for a in record.args
                )
        except Exception:
            pass
        return True


def setup_logging(
    level: str = "INFO",
    log_dir: Optional[str] = None,
    log_file: str = "stock-ai.log",
    console: bool = False,
) -> logging.Logger:
    """配置根 logger

    Args:
        level: 日志级别
        log_dir: 日志目录，None 表示使用项目根目录下的 logs/
        log_file: 日志文件名
        console: 是否同时输出到 stderr（默认关闭，避免干扰 CLI 展示）

    Returns:
        根 logger
    """
    if log_dir is None:
        from app.config import PROJECT_ROOT

        log_dir = str(Path(PROJECT_ROOT) / "logs")

    Path(log_dir).mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(getattr(logging, str(level).upper(), logging.INFO))

    # 避免重复添加 handler（CLI / TUI / 脚本可能多次调用）
    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    redactor = SecretRedactor()

    file_handler = logging.FileHandler(Path(log_dir) / log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.addFilter(redactor)
    root.addHandler(file_handler)

    if console:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        stream_handler.addFilter(redactor)
        root.addHandler(stream_handler)

    return root

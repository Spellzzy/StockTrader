"""统一日志与密钥脱敏"""

import logging

from app.logging_setup import SecretRedactor, redact, setup_logging


def test_redact_masks_token():
    assert "abc123" not in redact("pushplus token=abc123")
    assert redact("token=abc123") == "token=***"


def test_redact_handles_json_and_quotes():
    assert 'api_key": "sk-xxx"' not in redact('{"api_key": "sk-xxx"}')
    assert "secret: hunter2" not in redact("secret: hunter2")


def test_redact_keeps_normal_text():
    text = "回测 sh600519 完成，收益率 8.83%"
    assert redact(text) == text


def test_setup_logging_creates_file(tmp_path):
    logger = setup_logging(level="DEBUG", log_dir=str(tmp_path))

    logging.getLogger("test.scope").info("hello token=zzz")
    for handler in logger.handlers:
        handler.flush()

    content = (tmp_path / "stock-ai.log").read_text(encoding="utf-8")
    assert "hello" in content
    assert "zzz" not in content


def test_setup_logging_is_idempotent(tmp_path):
    logger = setup_logging(log_dir=str(tmp_path))
    first = len(logger.handlers)
    setup_logging(log_dir=str(tmp_path))
    assert len(logger.handlers) == first


def test_secret_redactor_filter():
    record = logging.LogRecord("n", logging.INFO, "p", 1, "token=plain", None, None)
    assert SecretRedactor().filter(record) is True
    assert record.msg == "token=***"

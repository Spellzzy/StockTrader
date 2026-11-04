"""券商通道注册表

默认 manual（人工确认）。真实通道必须显式改 broker.name 且打开 broker.enabled。
"""

from app.services.broker.base import Broker, BrokerError, BrokerResult
from app.services.broker.manual import ManualBroker
from app.services.broker.mock import MockBroker
from app.services.broker.paper import PaperBrokerAdapter

_REGISTRY = {
    "manual": ManualBroker,
    "mock": MockBroker,
    "paper": PaperBrokerAdapter,
}

__all__ = [
    "Broker", "BrokerError", "BrokerResult", "ManualBroker", "MockBroker",
    "PaperBrokerAdapter", "get_broker", "available_brokers",
]


def available_brokers() -> list[str]:
    return sorted(_REGISTRY)


def get_broker(name: str = "", cfg: dict | None = None, **kwargs) -> Broker:
    """按配置构造通道"""
    if cfg is None:
        from app.config import get_config

        cfg = get_config()

    broker_cfg = cfg.get("broker", {}) or {}
    name = (name or broker_cfg.get("name") or "manual").lower()

    if name not in _REGISTRY:
        raise BrokerError(
            f"未知券商通道 {name!r}，可用: {', '.join(available_brokers())}"
        )

    if name == "manual":
        return ManualBroker(draft_dir=broker_cfg.get("draft_dir", "./data/orders"))

    return _REGISTRY[name](**kwargs)

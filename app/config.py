"""全局配置管理

配置优先级（后者覆盖前者）:
    DEFAULT_CONFIG < config.yaml < 环境变量

环境变量规则:
    前缀 STOCK_AI_，用双下划线分隔层级，段名与键名大小写不敏感。
    例: STOCK_AI_AI__LLM__API_KEY        → ai.llm.api_key
        STOCK_AI_NOTIFICATION__PUSHPLUS__TOKEN → notification.pushplus.token
    推荐用环境变量存放密钥，避免写入 config.yaml。
    值会尝试解析为 bool / int / float，失败则保留字符串。
"""

import copy
import os
import yaml
from pathlib import Path
from typing import Any, Optional

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.resolve()

ENV_PREFIX = "STOCK_AI_"
ENV_SEPARATOR = "__"

# 默认配置
DEFAULT_CONFIG = {
    "database": {
        "path": "./data/stock_trader.db",
    },
    "stock_data": {
        "bin_path": "stock-data",
    },
    "color_scheme": "red_up",  # red_up=红涨绿跌(A股) / green_up=绿涨红跌(美股)
    "market": {
        "default": "A",
    },
    "cache": {
        "enabled": True,
        "dir": "./data/cache",
        "expire_minutes": 30,
    },
    "visualization": {
        "default_backend": "matplotlib",
        "theme": "dark",
        "save_dir": "./data/charts",
    },
    "fees": {
        "commission_rate": 0.0003,   # 佣金费率 万3
        "min_commission": 5.0,       # 单笔最低佣金
        "stamp_tax_rate": 0.001,     # 印花税 千1（仅 A 股卖出）
    },
    "backtest": {
        "fill_mode": "next_open",    # next_open=信号次日开盘成交 / close=信号当日收盘成交(含前视偏差)
        "slippage": 0.0,             # 滑点比例
    },
    "ai": {
        "llm": {
            "provider": "openai",
            "api_key": "",
            "model": "gpt-4o",
        },
        "model": {
            "save_dir": "./data/models",
        },
    },
}


def _coerce_env_value(raw: str) -> Any:
    """把环境变量字符串转成 bool / int / float，失败则保留原字符串"""
    lowered = raw.strip().lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    if lowered in ("none", "null", ""):
        return None
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


def _set_nested(config: dict, path: list[str], value: Any):
    """按路径写入嵌套字典，缺失的中间层自动创建"""
    node = config
    for key in path[:-1]:
        child = node.get(key)
        if not isinstance(child, dict):
            child = {}
            node[key] = child
        node = child
    node[path[-1]] = value


def _match_key(node: dict, wanted: str) -> Optional[str]:
    """在字典中按大小写不敏感查找键，返回真实键名"""
    if wanted in node:
        return wanted
    lowered = wanted.lower()
    for key in node:
        if isinstance(key, str) and key.lower() == lowered:
            return key
    return None


def _apply_env_overrides(config: dict):
    """应用 STOCK_AI_* 环境变量覆盖（优先级最高）"""
    for env_key, raw_value in os.environ.items():
        if not env_key.startswith(ENV_PREFIX):
            continue

        parts = [p for p in env_key[len(ENV_PREFIX):].split(ENV_SEPARATOR) if p]
        if not parts:
            continue

        # 逐层解析出真实键名（大小写不敏感）
        path: list[str] = []
        node = config
        for part in parts:
            real_key = _match_key(node, part) if isinstance(node, dict) else None
            if real_key is None:
                real_key = part.lower()
            path.append(real_key)
            if isinstance(node, dict) and real_key in node:
                node = node[real_key]

        _set_nested(config, path, _coerce_env_value(raw_value))


def load_config() -> dict:
    """加载配置：默认值 → config.yaml → 环境变量"""
    config_path = PROJECT_ROOT / "config.yaml"
    # 必须深拷贝：否则对返回值的合并/路径转换会污染模块级 DEFAULT_CONFIG
    config = copy.deepcopy(DEFAULT_CONFIG)

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            user_config = yaml.safe_load(f)
            if user_config:
                _deep_merge(config, user_config)

    _apply_env_overrides(config)

    # 将相对路径转为绝对路径
    config["database"]["path"] = str(
        PROJECT_ROOT / config["database"]["path"]
    )
    config["cache"]["dir"] = str(PROJECT_ROOT / config["cache"]["dir"])
    config["visualization"]["save_dir"] = str(
        PROJECT_ROOT / config["visualization"]["save_dir"]
    )
    config["ai"]["model"]["save_dir"] = str(
        PROJECT_ROOT / config["ai"]["model"]["save_dir"]
    )

    return config


def _deep_merge(base: dict, override: dict):
    """深度合并字典"""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


# 全局配置单例
_config = None


def get_config() -> dict:
    """获取全局配置（懒加载单例）"""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def get_fee_model():
    """获取费率模型（交易录入与回测共用）"""
    from app.domain.fees import FeeModel

    return FeeModel.from_config(get_config())


def get_db_path() -> str:
    """获取数据库路径"""
    return get_config()["database"]["path"]


def get_stock_data_bin() -> str:
    """获取 stock-data 可执行文件路径"""
    return get_config()["stock_data"]["bin_path"]

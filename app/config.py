"""全局配置管理"""

import os
import yaml
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.resolve()

# 默认配置
DEFAULT_CONFIG = {
    "database": {
        "path": "./data/stock_trader.db",
    },
    "stock_data": {
        "bin_path": "stock-data",
    },
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
    "ai": {
        "llm": {
            "provider": "openai",
            "api_key": "",
            "model": "gpt-4",
        },
        "model": {
            "save_dir": "./data/models",
        },
    },
}


def load_config() -> dict:
    """加载配置文件，合并默认配置"""
    config_path = PROJECT_ROOT / "config.yaml"
    config = DEFAULT_CONFIG.copy()

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            user_config = yaml.safe_load(f)
            if user_config:
                _deep_merge(config, user_config)

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


def get_db_path() -> str:
    """获取数据库路径"""
    return get_config()["database"]["path"]


def get_stock_data_bin() -> str:
    """获取 stock-data 可执行文件路径"""
    return get_config()["stock_data"]["bin_path"]

"""配置加载"""

import os

import app.config as config_mod


def test_default_config_has_required_sections():
    for section in ("database", "stock_data", "market", "cache", "visualization", "ai"):
        assert section in config_mod.DEFAULT_CONFIG


def test_get_config_returns_singleton():
    assert config_mod.get_config() is config_mod.get_config()


def test_load_config_absolutizes_paths():
    cfg = config_mod.load_config()

    assert os.path.isabs(cfg["database"]["path"])
    assert os.path.isabs(cfg["cache"]["dir"])
    assert os.path.isabs(cfg["visualization"]["save_dir"])
    assert os.path.isabs(cfg["ai"]["model"]["save_dir"])

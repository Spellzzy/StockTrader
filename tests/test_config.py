"""配置加载"""

import copy
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


def test_load_config_does_not_mutate_defaults():
    """load_config 必须基于默认值的深拷贝，否则会污染模块级 DEFAULT_CONFIG"""
    before = copy.deepcopy(config_mod.DEFAULT_CONFIG)
    config_mod.load_config()
    assert config_mod.DEFAULT_CONFIG == before


def test_env_override_sets_nested_value(monkeypatch, tmp_path):
    monkeypatch.setattr(config_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("STOCK_AI_NOTIFICATION__PUSHPLUS__TOKEN", "env-token")

    cfg = config_mod.load_config()
    assert cfg["notification"]["pushplus"]["token"] == "env-token"


def test_env_override_coerces_bool(monkeypatch, tmp_path):
    monkeypatch.setattr(config_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("STOCK_AI_CACHE__ENABLED", "false")

    cfg = config_mod.load_config()
    assert cfg["cache"]["enabled"] is False


def test_env_override_beats_yaml(monkeypatch, tmp_path):
    (tmp_path / "config.yaml").write_text(
        "ai:\n  llm:\n    api_key: from-yaml\n", encoding="utf-8"
    )
    monkeypatch.setattr(config_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("STOCK_AI_AI__LLM__API_KEY", "from-env")

    cfg = config_mod.load_config()
    assert cfg["ai"]["llm"]["api_key"] == "from-env"


def test_default_llm_model_matches_template():
    assert config_mod.DEFAULT_CONFIG["ai"]["llm"]["model"] == "gpt-4o"


def test_default_backtest_fill_mode_is_next_open():
    """默认必须是无前视偏差的次日开盘成交"""
    assert config_mod.DEFAULT_CONFIG["backtest"]["fill_mode"] == "next_open"

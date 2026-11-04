"""功能开关：订单执行层默认冻结，不应出现在 CLI 顶层"""

import app.config as config_mod


def test_order_group_is_not_exposed_by_default(isolate_config):
    import app.cli as cli

    names = [g.name for g in cli.app.registered_groups]
    assert "order" not in names
    # 代码仍保留，注册表仍完整（只是没挂到顶层）
    assert hasattr(cli.registry, "order_plan")
    assert hasattr(cli.registry, "order_reconcile")


def test_order_flag_defaults_to_false(isolate_config):
    assert isolate_config["features"]["order_enabled"] is False
    assert config_mod.DEFAULT_CONFIG["features"]["order_enabled"] is False


def test_order_can_be_enabled_via_env_override(isolate_config, monkeypatch):
    """环境变量能打开开关（恢复入口不需要改代码）"""
    monkeypatch.setenv("STOCK_AI_FEATURES__ORDER_ENABLED", "true")
    config_mod._apply_env_overrides(isolate_config)

    assert isolate_config["features"]["order_enabled"] is True

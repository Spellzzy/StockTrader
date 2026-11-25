"""命令注册表完整性

cli.py 不再把命令函数挂回自己（原来 import app.cli as _self_module），
改为显式注入 registry。凡是 shortcuts 等模块里写到的 `cli_module.xxx`，
registry 上都必须存在，否则快捷命令会在运行时 AttributeError。

这个测试会在新增命令但忘记注册时直接失败。
"""

import re
from pathlib import Path

# 文档/注释里的占位符，不是真实命令
IGNORED_NAMES = {"xxx"}

APP_DIR = Path(__file__).resolve().parent.parent / "app"


def _referenced_names() -> set:
    names = set()
    for path in APP_DIR.rglob("*.py"):
        names.update(re.findall(r"cli_module\.(\w+)", path.read_text(encoding="utf-8")))
    return names - IGNORED_NAMES


def test_registry_covers_every_referenced_command():
    import app.cli as cli

    missing = sorted(name for name in _referenced_names() if not hasattr(cli.registry, name))
    assert missing == [], f"registry 缺少这些命令: {missing}"


def test_cli_does_not_import_itself():
    """cli.py 不能反向 import 自己"""
    source = (APP_DIR / "cli.py").read_text(encoding="utf-8")
    assert "import app.cli" not in source
    assert "_self_module" not in source


def test_every_registered_command_help_runs(monkeypatch):
    """每个命令的 --help 都要能跑通，拦截导入期 NameError 等低级错误"""
    from typer.testing import CliRunner

    import app.cli as cli
    import app.logging_setup as logging_setup

    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(logging_setup, "setup_logging", lambda *a, **kw: None)

    runner = CliRunner()
    failures = []
    for command in cli.app.registered_commands:
        name = command.name or command.callback.__name__
        result = runner.invoke(cli.app, [name, "--help"])
        if result.exit_code != 0:
            failures.append((name, repr(result.exception)))
    for group in cli.app.registered_groups:
        result = runner.invoke(cli.app, [group.name, "--help"])
        if result.exit_code != 0:
            failures.append((group.name, repr(result.exception)))

    assert failures == [], f"--help 失败: {failures}"

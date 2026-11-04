"""Web 启动命令：端口占用与重复启动处理"""

import pytest
import typer

import app.commands.web as web_mod
from app.config import get_config


@pytest.fixture(autouse=True)
def quiet_config(isolate_config):
    get_config()  # 默认配置，端口 8765


def _run(monkeypatch, *, running, in_use, uvicorn_calls):
    monkeypatch.setattr(web_mod, "_is_our_service", lambda port: running)
    monkeypatch.setattr(web_mod, "_port_in_use", lambda port: in_use)
    monkeypatch.setattr(
        "uvicorn.run", lambda *a, **kw: uvicorn_calls.append((a, kw))
    )
    web_mod.do_web(no_browser=True)


def test_second_launch_reuses_running_service(monkeypatch):
    """双击两次脚本：第二次应提示已在运行并正常退出，而不是绑定报错"""
    uvicorn_calls = []
    _run(monkeypatch, running=True, in_use=True, uvicorn_calls=uvicorn_calls)

    assert uvicorn_calls == []          # 没有再次启动服务


def test_port_taken_by_other_program_fails_cleanly(monkeypatch):
    """端口被无关程序占用：给出清晰提示并以退出码 1 结束"""
    uvicorn_calls = []
    with pytest.raises(typer.Exit) as exc:
        _run(monkeypatch, running=False, in_use=True, uvicorn_calls=uvicorn_calls)

    assert exc.value.exit_code == 1
    assert uvicorn_calls == []


def test_normal_start(monkeypatch):
    uvicorn_calls = []
    _run(monkeypatch, running=False, in_use=False, uvicorn_calls=uvicorn_calls)

    assert len(uvicorn_calls) == 1
    args, kwargs = uvicorn_calls[0]
    assert args[0] == "app.web.api:app"
    assert kwargs["port"] == 8765
    assert kwargs["host"] == "127.0.0.1"

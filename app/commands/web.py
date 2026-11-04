"""Web UI 启动命令 — stock-ai web

双击 启动.bat / start.command 最终调用的就是这里。
"""

from __future__ import annotations

import threading
import time
import webbrowser

import typer
from app.commands import console, Panel, as_bool, as_int


def do_web(host: str = "", port: int = 0, no_browser: bool = False):
    """启动本地 Web 服务（默认 127.0.0.1:8765）"""
    import uvicorn

    from app.config import get_config

    cfg = get_config().get("web", {}) or {}
    host = host or cfg.get("host", "127.0.0.1")
    port = as_int(port, 0) or int(cfg.get("port", 8765))
    open_browser = cfg.get("open_browser", True) and not as_bool(no_browser)

    if host not in ("127.0.0.1", "localhost", "::1"):
        console.print(
            f"[yellow]⚠️ 你指定了 {host}，将监听非本机地址。"
            "本项目无账号体系，请勿在不可信网络中使用。[/yellow]"
        )

    url = f"http://{host if host != '::1' else '[::1]'}:{port}/"
    console.print(Panel(
        f"浏览器打开: [bold]{url}[/bold]\n"
        "[dim]按 Ctrl+C 停止服务；命令行与 TUI 仍可正常使用[/dim]",
        title="🌐 Stock Trader AI Web UI",
        border_style="cyan",
    ))

    if open_browser:
        def _open():
            time.sleep(1.2)
            try:
                webbrowser.open(url)
            except Exception:
                pass

        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run("app.web.api:app", host=host, port=port, log_level="warning")


def register_web_commands(app: typer.Typer):
    """注册 web 命令"""

    @app.command("web", help="启动本地 Web 可视化界面（自动打开浏览器）")
    def web_command(
        host: str = typer.Option("", "--host", help="监听地址，默认 127.0.0.1"),
        port: int = typer.Option(0, "--port", "-p", help="端口，默认 8765"),
        no_browser: bool = typer.Option(False, "--no-browser", help="不自动打开浏览器"),
    ):
        do_web(host=host, port=port, no_browser=no_browser)

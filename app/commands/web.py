"""Web UI 启动命令 — stock-ai web

双击 启动.bat / start.command 最终调用的就是这里。
"""

from __future__ import annotations

import json
import socket
import threading
import time
import webbrowser

import typer
from app.commands import console, Panel, as_bool, as_int


def _is_our_service(port: int) -> bool:
    """端口上是否已经在跑本项目的 Web 服务（避免双击两次脚本报绑定错误）"""
    try:
        import urllib.request

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/health", timeout=1.5
        ) as resp:
            data = json.load(resp)
            return isinstance(data.get("data"), dict) and "version" in data["data"]
    except Exception:
        return False


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def do_web(host: str = "", port: int = 0, no_browser: bool = False):
    """启动本地 Web 服务（默认 127.0.0.1:8765）"""
    import uvicorn

    from app.config import get_config

    cfg = get_config().get("web", {}) or {}
    host = host or cfg.get("host", "127.0.0.1")
    port = as_int(port, 0) or int(cfg.get("port", 8765))
    open_browser = cfg.get("open_browser", True) and not as_bool(no_browser)

    if host in ("127.0.0.1", "localhost") and _is_our_service(port):
        console.print(
            f"[cyan]ℹ️ 服务已在运行：http://127.0.0.1:{port}/[/cyan]\n"
            "[dim]本机同一服务只会启动一份，已为你打开浏览器。"
            "想重启请先关闭旧的窗口。[/dim]"
        )
        if open_browser:
            try:
                webbrowser.open(f"http://127.0.0.1:{port}/")
            except Exception:
                pass
        return

    if _port_in_use(port):
        console.print(
            f"[red]❌ 端口 {port} 已被其他程序占用。[/red]\n"
            f"换个端口启动：[bold]stock-ai web --port {port + 1}[/bold]\n"
            "[dim]或结束占用该端口的进程后重试。[/dim]"
        )
        raise typer.Exit(code=1)

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

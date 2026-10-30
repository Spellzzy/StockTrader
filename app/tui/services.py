"""TUI 服务容器（已提升到 app.container，CLI 与 TUI 共用）

保留本模块是为了兼容 `from app.tui.services import ServiceContainer`。
新代码请使用:

    from app.container import get_container
"""

from app.container import ServiceContainer, get_container, reset_container

__all__ = ["ServiceContainer", "get_container", "reset_container"]

"""全局涨跌颜色主题

根据 config.yaml 中的 color_scheme 配置，统一管理涨跌颜色。
- "red_up"   = 红涨绿跌 (A股惯例)
- "green_up" = 绿涨红跌 (美股/国际惯例)

使用方式:
    from app.theme import UP, DOWN, UP_HEX, DOWN_HEX, UP_BG, DOWN_BG, get_color
"""

from app.config import get_config

# ── Rich markup 颜色名 (用于 CLI 终端) ──

def _scheme() -> str:
    return get_config().get("color_scheme", "red_up")


def _is_red_up() -> bool:
    return _scheme() == "red_up"


# 用函数而非常量，因为配置可能在运行时加载
def get_up() -> str:
    """涨的颜色名 (Rich markup)"""
    return "red" if _is_red_up() else "green"


def get_down() -> str:
    """跌的颜色名 (Rich markup)"""
    return "green" if _is_red_up() else "red"


def get_color(change: float) -> str:
    """根据涨跌值返回颜色名"""
    if change > 0:
        return get_up()
    elif change < 0:
        return get_down()
    return "dim"


# ── Hex 颜色值 (用于 matplotlib 图表) ──

_RED_HEX = "#ff4444"
_GREEN_HEX = "#00c853"


def get_up_hex() -> str:
    """涨的 hex 颜色值 (matplotlib)"""
    return _RED_HEX if _is_red_up() else _GREEN_HEX


def get_down_hex() -> str:
    """跌的 hex 颜色值 (matplotlib)"""
    return _GREEN_HEX if _is_red_up() else _RED_HEX


# ── 背景色 (用于 Rich table row style) ──

_RED_BG = "on #2e1a1a"
_GREEN_BG = "on #1a2e1a"


def get_up_bg() -> str:
    """涨的行背景色"""
    return _RED_BG if _is_red_up() else _GREEN_BG


def get_down_bg() -> str:
    """跌的行背景色"""
    return _GREEN_BG if _is_red_up() else _RED_BG


# ── 便捷常量风格的 API (懒加载) ──
# 在模块被导入后首次访问时求值

class _ColorProxy:
    """延迟求值的颜色代理，避免模块加载顺序问题"""

    @property
    def UP(self) -> str:
        return get_up()

    @property
    def DOWN(self) -> str:
        return get_down()

    @property
    def UP_HEX(self) -> str:
        return get_up_hex()

    @property
    def DOWN_HEX(self) -> str:
        return get_down_hex()

    @property
    def UP_BG(self) -> str:
        return get_up_bg()

    @property
    def DOWN_BG(self) -> str:
        return get_down_bg()


C = _ColorProxy()

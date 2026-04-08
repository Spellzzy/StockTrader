"""TUI Widget 组件层"""

from app.tui.widgets.watchlist import WatchlistSidebar
from app.tui.widgets.quote_panel import QuotePanel
from app.tui.widgets.alert_log import AlertLog
from app.tui.widgets.portfolio import PortfolioTab
from app.tui.widgets.trades import TradesTab
from app.tui.widgets.ai_panel import AIPanel
from app.tui.widgets.status_bar import DashboardStatusBar

__all__ = [
    "WatchlistSidebar",
    "QuotePanel",
    "AlertLog",
    "PortfolioTab",
    "TradesTab",
    "AIPanel",
    "DashboardStatusBar",
]

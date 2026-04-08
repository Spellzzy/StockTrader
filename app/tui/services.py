"""ServiceContainer — TUI 服务容器

职责:
    1. 统一创建、缓存所有业务服务实例（单例模式）
    2. 提供 `run_sync(func, *args)` 在后台线程执行同步 IO，避免阻塞 Textual 事件循环
    3. 管理共享的行情缓存，供多个 widget 复用

设计原则:
    - Widget 不直接 import 业务服务，统一通过 `app.services` 获取
    - 所有对外方法都通过 `run_sync` 返回 awaitable，保持 TUI 响应流畅
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import cached_property
from typing import Any, Callable, Dict, Optional


class ServiceContainer:
    """TUI 业务服务容器

    Usage:
        container = ServiceContainer()
        # 在 async 上下文中
        quotes = await container.run_sync(container.market.get_quote, "sh600519")
    """

    def __init__(self, max_workers: int = 4):
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="tui-svc")
        # 共享行情缓存 {stock_code: {price, change, ...}}
        self._quotes_cache: Dict[str, dict] = {}

    # ==================== 服务实例（惰性单例） ====================

    @cached_property
    def market(self):
        """行情数据服务"""
        from app.services.market_service import MarketService
        return MarketService()

    @cached_property
    def watchlist(self):
        """自选股服务"""
        from app.services.watchlist_service import WatchlistService
        return WatchlistService()

    @cached_property
    def portfolio(self):
        """持仓管理服务"""
        from app.services.portfolio_service import PortfolioService
        return PortfolioService()

    @cached_property
    def trade(self):
        """交易记录服务"""
        from app.services.trade_service import TradeService
        return TradeService()

    @cached_property
    def alert(self):
        """预警监控服务"""
        from app.services.alert_service import AlertService
        return AlertService()

    @cached_property
    def analysis(self):
        """统计分析服务"""
        from app.services.analysis_service import AnalysisService
        return AnalysisService()

    @cached_property
    def notification(self):
        """通知推送管理器"""
        from app.services.notification import NotificationManager
        return NotificationManager()

    # ==================== 行情缓存 ====================

    @property
    def quotes_cache(self) -> Dict[str, dict]:
        """获取共享行情缓存"""
        return self._quotes_cache

    def update_quotes_cache(self, quotes: Dict[str, dict]) -> None:
        """更新行情缓存"""
        self._quotes_cache.update(quotes)

    def clear_quotes_cache(self) -> None:
        """清空行情缓存"""
        self._quotes_cache.clear()

    # ==================== 异步执行器 ====================

    async def run_sync(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """在后台线程池执行同步函数，不阻塞事件循环

        Args:
            func: 同步函数
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            函数返回值
        """
        loop = asyncio.get_running_loop()
        if kwargs:
            # functools.partial 处理关键字参数
            from functools import partial
            func = partial(func, **kwargs)
        return await loop.run_in_executor(self._pool, func, *args)

    # ==================== 生命周期 ====================

    def shutdown(self) -> None:
        """关闭线程池"""
        self._pool.shutdown(wait=False)

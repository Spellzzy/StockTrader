"""自选股/收藏列表服务"""

from typing import List, Optional
from datetime import datetime

from sqlalchemy import select

from app.db.database import get_session
from app.models.stock import Stock


class WatchlistService:
    """自选股管理服务

    基于 Stock 模型的 is_watched 字段来管理收藏列表。
    """

    def __init__(self):
        self.session = get_session()

    # ==================== 添加收藏 ====================

    def add_watch(self, stock_code: str, note: str = "") -> Stock:
        """添加自选股

        Args:
            stock_code: 股票代码 (如 sh600519)
            note: 关注备注/理由

        Returns:
            Stock 对象
        """
        # 检查是否已存在
        stock = self.session.execute(
            select(Stock).where(Stock.code == stock_code)
        ).scalar_one_or_none()

        if stock:
            # 已存在，更新关注状态
            stock.is_watched = True
            if note:
                stock.watch_note = note
            stock.updated_at = datetime.now()
        else:
            # 不存在，先查询名称再创建
            stock_name = ""
            market = Stock.parse_market(stock_code)
            try:
                from app.data.stock_data_client import StockDataClient
                client = StockDataClient()
                quote_data = client.quote(stock_code)
                stock_name = quote_data.get(stock_code, {}).get("name", "")
            except Exception:
                pass

            stock = Stock(
                code=stock_code,
                name=stock_name,
                market=market,
                is_watched=True,
                watch_note=note or None,
            )
            self.session.add(stock)

        self.session.commit()
        self.session.refresh(stock)
        return stock

    # ==================== 删除收藏 ====================

    def remove_watch(self, stock_code: str) -> bool:
        """取消收藏

        Args:
            stock_code: 股票代码

        Returns:
            是否成功取消
        """
        stock = self.session.execute(
            select(Stock).where(Stock.code == stock_code)
        ).scalar_one_or_none()

        if not stock:
            return False

        stock.is_watched = False
        stock.updated_at = datetime.now()
        self.session.commit()
        return True

    # ==================== 查询收藏列表 ====================

    def list_watched(self) -> List[Stock]:
        """获取所有自选股

        Returns:
            自选股列表
        """
        result = self.session.execute(
            select(Stock)
            .where(Stock.is_watched == True)
            .order_by(Stock.updated_at.desc())
        )
        return list(result.scalars().all())

    # ==================== 带行情的收藏列表 ====================

    def list_watched_with_quote(self) -> List[dict]:
        """获取自选股列表及实时行情

        Returns:
            带行情数据的自选股列表
        """
        stocks = self.list_watched()
        if not stocks:
            return []

        # 批量查询行情
        codes = [s.code for s in stocks]
        quotes = {}
        try:
            from app.data.stock_data_client import StockDataClient
            client = StockDataClient()
            quotes = client.quote(*codes)
        except Exception:
            pass

        result = []
        for s in stocks:
            q = quotes.get(s.code, {})
            # 如果名称为空，从行情数据补充
            name = s.name or q.get("name", "")
            if not s.name and name:
                try:
                    s.name = name
                    self.session.commit()
                except Exception:
                    pass

            result.append({
                "code": s.code,
                "name": name,
                "market": s.market,
                "note": s.watch_note or "",
                "price": q.get("price", 0),
                "change": q.get("change", 0),
                "change_percent": q.get("change_percent", 0),
                "open": q.get("open", 0),
                "high": q.get("high", 0),
                "low": q.get("low", 0),
                "volume": q.get("volume", 0),
                "turnover": q.get("turnover", 0),
                "pe_ratio": q.get("pe_ratio", 0),
                "added_at": s.updated_at,
            })

        return result

    # ==================== 更新备注 ====================

    def update_note(self, stock_code: str, note: str) -> bool:
        """更新自选股备注

        Args:
            stock_code: 股票代码
            note: 新备注

        Returns:
            是否成功
        """
        stock = self.session.execute(
            select(Stock).where(Stock.code == stock_code, Stock.is_watched == True)
        ).scalar_one_or_none()

        if not stock:
            return False

        stock.watch_note = note
        stock.updated_at = datetime.now()
        self.session.commit()
        return True

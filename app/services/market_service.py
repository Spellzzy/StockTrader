"""行情数据服务 - 封装 stock-data 为业务友好的接口"""

import pandas as pd
from typing import Optional

from app.data.stock_data_client import StockDataClient


class MarketService:
    """行情数据服务"""

    def __init__(self):
        self.client = StockDataClient()

    def search(self, keyword: str) -> str:
        """搜索股票"""
        return self.client.search(keyword)

    def get_quote(self, *codes: str) -> dict:
        """获取实时行情"""
        return self.client.quote(*codes)

    def get_kline_df(
        self,
        code: str,
        period: str = "day",
        count: int = 60,
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        """获取K线数据并转为 DataFrame

        Args:
            code: 股票代码
            period: K线周期
            count: 数量
            adjust: 复权类型

        Returns:
            包含 date, open, close, high, low, volume, amount, turnover 的 DataFrame
        """
        data = self.client.kline(code, period, count, adjust)

        # 解析 data.nodes 结构
        nodes = []
        if isinstance(data, dict):
            # 尝试不同的数据结构
            if "data" in data and isinstance(data["data"], dict):
                inner = data["data"]
                if "nodes" in inner:
                    nodes = inner["nodes"]
                else:
                    # 可能直接是 {code: {day: [...]}} 的旧结构
                    for key in inner:
                        if isinstance(inner[key], dict):
                            for period_key in inner[key]:
                                if isinstance(inner[key][period_key], list):
                                    nodes = inner[key][period_key]
                                    break
                        elif isinstance(inner[key], list):
                            nodes = inner[key]
                            break
            elif "nodes" in data:
                nodes = data["nodes"]

        if not nodes:
            return pd.DataFrame()

        # 构建 DataFrame
        rows = []
        for node in nodes:
            if isinstance(node, dict):
                rows.append({
                    "date": node.get("date", ""),
                    "open": float(node.get("open", 0)),
                    "close": float(node.get("last", node.get("close", 0))),
                    "high": float(node.get("high", 0)),
                    "low": float(node.get("low", 0)),
                    "volume": float(node.get("volume", 0)),
                    "amount": float(node.get("amount", 0)),
                    "turnover": float(node.get("exchange", 0)),
                })
            elif isinstance(node, list) and len(node) >= 6:
                rows.append({
                    "date": str(node[0]),
                    "open": float(node[1]),
                    "close": float(node[2]),
                    "high": float(node[3]),
                    "low": float(node[4]),
                    "volume": float(node[5]),
                    "amount": float(node[6]) if len(node) > 6 else 0,
                    "turnover": float(node[7]) if len(node) > 7 else 0,
                })

        df = pd.DataFrame(rows)
        if not df.empty and "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").reset_index(drop=True)

        return df

    def get_minute_df(self, code: str) -> pd.DataFrame:
        """获取分时数据转为 DataFrame"""
        data = self.client.minute(code)
        # 根据实际返回结构解析
        return pd.DataFrame(data) if isinstance(data, list) else pd.DataFrame()

    def get_finance(self, code: str, report_type: str = "summary", count: int = 4) -> dict:
        """获取财务数据"""
        return self.client.finance(code, report_type, count)

    def get_profile(self, code: str) -> dict:
        """获取公司简况"""
        return self.client.profile(code)

    def get_fund_flow(self, code: str, days: int = 20) -> dict:
        """获取资金流向（自动判断市场）"""
        if code.startswith("hk"):
            return self.client.hkfund(code, "day", days)
        else:
            return self.client.asfund(code, "historyFundFlow", days)

    def get_news(self, code: str, page: int = 1, size: int = 20) -> dict:
        """获取新闻"""
        return self.client.news(code, page, size, news_type=3)

    def get_rating(self, code: str) -> dict:
        """获取机构评级"""
        return self.client.rating(code)

    def get_chip(self, code: str) -> dict:
        """获取筹码分布"""
        return self.client.chip(code)

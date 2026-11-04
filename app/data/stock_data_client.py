"""stock-data CLI 封装客户端

将 stock-data 命令行工具封装为 Python 可调用的数据服务。
"""

import copy
import json
import subprocess
import logging
import threading
import time
from typing import Optional

from app.config import get_config, get_stock_data_bin

logger = logging.getLogger(__name__)

# quote 每次都要启动一次 stock-data 子进程（实测 1.2~3 秒），
# Web 端总览 / 持仓 / 自选三个页面会重复请求同一批代码。
# 这里做进程内短 TTL 缓存，行情本身非 tick 级，20 秒内复用是安全的。
_QUOTE_CACHE: dict[tuple[str, ...], tuple[float, dict]] = {}
_QUOTE_LOCK = threading.Lock()
_QUOTE_CACHE_MAX = 128
DEFAULT_QUOTE_TTL = 20.0


def quote_cache_ttl() -> float:
    """缓存秒数，可通过 market.quote_cache_seconds 配置，0 表示关闭"""
    try:
        return max(0.0, float(
            (get_config().get("market") or {}).get("quote_cache_seconds", DEFAULT_QUOTE_TTL)
        ))
    except (TypeError, ValueError):
        return DEFAULT_QUOTE_TTL


def clear_quote_cache() -> int:
    """清空行情缓存，返回被清除的条目数（手动刷新时调用）"""
    with _QUOTE_LOCK:
        count = len(_QUOTE_CACHE)
        _QUOTE_CACHE.clear()
    return count


class StockDataError(Exception):
    """stock-data 调用异常"""
    pass


class StockDataClient:
    """stock-data CLI 封装

    将 stock-data 二进制工具封装为 Python 方法调用，
    自动处理 JSON 解析、错误处理和数据格式化。
    """

    def __init__(self, bin_path: Optional[str] = None):
        self.bin_path = bin_path or get_stock_data_bin()

    def _run(self, *args: str) -> str:
        """执行 stock-data 命令并返回原始输出"""
        cmd = [self.bin_path] + list(args)
        logger.debug(f"执行命令: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
            )
            if result.returncode != 0:
                error_msg = result.stderr.strip() or result.stdout.strip()
                raise StockDataError(f"stock-data 命令失败 (code={result.returncode}): {error_msg}")

            return result.stdout.strip()

        except subprocess.TimeoutExpired:
            raise StockDataError("stock-data 命令超时(30s)")
        except FileNotFoundError:
            raise StockDataError(
                f"找不到 stock-data 可执行文件: {self.bin_path}\n"
                f"请确认已正确安装并配置 stock-data 路径。"
            )

    def _run_json(self, *args: str) -> dict:
        """执行命令并解析 JSON 输出"""
        output = self._run(*args)

        # stock-data 输出格式：
        #   [HTTP Request] http://...     <-- 非JSON，需跳过
        #   \n
        #   {                             <-- JSON 开始
        #     "key": "value"
        #   }

        # 策略：找到第一个单独的 { 字符位置（排除 [HTTP 等干扰）
        json_start = -1
        for i, ch in enumerate(output):
            if ch == '{':
                json_start = i
                break
            if ch == '[' and i + 1 < len(output) and output[i + 1] != 'H':
                # 可能是 JSON 数组开头（但不是 [HTTP...）
                json_start = i
                break

        if json_start < 0:
            return {"raw_output": output}

        json_str = output[json_start:]

        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return {"raw_output": output}

    # ==================== 搜索 ====================

    def search(self, keyword: str, search_type: str = "stock") -> str:
        """搜索股票/基金/板块

        Args:
            keyword: 搜索关键词
            search_type: 搜索类型 stock/fund/sector

        Returns:
            原始输出文本
        """
        args = ["search", keyword]
        if search_type != "stock":
            args.append(search_type)
        return self._run(*args)

    # ==================== 行情 ====================

    def quote(self, *codes: str, use_cache: bool = True) -> dict:
        """查询实时行情

        Args:
            codes: 一个或多个股票代码 (如 sh600519, hk00700)
            use_cache: 是否使用短 TTL 缓存（默认 True；需要强制拉新时传 False）

        Returns:
            行情数据字典
        """
        key = tuple(sorted(codes))
        ttl = quote_cache_ttl() if use_cache else 0.0

        if ttl > 0 and key:
            with _QUOTE_LOCK:
                hit = _QUOTE_CACHE.get(key)
                if hit and (time.monotonic() - hit[0]) < ttl:
                    logger.debug(f"行情缓存命中: {key}")
                    return copy.deepcopy(hit[1])
                if len(_QUOTE_CACHE) > _QUOTE_CACHE_MAX:
                    _QUOTE_CACHE.clear()

        data = self._run_json("quote", ",".join(codes))

        if ttl > 0 and key and isinstance(data, dict):
            with _QUOTE_LOCK:
                _QUOTE_CACHE[key] = (time.monotonic(), copy.deepcopy(data))
        return data

    def kline(
        self,
        code: str,
        period: str = "day",
        count: int = 20,
        adjust: str = "",
    ) -> dict:
        """查询K线数据

        Args:
            code: 股票代码
            period: K线周期 day/week/month/season/year/m1/m5/m15/m30/m60/m120
            count: 获取数量 (最大2000)
            adjust: 复权类型 qfq(前复权)/hfq(后复权)/空(不复权)

        Returns:
            K线数据字典
        """
        args = ["kline", code, period, str(count)]
        if adjust:
            args.append(adjust)
        return self._run_json(*args)

    def minute(self, code: str) -> dict:
        """查询分时数据

        Args:
            code: 股票代码

        Returns:
            分时数据字典
        """
        return self._run_json("minute", code)

    # ==================== 财务 ====================

    def finance(
        self,
        code: str,
        report_type: str = "summary",
        count: int = 4,
    ) -> dict:
        """查询财务数据

        Args:
            code: 股票代码
            report_type:
                A股: summary/lrb/zcfz/xjll
                港股: zhsy/zcfz/xjll
                美股: income/balance/cashflow
            count: 获取期数

        Returns:
            财务数据字典
        """
        args = ["finance", code, report_type]
        if report_type != "summary":
            args.append(str(count))
        return self._run_json(*args)

    # ==================== 公司信息 ====================

    def profile(self, code: str) -> dict:
        """查询公司简况

        Args:
            code: 股票代码

        Returns:
            公司信息字典
        """
        return self._run_json("profile", code)

    # ==================== 资金分析 ====================

    def asfund(
        self,
        code: str,
        fund_type: str = "",
        days: int = 20,
    ) -> dict:
        """A股主力资金分析

        Args:
            code: A股代码
            fund_type: 查询类型 historyFundFlow 等
            days: 天数

        Returns:
            资金流向数据
        """
        args = ["asfund", code]
        if fund_type:
            args.extend([fund_type, str(days)])
        return self._run_json(*args)

    def hkfund(
        self,
        code: str,
        period: str = "day",
        count: int = 20,
    ) -> dict:
        """港股资金分析（卖空+港股通）

        Args:
            code: 港股代码
            period: 周期
            count: 数量

        Returns:
            港股资金数据
        """
        return self._run_json("hkfund", code, period, str(count))

    def aspublic(
        self,
        code: str,
        data_types: str = "",
    ) -> dict:
        """A股公开交易数据（融资融券/龙虎榜/大宗交易）

        Args:
            code: A股代码
            data_types: 数据类型 rzrq/lhb/dzjy (逗号分隔)

        Returns:
            公开交易数据
        """
        args = ["aspublic", code]
        if data_types:
            args.append(data_types)
        return self._run_json(*args)

    # ==================== 资讯 ====================

    def news(
        self,
        code: str,
        page: int = 1,
        size: int = 20,
        news_type: int = 3,
    ) -> dict:
        """查询新闻资讯

        Args:
            code: 股票代码
            page: 页码
            size: 每页数量
            news_type: 类型 0=公告 1=研报 2=新闻 3=全部

        Returns:
            新闻列表
        """
        return self._run_json("news", code, str(page), str(size), str(news_type))

    def notice(
        self,
        code: str,
        notice_type: int = 0,
    ) -> dict:
        """查询公告列表

        Args:
            code: 股票代码
            notice_type: 0=全部 1=财报 2=配股 5=重大事项 6=风险提示

        Returns:
            公告列表
        """
        args = ["notice", code]
        if notice_type > 0:
            args.append(str(notice_type))
        return self._run_json(*args)

    def rating(self, code: str) -> dict:
        """查询机构评级（仅A股）

        Args:
            code: A股代码

        Returns:
            评级数据
        """
        return self._run_json("rating", code)

    def report(
        self,
        code: str,
        page: int = 1,
        size: int = 20,
    ) -> dict:
        """查询研报列表

        Args:
            code: 股票代码
            page: 页码
            size: 每页条数

        Returns:
            研报列表
        """
        return self._run_json("report", code, str(page), str(size))

    # ==================== 筹码分布 ====================

    def chip(
        self,
        code: str,
        date: str = "",
        price: Optional[float] = None,
        period: str = "day",
    ) -> dict:
        """查询筹码分布

        Args:
            code: 股票代码
            date: 指定日期 (YYYY-MM-DD)
            price: 指定价格（查获利比例）
            period: K线周期

        Returns:
            筹码分布数据
        """
        args = ["chip", code]
        if date:
            args.append(date)
        if price is not None:
            args.extend(["--price", str(price)])
        if period != "day":
            args.extend(["--period", period])
        return self._run_json(*args)

"""股票信息模型"""

import re
from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def normalize_stock_code(code: str) -> str:
    """智能补全股票代码前缀

    支持用户只输入数字代码，自动根据规则推断市场前缀:
        - 已有 sh/sz/hk/us 前缀 → 原样返回(小写)
        - 6 位纯数字:
            6xxxxx → sh (上海: 主板/科创板60xxxx, 688xxx)
            0xxxxx → sz (深圳: 主板)
            3xxxxx → sz (深圳: 创业板)
            8xxxxx → bj 或 sz (北交所/新三板; 暂归 sz 处理)
            4xxxxx → sz (新三板老股转; 暂归 sz)
            5xxxxx → sh (上海基金/ETF)
            1xxxxx → sz (深圳基金/ETF/可转债)
            2xxxxx → sz (深圳B股)
            9xxxxx → sh (上海B股)
        - 5 位纯数字 → hk (港股)
        - 纯字母 → us (美股)
        - 其它 → 原样返回

    Args:
        code: 用户输入的股票代码（可以是 '600519', 'sh600519', '00700' 等）

    Returns:
        带有市场前缀的标准代码 (如 'sh600519', 'sz000001', 'hk00700')
    """
    code = code.strip().lower()

    # 已有前缀，直接返回
    if re.match(r'^(sh|sz|hk|us|bj)', code):
        return code

    # 纯数字
    if code.isdigit():
        if len(code) == 6:
            first = code[0]
            if first == '6' or first == '5' or first == '9':
                return f"sh{code}"
            else:
                # 0/1/2/3/4/8 开头都归深圳
                return f"sz{code}"
        elif len(code) == 5:
            # 5 位数字 → 港股
            return f"hk{code}"
        else:
            # 其它长度数字, 尝试补零到 6 位再推断
            if len(code) < 6:
                padded = code.zfill(6)
                return normalize_stock_code(padded)
            return code

    # 纯字母 → 美股 (如 AAPL, TSLA)
    if code.isalpha():
        return f"us{code.upper()}"

    # 其它混合格式, 原样返回
    return code


def normalize_stock_codes(codes_str: str) -> str:
    """批量标准化逗号分隔的股票代码

    Args:
        codes_str: 逗号分隔的代码串 (如 '600519,000001,00700')

    Returns:
        标准化后的逗号分隔代码串 (如 'sh600519,sz000001,hk00700')
    """
    parts = [c.strip() for c in codes_str.split(",") if c.strip()]
    return ",".join(normalize_stock_code(c) for c in parts)


class Stock(Base):
    """股票基本信息表（本地缓存）"""
    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 基本信息
    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True, comment="股票代码(含前缀)")
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="股票名称")
    market: Mapped[str] = mapped_column(String(10), nullable=False, comment="市场: A/HK/US")
    market_name: Mapped[str] = mapped_column(String(50), nullable=True, comment="板块名(上海主板/深圳创业板等)")

    # 行业信息
    industry: Mapped[str] = mapped_column(String(50), nullable=True, comment="所属行业")
    sector: Mapped[str] = mapped_column(String(50), nullable=True, comment="所属板块")

    # 关注/标记
    is_watched: Mapped[bool] = mapped_column(default=False, comment="是否在自选列表")
    watch_note: Mapped[str] = mapped_column(Text, nullable=True, comment="自选备注")

    # 元数据
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self) -> str:
        return f"<Stock(code={self.code}, name={self.name}, market={self.market})>"

    @staticmethod
    def parse_market(code: str) -> str:
        """根据代码前缀判断市场类型"""
        normalized = normalize_stock_code(code)
        if normalized.startswith("sh") or normalized.startswith("sz"):
            return "A"
        elif normalized.startswith("hk"):
            return "HK"
        elif normalized.startswith("us"):
            return "US"
        else:
            return "A"

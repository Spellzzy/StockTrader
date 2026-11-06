"""领域层

放置不依赖 CLI/TUI、也不依赖行情与数据库的纯业务规则：
- 费率计算（fees）
- 技术指标（indicators）
- 交易日历（calendar）
- 日报落盘文件名与正文（report_persist；HTML 报告在调用时才加载）

依赖方向：services / ai → domain，domain 不反向依赖 services / ai / data / commands。
report_persist 只在写出 HTML 时才加载 visualization。
"""

from app.domain.calendar import TradingCalendar, get_calendar
from app.domain.fees import FeeModel
from app.domain.indicators import FeatureEngine

__all__ = ["FeeModel", "FeatureEngine", "TradingCalendar", "get_calendar"]

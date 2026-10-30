"""领域层

放置不依赖 CLI/TUI、也不依赖行情与数据库的纯业务规则：
- 费率计算（fees）
- 技术指标（indicators，P2 从 ai/feature_engine 下沉）
- 交易日历（calendar，P2/P3）

依赖方向：services / ai → domain，domain 不反向依赖上层。
"""

from app.domain.fees import FeeModel

__all__ = ["FeeModel"]

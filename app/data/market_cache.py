"""K 线缓存

每次拉 K 线都要新起一个 stock-data 子进程，全 A 扫描时调用量是 O(股票数 × 命令数)。
这里把 K 线按 (code, period, adjust) 缓存到本地，命中就直接用：

- 最后一根 K 线是今天 → 数据还会变，按 cache.expire_minutes 过期（盘中建议设短）
- 最后一根 K 线是历史日期 → 历史日线不会再变，按 24 小时过期
"""

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

CACHE_SUFFIX = ".joblib"
# 历史日线不会再变动，缓存有效期放宽到 1 天
STALE_HISTORICAL_MINUTES = 24 * 60


class KlineCache:
    """K 线本地缓存"""

    def __init__(
        self,
        enabled: bool = True,
        cache_dir: str = "./data/cache",
        expire_minutes: int = 30,
    ):
        self.enabled = enabled
        self.cache_dir = Path(cache_dir)
        self.expire_minutes = expire_minutes
        self.kline_dir = self.cache_dir / "kline"

    @classmethod
    def from_config(cls, cfg: Optional[dict] = None) -> "KlineCache":
        """从配置构造（cache 段）"""
        if cfg is None:
            from app.config import get_config

            cfg = get_config()
        cache_cfg = (cfg or {}).get("cache", {}) or {}
        return cls(
            enabled=bool(cache_cfg.get("enabled", True)),
            cache_dir=cache_cfg.get("dir", "./data/cache"),
            expire_minutes=int(cache_cfg.get("expire_minutes", 30)),
        )

    # ==================== 读写 ====================

    def _path(self, code: str, period: str, adjust: str) -> Path:
        return self.kline_dir / f"{code}_{period}_{adjust}{CACHE_SUFFIX}"

    def _expire_limit(self, df: pd.DataFrame, now: datetime) -> float:
        """当前行情按 expire_minutes 过期，历史行情放宽到 24 小时

        注意不能直接拿 calendar.date() 比：周末/节假日运行时，最后一根 K 线本来就是
        上一个交易日，会被误判成历史数据从而永不过期。
        """
        last_date = None
        if "date" in df.columns and not df.empty:
            try:
                last_date = pd.to_datetime(df["date"].max()).date()
            except (TypeError, ValueError):
                last_date = None

        if last_date is None:
            return float(self.expire_minutes)

        from app.domain.calendar import get_calendar

        latest_trading_day = get_calendar().previous_trading_day(now)
        if last_date >= latest_trading_day:
            return float(self.expire_minutes)
        return STALE_HISTORICAL_MINUTES

    def get(
        self,
        code: str,
        period: str = "day",
        adjust: str = "qfq",
        now: Optional[datetime] = None,
    ) -> Optional[pd.DataFrame]:
        """读取缓存，未命中或已过期返回 None"""
        if not self.enabled:
            return None

        path = self._path(code, period, adjust)
        if not path.exists():
            return None

        current = now or datetime.now()
        age_minutes = (current.timestamp() - path.stat().st_mtime) / 60.0

        try:
            import joblib

            df = joblib.load(path)
        except Exception as e:
            logger.warning(f"K线缓存读取失败，将重新拉取: {path.name} ({e})")
            return None

        if not isinstance(df, pd.DataFrame) or df.empty:
            return None

        if age_minutes > self._expire_limit(df, current):
            return None

        logger.debug(f"K线缓存命中: {path.name} (年龄 {age_minutes:.1f} 分钟)")
        return df

    def put(self, df: pd.DataFrame, code: str, period: str = "day", adjust: str = "qfq") -> Optional[Path]:
        """写入缓存"""
        if not self.enabled or df is None or df.empty:
            return None

        try:
            import joblib

            self.kline_dir.mkdir(parents=True, exist_ok=True)
            path = self._path(code, period, adjust)
            joblib.dump(df, path)
            return path
        except Exception as e:
            logger.warning(f"K线缓存写入失败: {e}")
            return None

    def clear(self, code: Optional[str] = None) -> int:
        """清理缓存（不指定代码则清空全部），返回删除数量"""
        if not self.kline_dir.exists():
            return 0

        pattern = f"{code}_*{CACHE_SUFFIX}" if code else f"*{CACHE_SUFFIX}"
        removed = 0
        for path in self.kline_dir.glob(pattern):
            path.unlink(missing_ok=True)
            removed += 1
        return removed

    def invalidate(self, code: str, period: str = "day", adjust: str = "qfq") -> bool:
        """让指定 K 线缓存失效"""
        path = self._path(code, period, adjust)
        if not path.exists():
            return False
        path.unlink(missing_ok=True)
        return True

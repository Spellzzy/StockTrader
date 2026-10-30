"""K 线缓存"""

import os
import time
from datetime import date

import pandas as pd

from app.data.market_cache import KlineCache


def _df(start="2024-01-01", n=5) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.bdate_range(start=start, periods=n),
            "close": [10.0 + i for i in range(n)],
        }
    )


def test_put_then_get_returns_same_data(tmp_path):
    cache = KlineCache(enabled=True, cache_dir=str(tmp_path), expire_minutes=30)
    df = _df()

    cache.put(df, "sh600519")
    loaded = cache.get("sh600519")

    assert loaded is not None
    pd.testing.assert_frame_equal(loaded, df)


def test_cache_is_disabled_by_config(tmp_path):
    cache = KlineCache(enabled=False, cache_dir=str(tmp_path))
    cache.put(_df(), "sh600519")

    assert cache.get("sh600519") is None


def test_expired_cache_misses(tmp_path):
    """当日数据在盘中会变化，超过 expire_minutes 即失效"""
    cache = KlineCache(enabled=True, cache_dir=str(tmp_path), expire_minutes=30)
    today = pd.bdate_range(end=date.today(), periods=5)
    cache.put(pd.DataFrame({"date": today, "close": [10.0] * 5}), "sh600519")

    # 把文件 mtime 推到 2 小时前
    path = cache._path("sh600519", "day", "qfq")
    old = time.time() - 7200
    os.utime(path, (old, old))

    assert cache.get("sh600519") is None


def test_historical_data_uses_longer_ttl(tmp_path):
    """最后一根 K 线是历史日期时，缓存有效期放宽到 24 小时"""
    cache = KlineCache(enabled=True, cache_dir=str(tmp_path), expire_minutes=30)
    cache.put(_df(start="2024-01-01"), "sh600519")

    path = cache._path("sh600519", "day", "qfq")
    old = time.time() - 3600  # 1 小时前
    os.utime(path, (old, old))

    assert cache.get("sh600519") is not None


def test_cache_key_includes_period_and_adjust(tmp_path):
    cache = KlineCache(enabled=True, cache_dir=str(tmp_path))
    cache.put(_df(), "sh600519", period="day", adjust="qfq")

    assert cache.get("sh600519", period="day", adjust="qfq") is not None
    assert cache.get("sh600519", period="week", adjust="qfq") is None
    assert cache.get("sh600519", period="day", adjust="") is None


def test_clear_removes_files(tmp_path):
    cache = KlineCache(enabled=True, cache_dir=str(tmp_path))
    cache.put(_df(), "sh600519")
    cache.put(_df(), "sz000001")

    assert cache.clear("sh600519") == 1
    assert cache.clear() == 1
    assert cache.clear() == 0


def test_invalidate(tmp_path):
    cache = KlineCache(enabled=True, cache_dir=str(tmp_path))
    cache.put(_df(), "sh600519")

    assert cache.invalidate("sh600519") is True
    assert cache.invalidate("sh600519") is False


def test_from_config_reads_cache_section():
    cache = KlineCache.from_config(
        {"cache": {"enabled": False, "dir": "/tmp/x", "expire_minutes": 5}}
    )
    assert cache.enabled is False
    assert cache.expire_minutes == 5

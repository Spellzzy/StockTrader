"""pytest 公共夹具

设计约束（保证 CI 可离线运行）：
1. 不调用 stock-data 子进程、不访问 LLM、不推送 —— 相关调用一律打桩；
2. 不读写用户真实数据库 —— 需要 DB 的用例使用内存 SQLite；
3. 不依赖用户 config.yaml —— 每个用例前把配置单例重置为默认值深拷贝。
"""

import copy
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.config as config_mod
from app.models.base import Base

# 确保所有 ORM 模型注册到 Base.metadata
import app.models  # noqa: F401

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def isolate_config():
    """隔离配置，避免用例读写用户 config.yaml 或污染 DEFAULT_CONFIG"""
    snapshot = copy.deepcopy(config_mod.DEFAULT_CONFIG)
    config_mod._config = copy.deepcopy(config_mod.DEFAULT_CONFIG)
    yield config_mod._config
    config_mod._config = None
    config_mod.DEFAULT_CONFIG.clear()
    config_mod.DEFAULT_CONFIG.update(snapshot)


@pytest.fixture
def db_session():
    """内存 SQLite 会话（每个用例独立建表/销毁）"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def make_kline_df(n: int = 200, seed: int = 42, start: str = "2024-01-01") -> pd.DataFrame:
    """生成确定性的日 K 样本（随机游走，保证 OHLC 自洽）"""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start=start, periods=n)

    close = 10.0 + np.cumsum(rng.normal(0, 0.15, n))
    close = np.maximum(close, 1.0)
    open_ = close + rng.normal(0, 0.05, n)
    high = np.maximum(open_, close) + rng.uniform(0.02, 0.20, n)
    low = np.minimum(open_, close) - rng.uniform(0.02, 0.20, n)
    volume = rng.integers(100_000, 1_000_000, n).astype(float)

    return pd.DataFrame(
        {
            "date": list(dates),
            "open": open_,
            "close": close,
            "high": high,
            "low": low,
            "volume": volume,
            "amount": volume * close,
        }
    )


@pytest.fixture
def kline_df() -> pd.DataFrame:
    return make_kline_df()


@pytest.fixture
def limit_kline_df() -> pd.DataFrame:
    """含一字涨停/一字跌停的 K 线样本（用于撮合规则测试）"""
    df = pd.read_csv(FIXTURES_DIR / "kline_limit.csv", encoding="utf-8")
    df["date"] = pd.to_datetime(df["date"])
    return df

"""股票池加载器 — 提供"全A股"等大池的代码列表

策略
----
A股代码段穷举 + 批量 quote 探活 + 本地缓存。

A股代码区间：
- 沪市主板: 600000~605999
- 沪市科创板: 688000~688999
- 深市主板/中小板: 000001~003999
- 深市创业板: 300001~301999

缓存文件: data/cache/all_a_codes.json
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from app.config import get_config
from app.data.stock_data_client import StockDataClient


# 默认缓存路径
def _cache_path() -> Path:
    cache_dir = Path(get_config()["cache"]["dir"])
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "all_a_codes.json"


# ============================================================================
# 代码段定义
# ============================================================================

A_SHARE_RANGES = [
    # (前缀, 起始, 结束)
    ("sh", 600000, 605999),  # 沪市主板
    ("sh", 688000, 688999),  # 沪市科创板
    ("sz", 0,      4999),    # 深市主板/中小板 (000001~003999, 含 sz0xxxxx)
    ("sz", 300001, 301999),  # 深市创业板
]


def _generate_candidates() -> list[str]:
    """穷举所有候选代码"""
    out = []
    for prefix, start, end in A_SHARE_RANGES:
        for n in range(start, end + 1):
            out.append(f"{prefix}{n:06d}")
    return out


# ============================================================================
# 缓存读写
# ============================================================================


def load_cache(max_age_days: int = 7) -> Optional[list[dict]]:
    """读取缓存。若缓存过期返回 None"""
    p = _cache_path()
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        ts = data.get("updated_at", 0)
        age = (datetime.now() - datetime.fromtimestamp(ts)).days
        if age > max_age_days:
            return None
        return data.get("codes", [])
    except Exception:
        return None


def save_cache(codes: list[dict]) -> Path:
    """保存缓存"""
    p = _cache_path()
    payload = {
        "updated_at": int(time.time()),
        "updated_str": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(codes),
        "codes": codes,
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


# ============================================================================
# 探活构建
# ============================================================================


def build_all_a_codes(
    batch_size: int = 50,
    progress_cb: Optional[Callable[[int, int, int], None]] = None,
    exclude_delisted: bool = True,
    exclude_st: bool = False,
) -> list[dict]:
    """探活构建全A代码列表

    探活规则（满足任一即视为已退市/停牌，剔除）：
        - name 含 "退" / "PT" / "暂停" / "退市"
        - exclude_delisted=True 时:
            open==0 且 volume==0 且 当前为交易日（说明全天无交易）
        - exclude_st=True 时还会剔除 name 含 "ST"

    Args:
        batch_size: 每批 quote 的数量
        progress_cb: 进度回调 fn(已处理, 总数, 已发现)
        exclude_delisted: 是否过滤已退市/长期停牌股
        exclude_st: 是否过滤 ST 股（默认 False）

    Returns:
        [{"code": "sh600000", "name": "浦发银行"}, ...]
    """
    client = StockDataClient()
    candidates = _generate_candidates()
    total = len(candidates)
    found: list[dict] = []

    # 退市/异常名称黑名单关键字
    DELISTED_KEYWORDS = ("退", "PT", "暂停", "退市")

    for i in range(0, total, batch_size):
        batch = candidates[i:i + batch_size]
        try:
            data = client.quote(*batch)
        except Exception:
            data = {}

        if isinstance(data, dict):
            for code in batch:
                q = data.get(code)
                if not isinstance(q, dict):
                    continue
                name = q.get("name", "") or ""
                prev = q.get("prev_close") or 0
                if not name or prev <= 0:
                    continue

                # 过滤名称含退市关键字的股票
                if exclude_delisted and any(k in name for k in DELISTED_KEYWORDS):
                    continue

                # 过滤 ST 股（可选）
                if exclude_st and ("ST" in name or "*ST" in name):
                    continue

                # 过滤"长期 0 成交 + 价格==前收"特征股（典型退市/长期停牌）
                if exclude_delisted:
                    open_p = q.get("open", 0) or 0
                    vol = q.get("volume", 0) or 0
                    price = q.get("price", 0) or 0
                    if open_p == 0 and vol == 0 and price == prev:
                        continue

                found.append({"code": code, "name": name})

        if progress_cb:
            progress_cb(min(i + batch_size, total), total, len(found))

    return found


def get_all_a_codes(
    refresh: bool = False,
    max_age_days: int = 7,
    progress_cb: Optional[Callable[[int, int, int], None]] = None,
    exclude_delisted: bool = True,
    exclude_st: bool = False,
) -> list[str]:
    """获取全A代码列表（带缓存）

    Returns:
        ["sh600000", "sh600001", ...]
    """
    if not refresh:
        cached = load_cache(max_age_days=max_age_days)
        if cached:
            return [c["code"] for c in cached]

    codes = build_all_a_codes(
        progress_cb=progress_cb,
        exclude_delisted=exclude_delisted,
        exclude_st=exclude_st,
    )
    save_cache(codes)
    return [c["code"] for c in codes]


def get_all_a_name_map(max_age_days: int = 7) -> dict[str, str]:
    """从缓存读取 {code: name} 映射，供 screener 大池场景填充名称"""
    cached = load_cache(max_age_days=max_age_days)
    if not cached:
        return {}
    return {c["code"]: c["name"] for c in cached}


def get_cache_info() -> Optional[dict]:
    """返回缓存元信息（用于展示）"""
    p = _cache_path()
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return {
            "path": str(p),
            "count": data.get("count", 0),
            "updated": data.get("updated_str", ""),
        }
    except Exception:
        return None

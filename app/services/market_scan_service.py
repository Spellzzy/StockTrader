"""全市场摘选服务

复用已有能力，不重写因子逻辑：
    pool_loader.get_all_a_codes()  → 全 A 代码池（7 天缓存）
    批量 quote                     → 廉价预筛（把 5000 只降到几百只）
    ScreenerService.screen()       → 条件评估（14 个可插拔条件、并发）
    ScreenRun                      → 结果落库，日报/定时脚本直接复用

关键约束：每只股票的条件评估要拉一次 K 线子进程，全 A 直接跑要 20~40 分钟，
所以必须先做只依赖批量 quote 的预筛。
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime
from typing import Callable, Optional

from sqlalchemy import select

from app.config import get_config
from app.data.stock_data_client import StockDataClient
from app.db.database import session_scope
from app.models.screen_run import ScreenRun
from app.services.screener_service import ScreenerService

logger = logging.getLogger(__name__)


class ScanCancelled(Exception):
    """用户主动取消了本次扫描"""

# market_scan 中需要透传给 ScreenerService 的键
_SCREENER_KEYS = (
    "min_kline", "kline_count", "max_workers", "max_kline_age_days",
    "benchmark", "all_a_cache_days", "pool_size_limit",
    "exclude_delisted", "exclude_st",
)
# 参与参数哈希、决定结果是否需要重算的键
_HASH_KEYS = (
    "pool", "batch_size", "candidate_limit", "min_amount_wan",
    "min_price", "max_price", "max_change_pct", "exclude_st",
    "exclude_delisted", "top_n", "side", "max_workers", "kline_count",
    "mode", "rules", "inherit_screener",
)

# 全市场摘选的默认规则：与「自选股选股」场景不同，大池需要宽进严出。
# 原 screener.buy 是 mode=all 且含 sector_strong（需基准）+ 量比 1.5，
# 四条全满足在大盘里几乎必然 0 命中。
DEFAULT_SCAN_MODE = "atleast:2"
DEFAULT_SCAN_RULES = [
    {"name": "ma_uptrend", "params": {"ma": 20, "lookback": 5}},
    {"name": "price_above_ma", "params": {"ma": 20}},
    {"name": "ma_bull", "params": {}},
    {"name": "macd_golden", "params": {"lookback": 3}},
    {"name": "volume_expand", "params": {"ma_window": 5, "ratio": 1.2}},
]


def build_report(result: dict) -> str:
    """把扫描结果渲染成 Markdown 报告（CLI 与定时脚本共用）"""
    hits = result.get("hits") or []
    lines = [
        f"# 全市场摘选 · {result.get('generated_at', '')}",
        "",
        f"- 股票池：`{result.get('pool', '-')}`（{result.get('universe_count', 0)} 只）",
        f"- 预筛候选：**{result.get('candidate_count', 0)} 只**"
        "（成交额 / 价格 / ST / 涨跌停硬过滤）",
        f"- 条件命中：**{result.get('hit_count', 0)} 只**，下方展示 Top {len(hits)}",
        f"- 耗时：{result.get('duration_seconds', 0)} 秒",
        "",
        "## 命中清单",
        "",
    ]
    if not hits:
        lines.append("本次没有股票满足当前条件组合。")
    else:
        lines.append("| # | 代码 | 名称 | 现价 | 命中条件数 | 命中理由 |")
        lines.append("|---|------|------|------|-----------|----------|")
        for i, h in enumerate(hits, 1):
            reasons = "、".join(str(r[0]) for r in (h.get("matched") or [])[:4])
            lines.append(
                f"| {i} | `{h['code']}` | {h.get('name', '')} | {h.get('price', '-')} | "
                f"{h.get('matched_count', 0)}/{h.get('total_rules', 0)} | {reasons} |"
            )
    lines += [
        "",
        "---",
        "*摘选结果仅为技术面信号，不构成投资建议。条件与阈值见 config.yaml 的 "
        "`screener` / `market_scan` 段。*",
    ]
    return "\n".join(lines)


class MarketScanService:
    """全市场摘选：预筛 → 条件筛选 → 打分 → 落库"""

    def __init__(self, config: Optional[dict] = None, scope=None):
        self.cfg = dict(config or get_config().get("market_scan", {}) or {})
        self._scope = scope
        self.client = StockDataClient()

        screener_cfg = dict(get_config().get("screener", {}) or {})
        for key in _SCREENER_KEYS:
            if key in self.cfg:
                screener_cfg[key] = self.cfg[key]

        # 摘选规则独立于 stock-ai sn：优先用 market_scan.rules，
        # 否则用内置的宽松默认；inherit_screener=true 可显式沿用原规则。
        if not self.cfg.get("inherit_screener", False):
            side = self.cfg.get("side", "buy")
            block = dict(screener_cfg.get(side) or {})
            block["rules"] = self.cfg.get("rules") or DEFAULT_SCAN_RULES
            block["mode"] = self.cfg.get("mode") or DEFAULT_SCAN_MODE
            screener_cfg[side] = block

        self.screener = ScreenerService(screener_config=screener_cfg)
        self._screener_cfg = screener_cfg

    @property
    def scope(self):
        return self._scope or session_scope

    def params_hash(self, pool: Optional[str] = None, side: Optional[str] = None) -> str:
        scan_params = {k: self.cfg.get(k) for k in _HASH_KEYS}
        # 命令行覆盖的池/方向必须参与哈希，否则先跑 watchlist 再跑 all_a 会误复用
        scan_params["pool"] = pool or self.cfg.get("pool", "all_a")
        scan_params["side"] = side or self.cfg.get("side", "buy")
        payload = {
            "scan": scan_params,
            "rules": {
                side: (self._screener_cfg.get(side) or {}).get("rules", [])
                for side in ("buy", "sell")
            },
        }
        body = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]

    # ==================== 预筛 ====================

    def _passes(self, quote: dict) -> bool:
        name = str(quote.get("name") or "").strip()
        if not name:
            return False
        if self.cfg.get("exclude_delisted", True) and any(
            k in name for k in ("退", "PT", "暂停", "退市")
        ):
            return False
        if self.cfg.get("exclude_st", True) and "ST" in name.upper():
            return False

        price = float(quote.get("price") or 0)
        min_price = float(self.cfg.get("min_price", 2.0))
        max_price = float(self.cfg.get("max_price", 500.0))
        if not (min_price <= price <= max_price):
            return False

        amount = float(quote.get("amount") or 0)  # 单位：万元
        if amount < float(self.cfg.get("min_amount_wan", 3000)):
            return False

        if not float(quote.get("volume") or 0):   # 停牌 / 无成交
            return False

        max_change = float(self.cfg.get("max_change_pct", 9.8) or 0)
        if max_change > 0:
            change = float(quote.get("change_percent") or 0)
            if abs(change) > max_change:
                return False
        return True

    def prefilter(
        self,
        codes: list[str],
        progress_cb: Optional[Callable[[int, int, int], None]] = None,
        cancel_event=None,
    ) -> tuple[list[str], dict]:
        """批量 quote 预筛，返回 (候选代码, 统计)"""
        batch_size = max(1, int(self.cfg.get("batch_size", 50)))
        rows: list[dict] = []

        for i in range(0, len(codes), batch_size):
            if cancel_event is not None and cancel_event.is_set():
                raise ScanCancelled("预筛阶段被取消")
            batch = codes[i:i + batch_size]
            try:
                data = self.client.quote(*batch) or {}
            except Exception as e:
                logger.warning(f"预筛行情批次失败 {i}: {e}")
                data = {}
            for code in batch:
                q = data.get(code)
                if isinstance(q, dict) and self._passes(q):
                    rows.append({
                        "code": code,
                        "name": str(q.get("name") or ""),
                        "amount": float(q.get("amount") or 0),
                        "price": float(q.get("price") or 0),
                        "change_percent": float(q.get("change_percent") or 0),
                    })
            if progress_cb:
                progress_cb(min(i + batch_size, len(codes)), len(codes), len(rows))

        rows.sort(key=lambda r: r["amount"], reverse=True)
        limit = int(self.cfg.get("candidate_limit", 600) or 0)
        candidates = rows[:limit] if limit > 0 else rows
        return [r["code"] for r in candidates], {
            "universe": len(codes),
            "quoted_pass": len(rows),
            "candidates": len(candidates),
        }

    # ==================== 落库与读取 ====================

    def _today(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def _find_today(self, params_hash: str) -> Optional[dict]:
        with self.scope() as s:
            run = s.execute(
                select(ScreenRun).where(
                    ScreenRun.run_date == self._today(),
                    ScreenRun.params_hash == params_hash,
                )
            ).scalar_one_or_none()
            if not run:
                return None
            return self._to_dict(run)

    def _save(self, result: dict) -> None:
        record = ScreenRun(
            run_date=result["run_date"],
            pool=result["pool"],
            params_hash=result["params_hash"],
            universe_count=result["universe_count"],
            candidate_count=result["candidate_count"],
            scanned_count=result["scanned_count"],
            hit_count=result["hit_count"],
            duration_seconds=result["duration_seconds"],
            top_n=result["top_n"],
            result_json=json.dumps(result, ensure_ascii=False, default=str),
        )
        try:
            with self.scope() as s:
                s.add(record)
        except Exception as e:
            # 并发/重复运行时 unique 约束会拦下，已有结果即可用
            logger.info(f"扫描结果已存在或落库失败（不阻断流程）: {e}")

    @staticmethod
    def _to_dict(run: ScreenRun) -> dict:
        try:
            data = json.loads(run.result_json or "{}")
        except Exception:
            data = {}
        data.update({"id": run.id, "created_at": run.created_at})
        return data

    def latest(self) -> Optional[dict]:
        """最近一次扫描结果（日报/定时脚本直接读，不重跑）"""
        with self.scope() as s:
            run = s.execute(
                select(ScreenRun).order_by(ScreenRun.id.desc()).limit(1)
            ).scalar_one_or_none()
            if not run:
                return None
            return self._to_dict(run)

    def list_runs(self, limit: int = 10) -> list[dict]:
        with self.scope() as s:
            runs = s.execute(
                select(ScreenRun).order_by(ScreenRun.id.desc()).limit(limit)
            ).scalars().all()
            return [{
                "id": r.id, "run_date": r.run_date, "pool": r.pool,
                "candidate_count": r.candidate_count, "hit_count": r.hit_count,
                "duration_seconds": r.duration_seconds, "created_at": r.created_at,
            } for r in runs]

    def get_run(self, run_id: int) -> Optional[dict]:
        """按 ID 读取某次扫描的完整结果（Web 历史回看）"""
        with self.scope() as s:
            run = s.get(ScreenRun, run_id)
            return self._to_dict(run) if run else None

    # ==================== 主流程 ====================

    def run(
        self,
        pool: Optional[str] = None,
        side: Optional[str] = None,
        force: bool = False,
        save: bool = True,
        prefilter_cb: Optional[Callable[[int, int, int], None]] = None,
        screen_cb: Optional[Callable[[int, int, int], None]] = None,
        cancel_event=None,
    ) -> dict:
        """跑一次全市场摘选

        Args:
            pool: 覆盖股票池（all_a / watchlist / portfolio / file:... / 代码列表）
            side: buy / sell，默认取配置
            force: 忽略「今天同参数已跑过」的缓存
            save: 是否落库
            cancel_event: threading.Event，置位后在批次边界中止并抛 ScanCancelled
        """
        started = time.perf_counter()
        pool = pool or self.cfg.get("pool", "all_a")
        side = side or self.cfg.get("side", "buy")
        params_hash = self.params_hash(pool, side)

        if save and not force:
            cached = self._find_today(params_hash)
            if cached:
                logger.info(f"今日同参数已扫描过，直接复用 run #{cached.get('id')}")
                return {**cached, "cached": True}

        universe = self.screener.resolve_pool(pool)
        logger.info(f"股票池 {pool}: {len(universe)} 只")
        candidates, stats = self.prefilter(
            universe, progress_cb=prefilter_cb, cancel_event=cancel_event
        )
        logger.info(f"预筛后候选: {stats['candidates']} 只")

        if cancel_event is None:
            hits = self.screener.screen(candidates, side=side, progress_cb=screen_cb)
        else:
            # 分批提交，取消时最多等当前这一批（否则 ThreadPoolExecutor 会等全部 futures）
            chunk = max(1, int(self.cfg.get("cancel_chunk", 50)))
            hits = []
            for start in range(0, len(candidates), chunk):
                if cancel_event.is_set():
                    raise ScanCancelled("条件评估阶段被取消")
                part_codes = candidates[start:start + chunk]

                def _part_cb(done, total, found, _start=start):
                    if cancel_event.is_set():
                        raise ScanCancelled("条件评估阶段被取消")
                    if screen_cb:
                        screen_cb(_start + done, len(candidates), len(hits) + found)

                hits.extend(self.screener.screen(
                    part_codes, side=side, progress_cb=_part_cb
                ))
        # 命中条件数越多越靠前，同分按代码稳定排序
        hits.sort(key=lambda h: (-len(h.matched), h.code))
        top_n = int(self.cfg.get("top_n", 20))
        picked = [{
            "code": h.code,
            "name": h.name,
            "side": h.side,
            "price": h.price,
            "matched_count": len(h.matched),
            "total_rules": h.total_rules,
            "matched": [list(x) for x in h.matched],
        } for h in hits[:top_n]]

        result = {
            "run_date": self._today(),
            "pool": pool,
            "side": side,
            "params_hash": params_hash,
            "universe_count": stats["universe"],
            "quoted_pass": stats["quoted_pass"],
            "candidate_count": stats["candidates"],
            "scanned_count": len(candidates),
            "hit_count": len(hits),
            "top_n": top_n,
            "duration_seconds": round(time.perf_counter() - started, 1),
            "hits": picked,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "note": "仅为技术面信号，不构成投资建议",
        }
        if save:
            self._save(result)
            logger.info(
                f"扫描完成并落库: 命中 {len(hits)} 只，耗时 {result['duration_seconds']}s"
            )
        return {**result, "cached": False}

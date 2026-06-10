"""可配置选股引擎 — Screener

设计思路
========
1. 条件以注册表（CONDITION_REGISTRY）方式可插拔，每个条件独立函数；
2. 用户通过 config.yaml 的 screener 段定义买入/卖出规则；
3. 聚合模式（mode）支持:
     all          → 全部满足
     any          → 任一满足
     atleast:N    → 至少 N 条满足
4. 数据源复用 MarketService.get_kline_df + FeatureEngine.build_features，
   股票池可来自自选股、本地 codes 文件或自定义代码列表。

新增条件方法
==============
    @register_condition("my_cond")
    def my_cond(ctx: ScreenContext, params: dict) -> ConditionResult:
        ...
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable, Optional

import pandas as pd

from app.ai.feature_engine import FeatureEngine
from app.services.market_service import MarketService


# ============================================================================
# 数据结构
# ============================================================================


@dataclass
class ConditionResult:
    """单条条件评估结果"""
    passed: bool
    detail: str = ""           # 人类可读的描述（如 "MA20=10.20 (向上)"）


@dataclass
class ScreenContext:
    """单只股票的评估上下文"""
    code: str
    name: str = ""
    df: pd.DataFrame = field(default_factory=pd.DataFrame)   # 已计算特征的 K 线
    last: Optional[pd.Series] = None                          # df.iloc[-1]
    quote: dict = field(default_factory=dict)                 # 实时行情
    position: Optional[dict] = None                           # 持仓信息（如 avg_cost, current_price）
    benchmark_df: Optional[pd.DataFrame] = None               # 基准（行业/大盘）K 线


@dataclass
class ScreenHit:
    """命中结果"""
    code: str
    name: str
    side: str                          # "buy" / "sell"
    price: float
    matched: list[tuple[str, str]]     # [(rule_name, detail), ...]
    total_rules: int


# ============================================================================
# 条件注册表
# ============================================================================

ConditionFn = Callable[[ScreenContext, dict], ConditionResult]
CONDITION_REGISTRY: dict[str, ConditionFn] = {}


def register_condition(name: str):
    """装饰器：注册条件函数"""

    def deco(fn: ConditionFn):
        CONDITION_REGISTRY[name] = fn
        return fn

    return deco


# ============================================================================
# 内置条件 — 买入侧
# ============================================================================


@register_condition("ma_uptrend")
def cond_ma_uptrend(ctx: ScreenContext, params: dict) -> ConditionResult:
    """均线向上：当前 MA(N) > lookback 日前 MA(N)"""
    n = int(params.get("ma", 20))
    lookback = int(params.get("lookback", 5))
    col = f"ma{n}"
    if col not in ctx.df.columns or len(ctx.df) <= lookback:
        return ConditionResult(False, f"{col} 数据不足")
    cur = ctx.df[col].iloc[-1]
    prev = ctx.df[col].iloc[-1 - lookback]
    if pd.isna(cur) or pd.isna(prev):
        return ConditionResult(False, f"{col} 含 NaN")
    passed = cur > prev
    arrow = "↑" if passed else "↓"
    return ConditionResult(
        passed,
        f"MA{n}: {prev:.2f} → {cur:.2f} {arrow}",
    )


@register_condition("price_above_ma")
def cond_price_above_ma(ctx: ScreenContext, params: dict) -> ConditionResult:
    """股价站上 MA(N)"""
    n = int(params.get("ma", 20))
    col = f"ma{n}"
    if ctx.last is None or col not in ctx.df.columns:
        return ConditionResult(False, f"{col} 不存在")
    price = ctx.last["close"]
    ma = ctx.last[col]
    if pd.isna(ma):
        return ConditionResult(False, f"{col}=NaN")
    passed = price > ma
    sign = ">" if passed else "≤"
    return ConditionResult(passed, f"价 {price:.2f} {sign} MA{n} {ma:.2f}")


@register_condition("price_below_ma")
def cond_price_below_ma(ctx: ScreenContext, params: dict) -> ConditionResult:
    """股价跌破 MA(N)"""
    n = int(params.get("ma", 10))
    col = f"ma{n}"
    if ctx.last is None or col not in ctx.df.columns:
        return ConditionResult(False, f"{col} 不存在")
    price = ctx.last["close"]
    ma = ctx.last[col]
    if pd.isna(ma):
        return ConditionResult(False, f"{col}=NaN")
    passed = price < ma
    sign = "<" if passed else "≥"
    return ConditionResult(passed, f"价 {price:.2f} {sign} MA{n} {ma:.2f}")


@register_condition("volume_expand")
def cond_volume_expand(ctx: ScreenContext, params: dict) -> ConditionResult:
    """成交量放大：当日成交量 > N 日均量 × ratio"""
    window = int(params.get("ma_window", 5))
    ratio = float(params.get("ratio", 1.5))
    col = f"vol_ma{window}" if f"vol_ma{window}" in ctx.df.columns else None
    if ctx.last is None:
        return ConditionResult(False, "无K线")
    cur_vol = ctx.last["volume"]
    if col:
        avg_vol = ctx.last[col]
    else:
        avg_vol = ctx.df["volume"].iloc[-window - 1:-1].mean() if len(ctx.df) > window else None
    if avg_vol is None or pd.isna(avg_vol) or avg_vol <= 0:
        return ConditionResult(False, "均量数据不足")
    r = cur_vol / avg_vol
    passed = r >= ratio
    return ConditionResult(passed, f"量比 {r:.2f}x (阈 {ratio:.2f}x)")


@register_condition("sector_strong")
def cond_sector_strong(ctx: ScreenContext, params: dict) -> ConditionResult:
    """行业/板块强势：个股 N 日涨幅强于基准

    需 ScreenContext.benchmark_df 已注入；若未注入直接 False。
    阈值 advantage：个股涨幅 - 基准涨幅 ≥ advantage(%)
    """
    window = int(params.get("window", 5))
    advantage = float(params.get("advantage", 0.0))
    if ctx.benchmark_df is None or ctx.benchmark_df.empty:
        return ConditionResult(False, "无基准数据")
    if len(ctx.df) <= window or len(ctx.benchmark_df) <= window:
        return ConditionResult(False, "K 线不足")

    stock_ret = (ctx.df["close"].iloc[-1] / ctx.df["close"].iloc[-1 - window] - 1) * 100
    bench_ret = (
        ctx.benchmark_df["close"].iloc[-1] / ctx.benchmark_df["close"].iloc[-1 - window] - 1
    ) * 100
    diff = stock_ret - bench_ret
    passed = diff >= advantage
    return ConditionResult(
        passed,
        f"{window}日 个股 {stock_ret:+.2f}% vs 基准 {bench_ret:+.2f}% (Δ{diff:+.2f}%)",
    )


@register_condition("ma_bull")
def cond_ma_bull(ctx: ScreenContext, params: dict) -> ConditionResult:
    """均线多头排列 MA5>MA10>MA20"""
    if ctx.last is None or "ma_bull" not in ctx.df.columns:
        return ConditionResult(False, "无 ma_bull")
    passed = bool(ctx.last["ma_bull"])
    return ConditionResult(passed, "多头排列" if passed else "非多头")


@register_condition("macd_golden")
def cond_macd_golden(ctx: ScreenContext, params: dict) -> ConditionResult:
    """MACD 金叉（最近 N 根内出现）"""
    lookback = int(params.get("lookback", 1))
    if "macd_cross" not in ctx.df.columns or len(ctx.df) < lookback:
        return ConditionResult(False, "无 macd_cross")
    recent = ctx.df["macd_cross"].iloc[-lookback:]
    passed = (recent == 1).any()
    return ConditionResult(passed, f"近{lookback}根{'有' if passed else '无'}金叉")


@register_condition("rsi_below")
def cond_rsi_below(ctx: ScreenContext, params: dict) -> ConditionResult:
    """RSI(N) 低于阈值（超卖）"""
    period = int(params.get("period", 6))
    threshold = float(params.get("threshold", 30))
    col = f"rsi{period}"
    if ctx.last is None or col not in ctx.df.columns:
        return ConditionResult(False, f"无 {col}")
    val = ctx.last[col]
    if pd.isna(val):
        return ConditionResult(False, f"{col}=NaN")
    passed = val < threshold
    return ConditionResult(passed, f"RSI({period})={val:.1f} (阈 <{threshold})")


@register_condition("breakout")
def cond_breakout(ctx: ScreenContext, params: dict) -> ConditionResult:
    """突破 N 日新高（最高价突破前 N 日最高）"""
    window = int(params.get("window", 20))
    if len(ctx.df) <= window:
        return ConditionResult(False, "K 线不足")
    cur_high = ctx.df["high"].iloc[-1]
    prev_max = ctx.df["high"].iloc[-1 - window:-1].max()
    passed = cur_high > prev_max
    return ConditionResult(passed, f"H {cur_high:.2f} vs 前{window}日 {prev_max:.2f}")


# ============================================================================
# 内置条件 — 卖出侧（部分依赖持仓）
# ============================================================================


@register_condition("bearish_volume")
def cond_bearish_volume(ctx: ScreenContext, params: dict) -> ConditionResult:
    """放量长阴：当日跌幅≥drop_pct 且 量比≥vol_ratio"""
    drop_pct = float(params.get("drop_pct", 3.0))
    vol_ratio = float(params.get("vol_ratio", 1.5))
    window = int(params.get("ma_window", 5))
    if ctx.last is None or len(ctx.df) < 2:
        return ConditionResult(False, "K 线不足")

    cur_close = ctx.last["close"]
    cur_open = ctx.last["open"]
    prev_close = ctx.df["close"].iloc[-2]
    chg = (cur_close / prev_close - 1) * 100 if prev_close else 0
    is_red = cur_close < cur_open

    col = f"vol_ma{window}" if f"vol_ma{window}" in ctx.df.columns else None
    avg_vol = ctx.last[col] if col else ctx.df["volume"].iloc[-window - 1:-1].mean()
    cur_vol = ctx.last["volume"]
    vr = cur_vol / avg_vol if avg_vol and avg_vol > 0 else 0

    passed = is_red and chg <= -drop_pct and vr >= vol_ratio
    return ConditionResult(
        passed,
        f"涨跌 {chg:+.2f}% / 量比 {vr:.2f}x / 阴={is_red}",
    )


@register_condition("loss_pct")
def cond_loss_pct(ctx: ScreenContext, params: dict) -> ConditionResult:
    """亏损达到阈值（需持仓 avg_cost）"""
    threshold = float(params.get("threshold", 8.0))
    if not ctx.position:
        return ConditionResult(False, "无持仓数据")
    cost = ctx.position.get("avg_cost", 0)
    price = ctx.position.get("current_price") or (ctx.last["close"] if ctx.last is not None else 0)
    if not cost or not price:
        return ConditionResult(False, "成本/现价缺失")
    pct = (price / cost - 1) * 100
    passed = pct <= -threshold
    return ConditionResult(passed, f"盈亏 {pct:+.2f}% (阈 ≤-{threshold}%)")


@register_condition("profit_pct")
def cond_profit_pct(ctx: ScreenContext, params: dict) -> ConditionResult:
    """盈利达到阈值（需持仓）"""
    threshold = float(params.get("threshold", 30.0))
    if not ctx.position:
        return ConditionResult(False, "无持仓数据")
    cost = ctx.position.get("avg_cost", 0)
    price = ctx.position.get("current_price") or (ctx.last["close"] if ctx.last is not None else 0)
    if not cost or not price:
        return ConditionResult(False, "成本/现价缺失")
    pct = (price / cost - 1) * 100
    passed = pct >= threshold
    return ConditionResult(passed, f"盈亏 {pct:+.2f}% (阈 ≥{threshold}%)")


@register_condition("macd_dead")
def cond_macd_dead(ctx: ScreenContext, params: dict) -> ConditionResult:
    """MACD 死叉（最近 N 根内）"""
    lookback = int(params.get("lookback", 1))
    if "macd_cross" not in ctx.df.columns or len(ctx.df) < lookback:
        return ConditionResult(False, "无 macd_cross")
    recent = ctx.df["macd_cross"].iloc[-lookback:]
    passed = (recent == -1).any()
    return ConditionResult(passed, f"近{lookback}根{'有' if passed else '无'}死叉")


@register_condition("rsi_above")
def cond_rsi_above(ctx: ScreenContext, params: dict) -> ConditionResult:
    """RSI(N) 高于阈值（超买）"""
    period = int(params.get("period", 6))
    threshold = float(params.get("threshold", 80))
    col = f"rsi{period}"
    if ctx.last is None or col not in ctx.df.columns:
        return ConditionResult(False, f"无 {col}")
    val = ctx.last[col]
    if pd.isna(val):
        return ConditionResult(False, f"{col}=NaN")
    passed = val > threshold
    return ConditionResult(passed, f"RSI({period})={val:.1f} (阈 >{threshold})")


# ============================================================================
# 聚合 / 评估
# ============================================================================


def _aggregate(results: list[ConditionResult], mode: str) -> tuple[bool, int]:
    """返回 (是否命中, 通过的条件数)"""
    passed_count = sum(1 for r in results if r.passed)
    total = len(results)
    mode = (mode or "all").lower().strip()

    if mode == "all":
        return passed_count == total and total > 0, passed_count
    if mode == "any":
        return passed_count >= 1, passed_count

    m = re.match(r"atleast:(\d+)", mode)
    if m:
        n = int(m.group(1))
        return passed_count >= n, passed_count

    # 默认 all
    return passed_count == total and total > 0, passed_count


# ============================================================================
# 主引擎
# ============================================================================


class ScreenerService:
    """选股引擎"""

    def __init__(self, screener_config: Optional[dict] = None):
        from app.config import get_config

        cfg = screener_config or get_config().get("screener", {}) or {}
        self.cfg = cfg
        self.market = MarketService()
        self.feature_engine = FeatureEngine()
        self._benchmark_cache: Optional[pd.DataFrame] = None

    # ---------- 公共入口 ----------

    def screen(
        self,
        codes: list[str],
        side: str = "buy",
        positions: Optional[dict] = None,
        progress_cb: Optional[Callable[[int, int, int], None]] = None,
    ) -> list[ScreenHit]:
        """筛选

        Args:
            codes:    待评估股票代码列表
            side:     "buy" / "sell"
            positions: {code: position_dict}  仅 sell 时需要
            progress_cb: 进度回调 fn(已处理, 总数, 命中数)

        Returns:
            命中列表
        """
        side = side.lower()
        rules_block = self.cfg.get(side, {}) or {}
        rules = rules_block.get("rules", []) or []
        mode = rules_block.get("mode", "all")
        if not rules:
            return []

        # 预取基准数据（如果有任何规则用到 sector_strong）
        need_bench = any(r.get("name") == "sector_strong" for r in rules)
        if need_bench and self._benchmark_cache is None:
            self._benchmark_cache = self._fetch_benchmark()

        min_kline = int(self.cfg.get("min_kline", 30))
        kline_count = int(self.cfg.get("kline_count", 90))
        max_workers = max(1, int(self.cfg.get("max_workers", 4)))
        # K线最新日期距今允许的最大天数（用于过滤退市/长期停牌股）
        max_kline_age_days = int(self.cfg.get("max_kline_age_days", 14))

        # 大池场景下不预取所有 quote（耗时且不必要），仅取小池
        quotes: dict = {}
        if len(codes) <= 200:
            try:
                quotes = self.market.get_quote(*codes) if codes else {}
            except Exception:
                quotes = {}

        # 大池时从 pool_loader 缓存读取名称（避免名称全显 "-"）
        name_map: dict = {}
        if len(codes) > 200:
            try:
                from app.services.pool_loader import get_all_a_name_map
                name_map = get_all_a_name_map(max_age_days=365)
            except Exception:
                name_map = {}

        # 当前日期，用于过滤过期 K 线
        from datetime import datetime as _dt, timedelta as _td
        today = _dt.now().date()
        stale_threshold = today - _td(days=max_kline_age_days)

        def _resolve_name(code: str) -> str:
            if isinstance(quotes, dict) and quotes.get(code):
                n = quotes[code].get("name", "")
                if n:
                    return n
            return name_map.get(code, "")

        # ---- 单只股票评估（线程内执行）----
        def _eval_one(code: str) -> Optional[ScreenHit]:
            try:
                df_raw = self.market.get_kline_df(
                    code, period="day", count=kline_count, adjust="qfq"
                )
                if df_raw is None or df_raw.empty or len(df_raw) < min_kline:
                    return None

                # 过滤退市/长期停牌：最后一根 K 线日期太老
                last_date_str = str(df_raw.iloc[-1].get("date", ""))
                try:
                    last_date = _dt.strptime(last_date_str[:10], "%Y-%m-%d").date()
                    if last_date < stale_threshold:
                        return None
                except Exception:
                    pass  # 解析失败时不过滤，交由后续逻辑

                df = self.feature_engine.build_features(df_raw, dropna=False)
                df = df.dropna(subset=[c for c in ["ma20", "ma10", "ma5"] if c in df.columns])
                if df.empty:
                    return None

                ctx = ScreenContext(
                    code=code,
                    name=_resolve_name(code),
                    df=df,
                    last=df.iloc[-1],
                    quote=quotes.get(code, {}) if isinstance(quotes, dict) else {},
                    position=(positions or {}).get(code),
                    benchmark_df=self._benchmark_cache,
                )

                results: list[ConditionResult] = []
                detail_pairs: list[tuple[str, str]] = []
                for rule in rules:
                    rname = rule.get("name", "")
                    rparams = rule.get("params", {}) or {}
                    fn = CONDITION_REGISTRY.get(rname)
                    if not fn:
                        continue
                    try:
                        r = fn(ctx, rparams)
                    except Exception as e:
                        r = ConditionResult(False, f"err: {e}")
                    results.append(r)
                    if r.passed:
                        detail_pairs.append((rname, r.detail))

                hit_flag, _ = _aggregate(results, mode)
                if hit_flag:
                    return ScreenHit(
                        code=code,
                        name=ctx.name,
                        side=side,
                        price=float(ctx.last["close"]),
                        matched=detail_pairs,
                        total_rules=len(results),
                    )
                return None
            except Exception:
                return None

        hits: list[ScreenHit] = []
        total = len(codes)
        processed = 0

        # 并发执行
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(_eval_one, c): c for c in codes}
            for fut in as_completed(futures):
                processed += 1
                hit = fut.result()
                if hit is not None:
                    hits.append(hit)
                if progress_cb:
                    progress_cb(processed, total, len(hits))

        return hits

    # ---------- 工具 ----------

    def _fetch_benchmark(self) -> Optional[pd.DataFrame]:
        bench_code = self.cfg.get("benchmark", "sz399101")  # 默认中证1000
        try:
            df_raw = self.market.get_kline_df(bench_code, period="day", count=60, adjust="")
            if df_raw is None or df_raw.empty:
                return None
            return df_raw
        except Exception:
            return None

    def resolve_pool(self, pool: Optional[str] = None) -> list[str]:
        """解析股票池

        支持：
            "watchlist"        自选股
            "portfolio"        当前持仓
            "all_a"            全 A 股（带本地缓存，首次需构建）
            "all_a:refresh"    强制刷新全 A 缓存
            "file:./codes.txt" 本地文件（每行一个代码）
            "code1,code2,..."  直接代码列表
        """
        pool = (pool or self.cfg.get("pool", "watchlist") or "").strip()

        if pool == "watchlist":
            from app.services.watchlist_service import WatchlistService
            return [s.code for s in WatchlistService().list_watched()]

        if pool == "portfolio":
            from app.services.portfolio_service import PortfolioService
            return [h.stock_code for h in PortfolioService().get_portfolio()]

        if pool.startswith("all_a"):
            from app.services.pool_loader import get_all_a_codes
            refresh = pool.endswith(":refresh")
            max_age = int(self.cfg.get("all_a_cache_days", 7))
            exclude_delisted = bool(self.cfg.get("exclude_delisted", True))
            exclude_st = bool(self.cfg.get("exclude_st", False))
            codes = get_all_a_codes(
                refresh=refresh,
                max_age_days=max_age,
                exclude_delisted=exclude_delisted,
                exclude_st=exclude_st,
            )
            # 池规模上限保护
            limit = int(self.cfg.get("pool_size_limit", 0) or 0)
            if limit > 0 and len(codes) > limit:
                codes = codes[:limit]
            return codes

        if pool.startswith("file:"):
            path = pool[5:].strip()
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return [
                        line.strip()
                        for line in f
                        if line.strip() and not line.strip().startswith("#")
                    ]
            except Exception:
                return []

        # 直接代码列表
        return [c.strip() for c in pool.split(",") if c.strip()]

    @staticmethod
    def list_conditions() -> list[str]:
        return sorted(CONDITION_REGISTRY.keys())

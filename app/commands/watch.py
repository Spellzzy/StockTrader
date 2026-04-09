"""实时看盘模式 — 从 cli.py 拆分

包含：
- 辅助格式化函数 (_fmt_delta, _fmt_vol_delta, _speed_label, _limit_pct)
- 指数识别常量与函数
- 排序字段映射
- _do_watch 核心实现
"""

from datetime import datetime
from app.commands import console, Table, Panel, box


# ==================== 辅助格式化 ====================

def _fmt_delta(val: float, suffix: str = "", precision: int = 2) -> str:
    """格式化差异值：正数绿色↑  负数红色↓  零灰色"""
    if abs(val) < 1e-6:
        return f"[dim]—{suffix}[/dim]"
    fmt = f"{val:+.{precision}f}{suffix}"
    if val > 0:
        return f"[green]{fmt} ↑[/green]"
    else:
        return f"[red]{fmt} ↓[/red]"


def _fmt_vol_delta(cur: float, prev: float) -> str:
    """格式化成交量增量"""
    delta = cur - prev
    if abs(delta) < 1:
        return "[dim]—[/dim]"
    if delta > 0:
        d_str = f"{delta / 10000:.1f}万" if delta > 10000 else str(int(delta))
        return f"[green]+{d_str} ↑[/green]"
    else:
        d_str = f"{abs(delta) / 10000:.1f}万" if abs(delta) > 10000 else str(int(abs(delta)))
        return f"[red]-{d_str} ↓[/red]"


def _speed_label(price_delta: float, seconds: int) -> str:
    """价格变动速度标签"""
    if abs(price_delta) < 0.001:
        return ""
    speed = abs(price_delta) / (seconds / 60) if seconds > 0 else 0
    if speed >= 1.0:
        tag = "⚡快速" if price_delta > 0 else "⚡急跌"
        return f" [{('green' if price_delta > 0 else 'red')}]{tag}[/{('green' if price_delta > 0 else 'red')}]"
    elif speed >= 0.3:
        tag = "🔥活跃"
        return f" [yellow]{tag}[/yellow]"
    return ""


def _limit_pct(code: str) -> float:
    """根据股票代码判断涨跌停比例：创业板(300)/科创板(688) ±20%, 北交所(8/4) ±30%, 其余 ±10%"""
    pure = code.replace("sh", "").replace("sz", "").replace("bj", "")
    if pure.startswith("300") or pure.startswith("688"):
        return 0.20
    elif pure.startswith("8") or pure.startswith("4"):
        return 0.30
    return 0.10


# ==================== 指数识别 ====================

# 常见大盘指数代码（标准化后）
_DEFAULT_INDEX_CODES = ["sh000001", "sz399001", "sz399006", "sh000688"]
_DEFAULT_INDEX_NAMES = {
    "sh000001": "上证指数",
    "sz399001": "深证成指",
    "sz399006": "创业板指",
    "sh000688": "科创50",
}


def _is_index_code(code: str) -> bool:
    """判断是否为指数代码（非个股）

    规则:
    - sh000xxx  上证系列指数
    - sz399xxx  深证系列指数
    - sh000688  科创50
    """
    pure = code.lower()
    if pure.startswith("sh000") or pure.startswith("sz399"):
        return True
    return False


# 排序字段映射
_SORT_KEYS = {
    "chg": ("涨跌幅", lambda q: q.get("change_percent", 0)),
    "amp": ("振幅", None),   # 需要动态计算
    "vol": ("成交额", lambda q: q.get("amount", 0) or q.get("turnover", 0)),
    "vr":  ("量比", lambda q: q.get("volume_ratio", 0) or q.get("vol_ratio", 0)),
    "tr":  ("换手率", lambda q: q.get("turnover_rate", 0)),
}


# ==================== 核心实现 ====================

def do_watch(codes_str: str, interval: int, alert_only: bool, sort_by: str = "chg"):
    """看盘模式内部实现（含轮次间差异对比）"""
    from app.services.alert_service import AlertService
    from app.services.watchlist_service import WatchlistService
    from app.services.market_service import MarketService

    # 解析股票代码
    codes = []
    if codes_str:
        codes = [c.strip() for c in codes_str.split(",") if c.strip()]
    else:
        watched = WatchlistService().list_watched()
        codes = [s.code for s in watched]

    if not codes:
        console.print("[yellow]请指定股票代码或先添加自选股 (stock-ai star <代码>)[/yellow]")
        return

    # ── 分离指数代码与个股代码 ──
    user_index_codes = [c for c in codes if _is_index_code(c)]
    stock_codes = [c for c in codes if not _is_index_code(c)]

    # 自动追加默认大盘指数（去重）
    index_codes = list(dict.fromkeys(user_index_codes + [c for c in _DEFAULT_INDEX_CODES if c not in user_index_codes]))

    # 合并所有需要请求行情的代码（指数 + 个股，去重）
    all_codes = list(dict.fromkeys(index_codes + stock_codes))

    # ── 间隔保护 ──
    MIN_INTERVAL = 10
    stock_count = len(stock_codes)
    all_count = len(all_codes)
    if interval < MIN_INTERVAL:
        console.print(
            f"[yellow]⚠️ 刷新间隔 {interval}s 过短，已自动调整为 {MIN_INTERVAL}s "
            f"(最小间隔 {MIN_INTERVAL}s)[/yellow]"
        )
        interval = MIN_INTERVAL

    # 根据股票数量建议合理间隔
    suggested = max(MIN_INTERVAL, all_count * 3)
    if interval < suggested and all_count > 5:
        console.print(
            f"[yellow]💡 监控 {all_count} 只标的，建议间隔 ≥ {suggested}s "
            f"(当前 {interval}s)[/yellow]"
        )

    svc = AlertService()
    market = MarketService()
    round_count = 0
    prev_quotes: dict = {}  # 上一轮行情数据
    first_quotes: dict = {}  # 首轮行情数据 (用于累计变动)
    total_api_calls = 0  # API 请求计数
    _vol_avg5: dict = {}  # 5日均量缓存 {code: 5日日均成交量(股)}
    _VR_BATCH = 2  # 每轮最多补充获取K线的股票数
    _tech_cache: dict = {}  # 技术指标跨轮缓存 {code: {...}}
    _tech_cache_ts: float = 0  # 技术指标缓存时间戳
    _TECH_CACHE_TTL = 300  # 技术指标缓存有效期（秒），日K级指标5分钟刷新即可

    idx_info = f" + {len(index_codes)}指数" if index_codes else ""
    console.print(f"[cyan]👀 实时看盘模式 — 监控 {stock_count} 只个股{idx_info} (每{interval}秒刷新, Ctrl+C 退出)[/cyan]\n")

    try:
        import time as time_mod

        while True:
            round_count += 1
            now_str = datetime.now().strftime("%H:%M:%S")
            has_prev = bool(prev_quotes)
            round_api_calls = 0

            try:
                # 获取行情（指数 + 个股，一次请求）
                quotes_data = market.get_quote(*all_codes)
                round_api_calls += 1

                # 首轮记录基准数据（仅个股）
                if not first_quotes:
                    first_quotes = {
                        code: {
                            "price": quotes_data.get(code, {}).get("price", 0),
                            "volume": quotes_data.get(code, {}).get("volume", 0),
                            "change_percent": quotes_data.get(code, {}).get("change_percent", 0),
                        }
                        for code in stock_codes
                        if quotes_data.get(code)
                    }

                # 渐进式获取5日均量（每轮最多补充 _VR_BATCH 只，避免首轮请求过多）
                _pending_vr = [c for c in stock_codes if c not in _vol_avg5]
                for code in _pending_vr[:_VR_BATCH]:
                    try:
                        kdf = market.get_kline_df(code, "day", 6)
                        round_api_calls += 1
                        if not kdf.empty and len(kdf) >= 2:
                            # 排除最后一行（当天）,取前5日均量
                            hist = kdf.iloc[:-1]
                            if len(hist) > 0:
                                _vol_avg5[code] = hist["volume"].mean()
                    except Exception:
                        _vol_avg5[code] = 0  # 标记已尝试，避免重复请求

                if not alert_only:
                    # ====== 📊 大盘指数面板（独立渲染）======
                    idx_parts = []
                    idx_total_amt = 0.0
                    for ic in index_codes:
                        iq = quotes_data.get(ic, {})
                        if not iq:
                            continue
                        idx_name = iq.get("name", "") or _DEFAULT_INDEX_NAMES.get(ic, ic)
                        idx_price = iq.get("price", 0)
                        idx_chg = iq.get("change_percent", 0)
                        idx_change = iq.get("change", 0)
                        idx_amt = iq.get("amount", 0) or iq.get("turnover", 0)
                        idx_total_amt += idx_amt
                        idx_high = iq.get("high", 0)
                        idx_low = iq.get("low", 0)

                        c = "green" if idx_chg > 0 else "red" if idx_chg < 0 else "dim"
                        arrow = "▲" if idx_chg > 0 else "▼" if idx_chg < 0 else "—"

                        # 格式化成交额
                        if idx_amt >= 1e8:
                            amt_s = f"{idx_amt / 1e8:.0f}亿"
                        elif idx_amt >= 1e4:
                            amt_s = f"{idx_amt / 1e4:.0f}万"
                        else:
                            amt_s = "-"

                        idx_parts.append(
                            f"[bold]{idx_name}[/bold]  "
                            f"[{c}]{idx_price:,.2f}  {arrow}{idx_chg:+.2f}%  {idx_change:+.2f}[/{c}]  "
                            f"[dim]高{idx_high:,.2f} 低{idx_low:,.2f} 额{amt_s}[/dim]"
                        )

                    if idx_parts:
                        # 成交额汇总
                        if idx_total_amt >= 1e8:
                            total_s = f"{idx_total_amt / 1e8:.0f}亿"
                        else:
                            total_s = f"{idx_total_amt / 1e4:.0f}万"

                        idx_text = "\n".join(idx_parts)
                        idx_text += f"\n[dim]──  两市合计成交额: {total_s}  ──[/dim]"
                        console.print(Panel(
                            idx_text,
                            title=f"📊 大盘指数 [{now_str}]",
                            border_style="bright_blue",
                            expand=False,
                            padding=(0, 2),
                        ))

                    # ====== 预计算每只个股的振幅（排序和显示共用）======
                    _amp_cache = {}
                    _pre_close_cache = {}
                    for code in stock_codes:
                        q = quotes_data.get(code, {})
                        if not q:
                            continue
                        high = q.get("high", 0)
                        low = q.get("low", 0)
                        pre_close = q.get("pre_close", 0) or q.get("yesterday_close", 0)
                        if not pre_close:
                            cur_p = q.get("price", 0)
                            cur_c = q.get("change", 0)
                            pre_close = cur_p - cur_c if cur_p and cur_c else 0
                        _pre_close_cache[code] = pre_close
                        _amp_cache[code] = ((high - low) / pre_close * 100) if pre_close else 0

                    # ====== 预计算量比缓存 ======
                    _vr_cache = {}
                    now_dt = datetime.now()
                    TOTAL_MINUTES = 240
                    morning_start = now_dt.replace(hour=9, minute=30, second=0)
                    morning_end = now_dt.replace(hour=11, minute=30, second=0)
                    afternoon_start = now_dt.replace(hour=13, minute=0, second=0)
                    afternoon_end = now_dt.replace(hour=15, minute=0, second=0)
                    _elapsed_min = 0
                    if now_dt >= afternoon_end:
                        _elapsed_min = TOTAL_MINUTES
                    elif now_dt >= afternoon_start:
                        _elapsed_min = 120 + (now_dt - afternoon_start).total_seconds() / 60
                    elif now_dt >= morning_end:
                        _elapsed_min = 120
                    elif now_dt >= morning_start:
                        _elapsed_min = (now_dt - morning_start).total_seconds() / 60
                    for code in stock_codes:
                        q = quotes_data.get(code, {})
                        if not q:
                            continue
                        vr = q.get("volume_ratio", 0) or q.get("vol_ratio", 0)
                        if vr and vr > 0:
                            _vr_cache[code] = vr
                        elif _elapsed_min > 0 and code in _vol_avg5 and _vol_avg5[code] > 0:
                            cur_vol = q.get("volume", 0)
                            avg5 = _vol_avg5[code]
                            expected = avg5 * (_elapsed_min / TOTAL_MINUTES)
                            if expected > 0:
                                _vr_cache[code] = cur_vol / expected

                    # ====== 排序（仅个股）======
                    sort_label = _SORT_KEYS.get(sort_by, _SORT_KEYS["chg"])[0]
                    valid_codes = [c for c in stock_codes if quotes_data.get(c)]
                    if sort_by == "amp":
                        valid_codes.sort(key=lambda c: _amp_cache.get(c, 0), reverse=True)
                    elif sort_by == "vr":
                        valid_codes.sort(key=lambda c: _vr_cache.get(c, 0), reverse=True)
                    elif sort_by in _SORT_KEYS and _SORT_KEYS[sort_by][1]:
                        valid_codes.sort(key=lambda c: _SORT_KEYS[sort_by][1](quotes_data.get(c, {})), reverse=True)
                    else:
                        valid_codes.sort(key=lambda c: quotes_data.get(c, {}).get("change_percent", 0), reverse=True)

                    # ====== 主行情表 ======
                    table = Table(
                        title=f"👀 实时行情 [{now_str}] (第{round_count}轮) [dim]排序:{sort_label}↓[/dim]",
                        box=box.ROUNDED,
                        header_style="bold cyan",
                        show_lines=True,
                    )
                    table.add_column("#", width=3, justify="right")
                    table.add_column("代码", width=10)
                    table.add_column("名称", width=8)
                    table.add_column("现价", width=9, justify="right")
                    table.add_column("涨跌幅", width=9, justify="right")
                    table.add_column("涨跌额", width=9, justify="right")
                    table.add_column("最高", width=9, justify="right")
                    table.add_column("最低", width=9, justify="right")
                    table.add_column("振幅", width=8, justify="right")
                    table.add_column("成交量", width=10, justify="right")
                    table.add_column("成交额", width=10, justify="right")
                    table.add_column("换手率", width=8, justify="right")
                    table.add_column("量比", width=7, justify="right")
                    table.add_column("委比", width=8, justify="right")
                    table.add_column("内外盘", width=12, justify="right")
                    table.add_column("距涨停", width=8, justify="right")
                    table.add_column("距跌停", width=8, justify="right")

                    # 统计汇总变量
                    _stat_up = 0      # 上涨家数
                    _stat_down = 0    # 下跌家数
                    _stat_flat = 0    # 平盘家数
                    _stat_chg_sum = 0.0  # 涨跌幅之和
                    _stat_amt_sum = 0.0  # 成交额之和
                    _stat_count = 0

                    for rank, code in enumerate(valid_codes, 1):
                        q = quotes_data.get(code, {})
                        chg = q.get("change_percent", 0)
                        vol = q.get("volume", 0)
                        vol_str = f"{vol / 10000:.1f}万" if vol > 10000 else str(int(vol)) if vol else "-"

                        # ---- 行级着色 ----
                        if chg > 0:
                            row_style = "on #1a2e1a"  # 淡绿底
                            color = "green"
                            _stat_up += 1
                        elif chg < 0:
                            row_style = "on #2e1a1a"  # 淡红底
                            color = "red"
                            _stat_down += 1
                        else:
                            row_style = ""
                            color = "dim"
                            _stat_flat += 1
                        _stat_chg_sum += chg
                        _stat_count += 1

                        # ---- 振幅 (使用缓存) ----
                        high = q.get("high", 0)
                        low = q.get("low", 0)
                        pre_close = _pre_close_cache.get(code, 0)
                        amplitude = _amp_cache.get(code, 0)
                        amp_str = f"{amplitude:.2f}%"

                        # ---- 成交额 ----
                        amount = q.get("amount", 0) or q.get("turnover", 0)
                        _stat_amt_sum += amount
                        if amount >= 1e8:
                            amt_str = f"{amount / 1e8:.2f}亿"
                        elif amount >= 1e4:
                            amt_str = f"{amount / 1e4:.1f}万"
                        elif amount > 0:
                            amt_str = f"{amount:.0f}"
                        else:
                            amt_str = "-"

                        # ---- 量比（使用预计算缓存）----
                        vol_ratio = _vr_cache.get(code, 0)
                        if vol_ratio:
                            vr_color = "red" if vol_ratio >= 3 else "yellow" if vol_ratio >= 1.5 else "green" if vol_ratio >= 0.8 else "dim"
                            vr_str = f"[{vr_color}]{vol_ratio:.2f}[/{vr_color}]"
                        else:
                            vr_str = "[dim]-[/dim]"

                        # ---- 委比（五档盘口计算）----
                        wb = q.get("committee_ratio", None)
                        if wb is None:
                            # 用五档买卖挂单量求和
                            bid_vol = sum(q.get(f"bid{i}_vol", 0) or 0 for i in range(1, 6))
                            ask_vol = sum(q.get(f"ask{i}_vol", 0) or 0 for i in range(1, 6))
                            if bid_vol or ask_vol:
                                wb = (bid_vol - ask_vol) / (bid_vol + ask_vol) * 100 if (bid_vol + ask_vol) > 0 else 0
                        if wb is not None:
                            wb_color = "green" if wb > 0 else "red" if wb < 0 else "dim"
                            wb_str = f"[{wb_color}]{wb:+.1f}%[/{wb_color}]"
                        else:
                            wb_str = "[dim]-[/dim]"

                        # ---- 内外盘比 ----
                        outer = q.get("outer_volume", 0) or q.get("buy_count", 0)
                        inner = q.get("inner_volume", 0) or q.get("sell_count", 0)
                        if outer or inner:
                            o_str = f"{outer / 10000:.1f}万" if outer > 10000 else str(int(outer))
                            i_str = f"{inner / 10000:.1f}万" if inner > 10000 else str(int(inner))
                            io_ratio = outer / inner if inner > 0 else 0
                            io_color = "green" if io_ratio > 1 else "red"
                            io_str = f"[{io_color}]{o_str}/{i_str}[/{io_color}]"
                        else:
                            io_str = "[dim]-[/dim]"

                        # ---- 距涨停/跌停（自适应板块） ----
                        cur_price = q.get("price", 0)
                        lp = _limit_pct(code)
                        if pre_close > 0 and cur_price > 0:
                            limit_up = round(pre_close * (1 + lp), 2)
                            limit_down = round(pre_close * (1 - lp), 2)
                            dist_up = (limit_up - cur_price) / cur_price * 100
                            dist_down = (cur_price - limit_down) / cur_price * 100
                            up_str = f"[green]{dist_up:.2f}%[/green]" if dist_up > 1 else f"[red bold]{dist_up:.2f}%[/red bold]"
                            dn_str = f"[green]{dist_down:.2f}%[/green]" if dist_down > 1 else f"[red bold]{dist_down:.2f}%[/red bold]"
                        else:
                            up_str = "[dim]-[/dim]"
                            dn_str = "[dim]-[/dim]"

                        table.add_row(
                            f"[bold]{rank}[/bold]",
                            code,
                            q.get("name", ""),
                            f"{cur_price:.2f}",
                            f"[{color}]{chg:+.2f}%[/{color}]",
                            f"[{color}]{q.get('change', 0):+.2f}[/{color}]",
                            f"{high:.2f}",
                            f"{low:.2f}",
                            amp_str,
                            vol_str,
                            amt_str,
                            f"{q.get('turnover_rate', 0):.2f}%",
                            vr_str,
                            wb_str,
                            io_str,
                            up_str,
                            dn_str,
                            style=row_style,
                        )

                    # ====== 统计摘要行 ======
                    if _stat_count > 0:
                        avg_chg = _stat_chg_sum / _stat_count
                        avg_color = "green" if avg_chg > 0 else "red" if avg_chg < 0 else "dim"
                        if _stat_amt_sum >= 1e8:
                            total_amt = f"{_stat_amt_sum / 1e8:.2f}亿"
                        elif _stat_amt_sum >= 1e4:
                            total_amt = f"{_stat_amt_sum / 1e4:.1f}万"
                        else:
                            total_amt = f"{_stat_amt_sum:.0f}"
                        table.add_row(
                            "",
                            "[bold]汇总[/bold]",
                            f"[dim]{_stat_count}只[/dim]",
                            "",
                            f"[{avg_color}]均{avg_chg:+.2f}%[/{avg_color}]",
                            "",
                            "",
                            "",
                            "",
                            "",
                            f"[bold]{total_amt}[/bold]",
                            "",
                            "",
                            "",
                            "",
                            f"[green]↑{_stat_up}[/green]",
                            f"[red]↓{_stat_down}[/red]",
                            style="on #1a1a2e",
                        )

                    console.print(table)

                    # ====== 差异对比表 (第2轮起显示) ======
                    if has_prev:
                        diff_table = Table(
                            title=f"📊 变动追踪 (对比上轮 Δ{interval}s) [dim]按|涨跌幅Δ|排序[/dim]",
                            box=box.SIMPLE_HEAVY,
                            header_style="bold yellow",
                            show_lines=True,
                        )
                        diff_table.add_column("#", width=3, justify="right")
                        diff_table.add_column("代码", width=10)
                        diff_table.add_column("名称", width=8)
                        diff_table.add_column("价格变动", width=12, justify="right")
                        diff_table.add_column("涨跌幅Δ", width=10, justify="right")
                        diff_table.add_column("振幅Δ", width=10, justify="right")
                        diff_table.add_column("成交量增量", width=12, justify="right")
                        diff_table.add_column("量比变动", width=10, justify="right")
                        diff_table.add_column("换手率Δ", width=10, justify="right")
                        diff_table.add_column("累计变动", width=12, justify="right")
                        diff_table.add_column("动向", width=10, justify="center")

                        # 预计算变动追踪数据并排序
                        diff_rows = []
                        for code in stock_codes:
                            q = quotes_data.get(code, {})
                            pq = prev_quotes.get(code, {})
                            fq = first_quotes.get(code, {})
                            if not q or not pq:
                                continue

                            cur_price = q.get("price", 0)
                            prev_price = pq.get("price", 0)
                            price_delta = cur_price - prev_price

                            cur_chg = q.get("change_percent", 0)
                            prev_chg = pq.get("change_percent", 0)
                            chg_delta = cur_chg - prev_chg

                            # ---- 振幅Δ ----
                            cur_high = q.get("high", 0)
                            cur_low = q.get("low", 0)
                            cur_pre_close = q.get("pre_close", 0) or q.get("yesterday_close", 0)
                            if not cur_pre_close:
                                cur_pre_close = cur_price - q.get("change", 0) if cur_price and q.get("change") else 0
                            cur_amp = ((cur_high - cur_low) / cur_pre_close * 100) if cur_pre_close else 0
                            prev_amp = pq.get("_amplitude", 0)
                            amp_delta = cur_amp - prev_amp

                            cur_vol = q.get("volume", 0)
                            prev_vol = pq.get("volume", 0)

                            # 量比变动
                            if prev_vol > 0:
                                vol_change_pct = (cur_vol - prev_vol) / prev_vol * 100
                            else:
                                vol_change_pct = 0

                            # ---- 换手率Δ ----
                            cur_turnover = q.get("turnover_rate", 0)
                            prev_turnover = pq.get("turnover_rate", 0)
                            turnover_delta = cur_turnover - prev_turnover

                            # 累计变动
                            first_price = fq.get("price", cur_price)
                            cum_delta = cur_price - first_price
                            cum_pct = (cum_delta / first_price * 100) if first_price else 0

                            # 动向判定
                            speed = _speed_label(price_delta, interval)
                            if abs(price_delta) < 0.001:
                                direction = "[dim]横盘[/dim]"
                            elif price_delta > 0:
                                direction = "[green]📈 上行[/green]"
                            else:
                                direction = "[red]📉 下行[/red]"
                            direction += speed

                            diff_rows.append({
                                "code": code,
                                "name": q.get("name", ""),
                                "price_delta": price_delta,
                                "chg_delta": chg_delta,
                                "amp_delta": amp_delta,
                                "cur_vol": cur_vol,
                                "prev_vol": prev_vol,
                                "vol_change_pct": vol_change_pct,
                                "turnover_delta": turnover_delta,
                                "cum_delta": cum_delta,
                                "cum_pct": cum_pct,
                                "direction": direction,
                            })

                        # 按 |涨跌幅Δ| 降序排序
                        diff_rows.sort(key=lambda r: abs(r["chg_delta"]), reverse=True)

                        for rank, row in enumerate(diff_rows, 1):
                            # 行级着色
                            if row["chg_delta"] > 0.001:
                                d_row_style = "on #1a2e1a"
                            elif row["chg_delta"] < -0.001:
                                d_row_style = "on #2e1a1a"
                            else:
                                d_row_style = ""

                            # 量比变动格式化
                            vcp = row["vol_change_pct"]
                            if abs(vcp) < 0.01:
                                vol_pct_str = "[dim]—[/dim]"
                            elif vcp > 0:
                                vol_pct_str = f"[green]+{vcp:.1f}% ↑[/green]"
                            else:
                                vol_pct_str = f"[red]{vcp:.1f}% ↓[/red]"

                            diff_table.add_row(
                                f"[bold]{rank}[/bold]",
                                row["code"],
                                row["name"],
                                _fmt_delta(row["price_delta"], "元"),
                                _fmt_delta(row["chg_delta"], "%"),
                                _fmt_delta(row["amp_delta"], "%"),
                                _fmt_vol_delta(row["cur_vol"], row["prev_vol"]),
                                vol_pct_str,
                                _fmt_delta(row["turnover_delta"], "%"),
                                _fmt_delta(row["cum_delta"], f"({row['cum_pct']:+.2f}%)", precision=2),
                                row["direction"],
                                style=d_row_style,
                            )

                        console.print(diff_table)

                        # ====== 异动提醒（增强版）======
                        movers = []
                        for code in stock_codes:
                            q = quotes_data.get(code, {})
                            pq = prev_quotes.get(code, {})
                            if not q or not pq:
                                continue
                            name = q.get("name", code)
                            cur_price = q.get("price", 0)
                            prev_price = pq.get("price", 0)
                            price_delta = cur_price - prev_price
                            pct_move = (price_delta / prev_price * 100) if prev_price else 0

                            cur_vol = q.get("volume", 0)
                            prev_vol = pq.get("volume", 0)
                            vol_delta = cur_vol - prev_vol

                            # ① 价格快速异动（单轮涨跌超0.5%）
                            if abs(pct_move) >= 0.5:
                                tag = "🚀 快速拉升" if pct_move > 0 else "💥 快速下跌"
                                color = "green" if pct_move > 0 else "red"
                                movers.append(
                                    f"  [{color}]{tag}[/{color}] "
                                    f"[bold]{name}({code})[/bold] "
                                    f"单轮变动 {pct_move:+.2f}% ({price_delta:+.2f}元)"
                                )

                            # ② 放量异动（成交量增量超前一轮总量的20%）
                            if prev_vol > 0 and vol_delta > 0:
                                vol_ratio = vol_delta / prev_vol
                                if vol_ratio >= 0.2:
                                    vol_d_str = f"{vol_delta / 10000:.1f}万" if vol_delta > 10000 else str(int(vol_delta))
                                    movers.append(
                                        f"  [yellow]📦 放量[/yellow] "
                                        f"[bold]{name}({code})[/bold] "
                                        f"成交增量 +{vol_d_str} (较上轮+{vol_ratio * 100:.0f}%)"
                                    )

                            # ③ 振幅骤增（振幅单轮扩大 ≥0.5%）
                            cur_amp_v = _amp_cache.get(code, 0)
                            prev_amp_v = pq.get("_amplitude", 0)
                            amp_jump = cur_amp_v - prev_amp_v
                            if amp_jump >= 0.5:
                                movers.append(
                                    f"  [magenta]🌊 振幅骤增[/magenta] "
                                    f"[bold]{name}({code})[/bold] "
                                    f"振幅 {prev_amp_v:.2f}%→{cur_amp_v:.2f}% (Δ+{amp_jump:.2f}%)"
                                )

                            # ④ 换手率飙升（换手率单轮增加 ≥0.3%）
                            cur_tr = q.get("turnover_rate", 0)
                            prev_tr = pq.get("turnover_rate", 0)
                            tr_jump = cur_tr - prev_tr
                            if tr_jump >= 0.3:
                                movers.append(
                                    f"  [cyan]🔄 换手飙升[/cyan] "
                                    f"[bold]{name}({code})[/bold] "
                                    f"换手率 {prev_tr:.2f}%→{cur_tr:.2f}% (Δ+{tr_jump:.2f}%)"
                                )

                            # ⑤ 接近涨停/跌停（距离 <1%）
                            pre_close = _pre_close_cache.get(code, 0)
                            lp = _limit_pct(code)
                            if pre_close > 0 and cur_price > 0:
                                limit_up = round(pre_close * (1 + lp), 2)
                                limit_down = round(pre_close * (1 - lp), 2)
                                dist_up = (limit_up - cur_price) / cur_price * 100
                                dist_down = (cur_price - limit_down) / cur_price * 100
                                if dist_up < 1 and dist_up > 0:
                                    movers.append(
                                        f"  [red bold]🔺 逼近涨停[/red bold] "
                                        f"[bold]{name}({code})[/bold] "
                                        f"距涨停仅 {dist_up:.2f}% (涨停价{limit_up:.2f})"
                                    )
                                if dist_down < 1 and dist_down > 0:
                                    movers.append(
                                        f"  [red bold]🔻 逼近跌停[/red bold] "
                                        f"[bold]{name}({code})[/bold] "
                                        f"距跌停仅 {dist_down:.2f}% (跌停价{limit_down:.2f})"
                                    )

                        if movers:
                            console.print(Panel(
                                "\n".join(movers),
                                title="⚡ 异动捕捉",
                                border_style="yellow",
                                expand=False,
                            ))

                # 检测预警（复用已获取的行情数据 + 技术指标跨轮缓存，避免重复请求）
                _now_ts = time_mod.time()
                if _now_ts - _tech_cache_ts > _TECH_CACHE_TTL:
                    _tech_cache.clear()
                    _tech_cache_ts = _now_ts
                triggered = svc.check_alerts(verbose=True, quotes_cache=quotes_data, tech_cache=_tech_cache)
                if triggered:
                    console.print(f"\n[bold red]🚨 {len(triggered)} 条预警触发！[/bold red]")
                    for t in triggered:
                        alert = t["alert"]
                        console.print(
                            f"  [red]🚨[/red] [bold]{alert.stock_code}[/bold] "
                            f"{alert.stock_name or ''} — {t['message']}"
                        )
                    console.print()

                if not alert_only:
                    if round_count == 1:
                        console.print("[dim]💡 首轮采集基准数据，下轮起显示变动追踪[/dim]")
                    _pending_count = len([c for c in stock_codes if c not in _vol_avg5])
                    if _pending_count > 0:
                        console.print(f"[dim]📈 量比数据加载中 (剩余{_pending_count}只，每轮补充{_VR_BATCH}只)[/dim]")
                    total_api_calls += round_api_calls
                    rate_per_hour = total_api_calls / (round_count * interval) * 3600 if round_count > 0 else 0
                    console.print(
                        f"[dim]下次刷新: {interval}秒后 | "
                        f"本轮请求: {round_api_calls}次 | "
                        f"累计: {total_api_calls}次/{round_count}轮 "
                        f"(≈{rate_per_hour:.0f}次/小时) "
                        f"(Ctrl+C 退出)[/dim]\n"
                    )

                # 保存当前轮数据作为下一轮的对比基准（仅个股）
                prev_quotes = {}
                for code in stock_codes:
                    qd = quotes_data.get(code, {})
                    if not qd:
                        continue
                    # 计算当前轮振幅，保存为 _amplitude 供下轮Δ使用
                    _h = qd.get("high", 0)
                    _l = qd.get("low", 0)
                    _pc = qd.get("pre_close", 0) or qd.get("yesterday_close", 0)
                    if not _pc:
                        _pc = qd.get("price", 0) - qd.get("change", 0) if qd.get("price") and qd.get("change") else 0
                    _amp = ((_h - _l) / _pc * 100) if _pc else 0

                    prev_quotes[code] = {
                        "price": qd.get("price", 0),
                        "volume": qd.get("volume", 0),
                        "change_percent": qd.get("change_percent", 0),
                        "name": qd.get("name", ""),
                        "turnover_rate": qd.get("turnover_rate", 0),
                        "_amplitude": _amp,
                    }

            except Exception as e:
                console.print(f"[yellow]⚠️ 数据获取异常: {e}[/yellow]")

            time_mod.sleep(interval)

    except KeyboardInterrupt:
        console.print(f"\n[cyan]👋 已退出看盘模式 (共刷新 {round_count} 轮)[/cyan]")

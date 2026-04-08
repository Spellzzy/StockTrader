"""个股详情页 — 点击/选中股票后弹出全屏详情

功能:
    1. 顶部：股票基本行情信息（实时价格/涨跌/最高最低/成交量）
    2. 中部：ASCII K线图 + 分时走势图（Tab 切换）
    3. 底部：公司简况 / 资金流向
    4. 快捷键: ESC 返回, 数字键切换 K 线周期
"""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static, TabbedContent, TabPane, RichLog
from textual.binding import Binding

from rich.text import Text
from rich.table import Table


class StockDetailScreen(Screen):
    """个股详情全屏页"""

    BINDINGS = [
        Binding("escape", "go_back", "返回", show=True),
        Binding("r", "refresh_detail", "刷新", show=True),
        Binding("1", "period_day", "日K"),
        Binding("2", "period_week", "周K"),
        Binding("3", "period_month", "月K"),
        Binding("4", "period_m60", "60分K"),
        Binding("5", "period_m30", "30分K"),
    ]

    CSS = """
    StockDetailScreen {
        layout: vertical;
    }

    #detail-header {
        dock: top;
        height: 1;
        background: $primary;
        color: $text;
        text-style: bold;
        padding: 0 2;
    }

    #detail-quote-bar {
        height: 3;
        padding: 0 2;
        background: $surface-darken-1;
    }

    #detail-main {
        height: 1fr;
    }

    #chart-area {
        height: 1fr;
        padding: 0 1;
    }

    #chart-display {
        height: 1fr;
    }

    #detail-bottom {
        height: 10;
        min-height: 6;
        max-height: 14;
        border-top: solid $primary-lighten-2;
    }

    #detail-footer {
        dock: bottom;
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
    }
    """

    def __init__(self, stock_code: str, stock_name: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self._code = stock_code
        self._name = stock_name
        self._quote: dict = {}
        self._current_period = "day"

    def compose(self) -> ComposeResult:
        yield Static(f" 📈 {self._name or self._code} 详情", id="detail-header")
        yield Static("加载中...", id="detail-quote-bar")

        with Vertical(id="detail-main"):
            with Vertical(id="chart-area"):
                yield Static("", id="chart-period-label")
                yield RichLog(id="chart-display", markup=True, wrap=False)

            with Vertical(id="detail-bottom"):
                with TabbedContent():
                    with TabPane("📋 公司概况", id="tab-profile"):
                        yield RichLog(id="profile-log", markup=True, wrap=True)
                    with TabPane("💰 资金流向", id="tab-fund"):
                        yield RichLog(id="fund-log", markup=True, wrap=True)

        yield Static(
            " [Esc]返回 [R]刷新 [1]日K [2]周K [3]月K [4]60分 [5]30分",
            id="detail-footer",
        )

    def on_mount(self) -> None:
        """加载数据"""
        self.call_after_refresh(self._load_all)

    async def _load_all(self) -> None:
        """加载所有数据"""
        await self._load_quote()
        await self._load_chart()
        await self._load_profile()
        await self._load_fund_flow()

    # ==================== 行情数据 ====================

    async def _load_quote(self) -> None:
        """加载实时行情"""
        try:
            services = self.app.services
            data = await services.run_sync(services.market.get_quote, self._code)
            self._quote = data.get(self._code, {})
            self._render_quote_bar()
        except Exception as e:
            bar = self.query_one("#detail-quote-bar", Static)
            bar.update(f"[red]行情加载失败: {e}[/red]")

    def _render_quote_bar(self) -> None:
        """渲染顶部行情摘要"""
        q = self._quote
        if not q:
            return

        name = q.get("name", self._name) or self._code
        price = q.get("price", 0)
        change = q.get("change", 0)
        change_pct = q.get("change_percent", 0)
        high = q.get("high", 0)
        low = q.get("low", 0)
        opn = q.get("open", 0)
        volume = q.get("volume", 0)
        turnover = q.get("turnover", 0)

        # 更新标题
        header = self.query_one("#detail-header", Static)
        header.update(f" 📈 {name} ({self._code})")

        # 涨跌颜色
        if change_pct > 0:
            color = "red"
            sign = "+"
        elif change_pct < 0:
            color = "green"
            sign = ""
        else:
            color = "white"
            sign = ""

        bar = Text()
        bar.append(f"  ¥{price:.2f} ", style=f"bold {color}")
        bar.append(f"{sign}{change:.2f} ({sign}{change_pct:.2f}%) ", style=color)
        bar.append("  │  ", style="dim")
        bar.append(f"开:{opn:.2f}", style="")
        bar.append(f"  高:{high:.2f}", style="red" if high > opn else "")
        bar.append(f"  低:{low:.2f}", style="green" if low < opn else "")
        bar.append("  │  ", style="dim")

        # 成交量格式化
        if volume >= 1_0000_0000:
            vol_str = f"{volume / 1_0000_0000:.2f}亿"
        elif volume >= 1_0000:
            vol_str = f"{volume / 1_0000:.1f}万"
        else:
            vol_str = f"{volume:.0f}"
        bar.append(f"量:{vol_str}", style="")
        bar.append(f"  换手:{turnover:.2f}%", style="")

        quote_bar = self.query_one("#detail-quote-bar", Static)
        quote_bar.update(bar)

    # ==================== K 线图 ====================

    async def _load_chart(self) -> None:
        """加载并绘制 K 线图"""
        period_label = self.query_one("#chart-period-label", Static)
        period_names = {
            "day": "日K", "week": "周K", "month": "月K",
            "m60": "60分钟", "m30": "30分钟", "m15": "15分钟",
        }
        period_label.update(
            f" 📊 {period_names.get(self._current_period, self._current_period)} 走势 "
            f"({self._code})"
        )

        chart_log = self.query_one("#chart-display", RichLog)
        chart_log.clear()
        chart_log.write(Text("加载K线数据...", style="dim"))

        try:
            services = self.app.services
            df = await services.run_sync(
                services.market.get_kline_df,
                self._code,
                period=self._current_period,
                count=60,
                adjust="qfq",
            )

            chart_log.clear()

            if df.empty:
                chart_log.write(Text("暂无K线数据", style="dim"))
                return

            self._render_ascii_kline(df, chart_log)

        except Exception as e:
            chart_log.clear()
            chart_log.write(Text(f"K线加载失败: {e}", style="red"))

    def _render_ascii_kline(self, df, chart_log: RichLog) -> None:
        """绘制 ASCII K 线图

        使用 Unicode 字符绘制简化版 K 线:
            █ 阳线(红)  █ 阴线(绿)
            │ 上下影线
        """
        if df.empty:
            return

        # 获取价格范围
        all_highs = df["high"].tolist()
        all_lows = df["low"].tolist()
        all_closes = df["close"].tolist()
        all_opens = df["open"].tolist()
        dates = df["date"].tolist()

        price_max = max(all_highs)
        price_min = min(all_lows)
        price_range = price_max - price_min

        if price_range <= 0:
            chart_log.write(Text("价格无变化", style="dim"))
            return

        # 图表高度（行数）
        chart_height = 20
        # 取最后 N 根K线（适配终端宽度）
        max_bars = min(len(df), 50)
        df_tail = df.tail(max_bars)

        # 绘制 K 线图
        # 每行代表一个价格区间
        rows: list[Text] = []

        for row_idx in range(chart_height):
            # 当前行对应的价格范围（从上到下，高→低）
            row_price_top = price_max - (row_idx / chart_height) * price_range
            row_price_bot = price_max - ((row_idx + 1) / chart_height) * price_range

            line = Text()
            # 左侧价格标签
            if row_idx == 0:
                line.append(f"{price_max:>8.2f} │", style="dim")
            elif row_idx == chart_height - 1:
                line.append(f"{price_min:>8.2f} │", style="dim")
            elif row_idx == chart_height // 2:
                mid_price = (price_max + price_min) / 2
                line.append(f"{mid_price:>8.2f} │", style="dim")
            else:
                line.append("         │", style="dim")

            # 每根K线
            for _, kline_row in df_tail.iterrows():
                o = kline_row["open"]
                c = kline_row["close"]
                h = kline_row["high"]
                l = kline_row["low"]

                body_top = max(o, c)
                body_bot = min(o, c)
                is_up = c >= o  # 阳线

                color = "red" if is_up else "green"

                # 判断当前行应该画什么
                if row_price_bot <= h and row_price_top >= l:
                    # 在影线范围内
                    if row_price_bot <= body_top and row_price_top >= body_bot:
                        # 在实体范围内
                        line.append("█", style=color)
                    else:
                        # 只有影线
                        line.append("│", style=color)
                else:
                    line.append(" ")

            rows.append(line)

        for row in rows:
            chart_log.write(row)

        # 底部日期标签
        dates_tail = df_tail["date"].tolist()
        date_line = Text()
        date_line.append("         └", style="dim")
        for i, d in enumerate(dates_tail):
            if i % (max(1, len(dates_tail) // 6)) == 0:
                date_str = str(d)[:10] if hasattr(d, 'strftime') else str(d)[:10]
                # 简化日期为 MM-DD
                if len(date_str) >= 10:
                    date_line.append(date_str[5:10], style="dim")
                else:
                    date_line.append(date_str[-5:], style="dim")
            else:
                date_line.append(" ")
        chart_log.write(date_line)

        # 统计摘要
        last_close = all_closes[-1]
        first_close = all_closes[0] if all_closes else last_close
        total_change = ((last_close - first_close) / first_close * 100) if first_close else 0
        change_color = "red" if total_change > 0 else "green" if total_change < 0 else "white"
        sign = "+" if total_change > 0 else ""

        summary = Text()
        summary.append(f"\n  区间: {str(dates_tail[0])[:10]} ~ {str(dates_tail[-1])[:10]}", style="dim")
        summary.append(f"  |  最高: {price_max:.2f}", style="red")
        summary.append(f"  最低: {price_min:.2f}", style="green")
        summary.append(f"  |  区间涨幅: {sign}{total_change:.2f}%", style=change_color)
        chart_log.write(summary)

    # ==================== 公司概况 ====================

    async def _load_profile(self) -> None:
        """加载公司概况"""
        log = self.query_one("#profile-log", RichLog)
        log.clear()
        log.write(Text("加载中...", style="dim"))

        try:
            services = self.app.services
            data = await services.run_sync(services.market.get_profile, self._code)

            log.clear()

            if not data or "raw_output" in data:
                log.write(Text("暂无公司资料", style="dim"))
                return

            # 解析 profile 数据
            profile = data.get("data", data)
            if isinstance(profile, dict):
                # 逐字段展示
                fields = [
                    ("名称", "name"),
                    ("行业", "industry"),
                    ("板块", "sector"),
                    ("市值", "market_cap"),
                    ("流通市值", "float_cap"),
                    ("PE(TTM)", "pe_ttm"),
                    ("PB", "pb"),
                    ("总股本", "total_shares"),
                    ("流通股本", "float_shares"),
                    ("上市日期", "list_date"),
                    ("主营业务", "business"),
                ]
                for label, key in fields:
                    value = profile.get(key)
                    if value is not None and str(value).strip():
                        line = Text()
                        line.append(f"  {label}: ", style="bold cyan")
                        line.append(str(value))
                        log.write(line)
            else:
                log.write(Text(str(data)[:500]))

        except Exception as e:
            log.clear()
            log.write(Text(f"加载失败: {e}", style="red"))

    # ==================== 资金流向 ====================

    async def _load_fund_flow(self) -> None:
        """加载资金流向"""
        log = self.query_one("#fund-log", RichLog)
        log.clear()
        log.write(Text("加载中...", style="dim"))

        try:
            services = self.app.services
            data = await services.run_sync(
                services.market.get_fund_flow, self._code, days=10
            )

            log.clear()

            if not data or "raw_output" in data:
                log.write(Text("暂无资金流向数据", style="dim"))
                return

            # 尝试提取资金流向数据
            flow_data = data.get("data", data)
            if isinstance(flow_data, list):
                header = Text()
                header.append("  日期       主力净流入    超大单净流入   大单净流入    中单净流入    小单净流入", style="bold")
                log.write(header)

                for item in flow_data[:10]:
                    if isinstance(item, dict):
                        date = str(item.get("date", ""))[:10]
                        main_flow = item.get("main_flow", item.get("main_net", 0))
                        line = Text()
                        line.append(f"  {date} ", style="dim")

                        # 格式化金额
                        for key in ["main_flow", "super_large_flow", "large_flow", "mid_flow", "small_flow"]:
                            val = item.get(key, item.get(key.replace("_flow", "_net"), 0))
                            if isinstance(val, (int, float)):
                                if val >= 1_0000_0000:
                                    val_str = f"{val / 1_0000_0000:>7.2f}亿"
                                elif val >= 1_0000:
                                    val_str = f"{val / 1_0000:>7.1f}万"
                                elif val <= -1_0000_0000:
                                    val_str = f"{val / 1_0000_0000:>7.2f}亿"
                                elif val <= -1_0000:
                                    val_str = f"{val / 1_0000:>7.1f}万"
                                else:
                                    val_str = f"{val:>9.0f}"
                                color = "red" if val > 0 else "green" if val < 0 else "dim"
                                line.append(f" {val_str}", style=color)
                            else:
                                line.append(f" {'--':>9s}")
                        log.write(line)
            elif isinstance(flow_data, dict):
                # 单条数据
                for key, val in flow_data.items():
                    line = Text()
                    line.append(f"  {key}: ", style="bold cyan")
                    line.append(str(val))
                    log.write(line)
            else:
                log.write(Text(str(data)[:500]))

        except Exception as e:
            log.clear()
            log.write(Text(f"加载失败: {e}", style="red"))

    # ==================== K 线周期切换 ====================

    async def action_period_day(self) -> None:
        self._current_period = "day"
        await self._load_chart()

    async def action_period_week(self) -> None:
        self._current_period = "week"
        await self._load_chart()

    async def action_period_month(self) -> None:
        self._current_period = "month"
        await self._load_chart()

    async def action_period_m60(self) -> None:
        self._current_period = "m60"
        await self._load_chart()

    async def action_period_m30(self) -> None:
        self._current_period = "m30"
        await self._load_chart()

    # ==================== 导航 ====================

    def action_go_back(self) -> None:
        """返回主屏幕"""
        self.app.pop_screen()

    async def action_refresh_detail(self) -> None:
        """刷新所有数据"""
        await self._load_all()

"""可视化图表模块 - matplotlib + plotly"""

import os
from datetime import datetime
from typing import Optional
from pathlib import Path

import pandas as pd
import numpy as np

from app.config import get_config


class ChartService:
    """图表可视化服务"""

    def __init__(self):
        config = get_config()
        self.save_dir = config["visualization"]["save_dir"]
        self.theme = config["visualization"]["theme"]
        os.makedirs(self.save_dir, exist_ok=True)

    def _apply_theme(self, fig, ax):
        """应用暗色主题"""
        if self.theme == "dark":
            fig.patch.set_facecolor("#1e1e2f")
            ax.set_facecolor("#1e1e2f")
            ax.tick_params(colors="#cccccc")
            ax.xaxis.label.set_color("#cccccc")
            ax.yaxis.label.set_color("#cccccc")
            ax.title.set_color("#ffffff")
            for spine in ax.spines.values():
                spine.set_color("#444444")

    def plot_pnl_curve(
        self,
        daily_pnl: pd.DataFrame,
        title: str = "累计收益曲线",
        save: bool = True,
    ) -> str:
        """绘制收益曲线

        Args:
            daily_pnl: 包含 date, daily_pnl, cumulative_pnl 列的 DataFrame
            title: 图表标题
            save: 是否保存到文件

        Returns:
            保存的文件路径
        """
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates

        plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
        plt.rcParams["axes.unicode_minus"] = False

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), height_ratios=[3, 1])
        self._apply_theme(fig, ax1)
        self._apply_theme(fig, ax2)

        dates = daily_pnl["date"]
        cum_pnl = daily_pnl["cumulative_pnl"]

        # 上图：累计收益曲线
        colors = ["#ff4444" if v < 0 else "#00c853" for v in cum_pnl]
        ax1.fill_between(dates, cum_pnl, 0, where=cum_pnl >= 0, alpha=0.3, color="#00c853")
        ax1.fill_between(dates, cum_pnl, 0, where=cum_pnl < 0, alpha=0.3, color="#ff4444")
        ax1.plot(dates, cum_pnl, color="#2196F3", linewidth=2)
        ax1.axhline(y=0, color="#888888", linestyle="--", linewidth=0.8)
        ax1.set_title(title, fontsize=16, fontweight="bold")
        ax1.set_ylabel("累计盈亏 (元)", fontsize=12)
        ax1.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
        ax1.grid(True, alpha=0.2)

        # 下图：每日盈亏柱状图
        daily = daily_pnl["daily_pnl"]
        bar_colors = ["#00c853" if v >= 0 else "#ff4444" for v in daily]
        ax2.bar(dates, daily, color=bar_colors, width=1.0, alpha=0.8)
        ax2.axhline(y=0, color="#888888", linestyle="--", linewidth=0.8)
        ax2.set_ylabel("每日盈亏", fontsize=10)
        ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
        ax2.grid(True, alpha=0.2)

        plt.tight_layout()

        filepath = ""
        if save:
            filepath = os.path.join(self.save_dir, "pnl_curve.png")
            fig.savefig(filepath, dpi=150, bbox_inches="tight")

        plt.show()
        plt.close(fig)
        return filepath

    def plot_kline(
        self,
        kline_df: pd.DataFrame,
        title: str = "K线图",
        show_volume: bool = True,
        show_ma: bool = True,
        show_macd: bool = True,
        ma_periods: list | None = None,
        save: bool = True,
    ) -> str:
        """绘制专业K线图（含均线 + MACD）

        Args:
            kline_df: 包含 date, open, close, high, low, volume 列的 DataFrame
            title: 图表标题
            show_volume: 是否显示成交量
            show_ma: 是否显示均线
            show_macd: 是否显示 MACD 指标
            ma_periods: 均线周期列表，默认 [5, 10, 20, 60]
            save: 是否保存

        Returns:
            保存的文件路径
        """
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        from matplotlib.patches import Rectangle

        plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
        plt.rcParams["axes.unicode_minus"] = False

        if ma_periods is None:
            ma_periods = [5, 10, 20, 60]

        df = kline_df.copy()
        x = list(range(len(df)))

        # ── 计算均线 ──
        ma_colors = {5: "#FFD700", 10: "#FF69B4", 20: "#00BFFF", 60: "#FF8C00"}
        ma_data = {}
        if show_ma:
            for p in ma_periods:
                if len(df) >= p:
                    ma_data[p] = df["close"].rolling(window=p).mean()

        # ── 计算 MACD ──
        macd_line, signal_line, macd_hist = None, None, None
        if show_macd and len(df) >= 26:
            ema12 = df["close"].ewm(span=12, adjust=False).mean()
            ema26 = df["close"].ewm(span=26, adjust=False).mean()
            macd_line = ema12 - ema26
            signal_line = macd_line.ewm(span=9, adjust=False).mean()
            macd_hist = (macd_line - signal_line) * 2  # 柱状图 (×2 放大)

        # ── 布局 ──
        num_panels = 1
        ratios = [4]
        if show_volume:
            num_panels += 1
            ratios.append(1)
        if show_macd and macd_line is not None:
            num_panels += 1
            ratios.append(1.2)

        fig, axes = plt.subplots(
            num_panels, 1,
            figsize=(16, 4 + num_panels * 2.5),
            height_ratios=ratios,
            sharex=True,
        )
        if num_panels == 1:
            axes = [axes]

        ax_main = axes[0]
        ax_idx = 1
        ax_vol = None
        ax_macd = None
        if show_volume:
            ax_vol = axes[ax_idx]
            ax_idx += 1
        if show_macd and macd_line is not None:
            ax_macd = axes[ax_idx]

        for ax in axes:
            self._apply_theme(fig, ax)

        # ── 绘制K线 ──
        for i_row, row in df.iterrows():
            idx = list(df.index).index(i_row)
            o, c, h, l = row["open"], row["close"], row["high"], row["low"]
            # 中国市场：红涨绿跌
            color = "#00c853" if c >= o else "#ff4444"
            if abs(c - o) < 1e-6:
                color = "#999999"

            # 影线
            ax_main.plot([idx, idx], [l, h], color=color, linewidth=0.8)

            # 实体
            body_bottom = min(o, c)
            body_height = abs(c - o) or (h - l) * 0.01
            rect = Rectangle(
                (idx - 0.35, body_bottom), 0.7, body_height,
                facecolor=color, edgecolor=color, linewidth=0.5,
            )
            ax_main.add_patch(rect)

        # ── 绘制均线 ──
        if show_ma and ma_data:
            for p, ma_values in ma_data.items():
                valid = ma_values.dropna()
                if valid.empty:
                    continue
                start_idx = valid.index[0]
                ma_x = [list(df.index).index(i) for i in valid.index]
                ax_main.plot(
                    ma_x, valid.values,
                    color=ma_colors.get(p, "#AAAAAA"),
                    linewidth=1.2,
                    label=f"MA{p}",
                    alpha=0.85,
                )
            ax_main.legend(
                loc="upper left", fontsize=9, framealpha=0.7,
                facecolor="#2a2a3d" if self.theme == "dark" else "white",
                labelcolor="#cccccc" if self.theme == "dark" else "#333333",
            )

        ax_main.set_title(title, fontsize=16, fontweight="bold", pad=12)
        ax_main.set_ylabel("价格", fontsize=12)
        ax_main.grid(True, alpha=0.15)
        ax_main.set_xlim(-1, len(df))

        # 标注最高/最低价
        if len(df) > 0:
            hi_idx = df["high"].idxmax()
            lo_idx = df["low"].idxmin()
            hi_x = list(df.index).index(hi_idx)
            lo_x = list(df.index).index(lo_idx)
            ax_main.annotate(
                f"↑ {df.loc[hi_idx, 'high']:.2f}",
                xy=(hi_x, df.loc[hi_idx, "high"]),
                fontsize=8, color="#00c853", fontweight="bold",
                ha="center", va="bottom",
            )
            ax_main.annotate(
                f"↓ {df.loc[lo_idx, 'low']:.2f}",
                xy=(lo_x, df.loc[lo_idx, "low"]),
                fontsize=8, color="#ff4444", fontweight="bold",
                ha="center", va="top",
            )

        # ── 成交量 ──
        if ax_vol is not None:
            vol = df["volume"].values
            vol_colors = [
                "#00c853" if df.iloc[i]["close"] >= df.iloc[i]["open"] else "#ff4444"
                for i in range(len(df))
            ]
            ax_vol.bar(x, vol, color=vol_colors, alpha=0.7, width=0.7)
            ax_vol.set_ylabel("成交量", fontsize=10)
            ax_vol.grid(True, alpha=0.15)
            # 成交量均线
            if len(df) >= 5:
                vol_ma5 = pd.Series(vol).rolling(5).mean()
                ax_vol.plot(x, vol_ma5, color="#FFD700", linewidth=0.8, alpha=0.8, label="VOL MA5")
            if len(df) >= 10:
                vol_ma10 = pd.Series(vol).rolling(10).mean()
                ax_vol.plot(x, vol_ma10, color="#FF69B4", linewidth=0.8, alpha=0.8, label="VOL MA10")

        # ── MACD ──
        if ax_macd is not None and macd_hist is not None:
            # MACD 柱状图
            hist_colors = ["#00c853" if v >= 0 else "#ff4444" for v in macd_hist]
            ax_macd.bar(x, macd_hist, color=hist_colors, alpha=0.6, width=0.7)
            # DIF 和 DEA 线
            ax_macd.plot(x, macd_line, color="#2196F3", linewidth=1.0, label="DIF")
            ax_macd.plot(x, signal_line, color="#FF9800", linewidth=1.0, label="DEA")
            ax_macd.axhline(y=0, color="#888888", linestyle="--", linewidth=0.5)
            ax_macd.set_ylabel("MACD", fontsize=10)
            ax_macd.grid(True, alpha=0.15)
            ax_macd.legend(
                loc="upper left", fontsize=8, framealpha=0.7,
                facecolor="#2a2a3d" if self.theme == "dark" else "white",
                labelcolor="#cccccc" if self.theme == "dark" else "#333333",
            )

        # ── X 轴标签 ──
        step = max(1, len(df) // 12)
        tick_positions = list(range(0, len(df), step))
        tick_labels = [
            df.iloc[i]["date"].strftime("%m-%d") if hasattr(df.iloc[i]["date"], "strftime")
            else str(df.iloc[i]["date"])[:5]
            for i in tick_positions
        ]
        axes[-1].set_xticks(tick_positions)
        axes[-1].set_xticklabels(tick_labels, rotation=45, fontsize=9)

        plt.tight_layout()
        plt.subplots_adjust(hspace=0.08)

        filepath = ""
        if save:
            code_name = title.replace(" ", "_")
            filepath = os.path.join(self.save_dir, f"kline_{code_name}.png")
            fig.savefig(filepath, dpi=150, bbox_inches="tight")

        plt.show()
        plt.close(fig)
        return filepath

    def plot_portfolio_pie(
        self,
        holdings: list[dict],
        title: str = "持仓分布",
        save: bool = True,
    ) -> str:
        """绘制持仓分布饼图

        Args:
            holdings: 持仓列表 [{stock_code, stock_name, market_value}, ...]
            title: 标题
            save: 是否保存

        Returns:
            文件路径
        """
        import matplotlib.pyplot as plt

        plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
        plt.rcParams["axes.unicode_minus"] = False

        if not holdings:
            return ""

        fig, ax = plt.subplots(1, 1, figsize=(10, 8))
        self._apply_theme(fig, ax)

        labels = [
            f"{h.get('stock_name') or h['stock_code']}"
            for h in holdings
        ]
        sizes = [h.get("market_value", 0) for h in holdings]
        total = sum(sizes) or 1

        # 颜色方案
        colors = [
            "#2196F3", "#FF9800", "#4CAF50", "#E91E63", "#9C27B0",
            "#00BCD4", "#FF5722", "#795548", "#607D8B", "#CDDC39",
        ]

        wedges, texts, autotexts = ax.pie(
            sizes,
            labels=labels,
            autopct=lambda pct: f"{pct:.1f}%\n({pct/100*total:,.0f}元)" if pct > 3 else "",
            colors=colors[: len(labels)],
            startangle=90,
            textprops={"fontsize": 10, "color": "#ffffff" if self.theme == "dark" else "#333333"},
        )

        ax.set_title(title, fontsize=16, fontweight="bold")
        plt.tight_layout()

        filepath = ""
        if save:
            filepath = os.path.join(self.save_dir, "portfolio_pie.png")
            fig.savefig(filepath, dpi=150, bbox_inches="tight")

        plt.show()
        plt.close(fig)
        return filepath

    def plot_win_loss_bar(
        self,
        summary: dict,
        title: str = "胜负统计",
        save: bool = True,
    ) -> str:
        """绘制胜负统计图

        Args:
            summary: AnalysisService.summary() 的返回值
            save: 是否保存

        Returns:
            文件路径
        """
        import matplotlib.pyplot as plt

        plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
        plt.rcParams["axes.unicode_minus"] = False

        fig, axes = plt.subplots(1, 3, figsize=(15, 5))
        self._apply_theme(fig, axes[0])
        self._apply_theme(fig, axes[1])
        self._apply_theme(fig, axes[2])

        # 1. 胜率饼图
        win = summary.get("win_count", 0)
        loss = summary.get("loss_count", 0)
        even = summary.get("even_count", 0)
        if win + loss + even > 0:
            axes[0].pie(
                [win, loss, even],
                labels=["盈利", "亏损", "持平"],
                colors=["#00c853", "#ff4444", "#888888"],
                autopct="%1.1f%%",
                textprops={"color": "#ffffff" if self.theme == "dark" else "#333333"},
            )
        axes[0].set_title(f"胜率: {summary.get('win_rate', 0)}%", fontsize=14)

        # 2. 盈亏对比
        tp = summary.get("total_profit", 0)
        tl = summary.get("total_loss", 0)
        bar_colors = ["#00c853", "#ff4444"]
        axes[1].bar(["总盈利", "总亏损"], [tp, tl], color=bar_colors, width=0.5)
        axes[1].set_title("盈亏对比", fontsize=14)
        axes[1].set_ylabel("金额 (元)")
        axes[1].grid(True, alpha=0.2)

        # 3. 平均盈亏
        ap = summary.get("avg_profit", 0)
        al = summary.get("avg_loss", 0)
        axes[2].bar(["平均盈利", "平均亏损"], [ap, al], color=bar_colors, width=0.5)
        ratio = summary.get("profit_loss_ratio", 0)
        axes[2].set_title(f"盈亏比: {ratio:.2f}", fontsize=14)
        axes[2].set_ylabel("金额 (元)")
        axes[2].grid(True, alpha=0.2)

        plt.tight_layout()

        filepath = ""
        if save:
            filepath = os.path.join(self.save_dir, "win_loss.png")
            fig.savefig(filepath, dpi=150, bbox_inches="tight")

        plt.show()
        plt.close(fig)
        return filepath

    def plot_monthly_pnl(
        self,
        monthly_df: pd.DataFrame,
        title: str = "月度盈亏",
        save: bool = True,
    ) -> str:
        """绘制月度盈亏柱状图

        Args:
            monthly_df: AnalysisService.monthly_summary() 的返回值
            save: 是否保存

        Returns:
            文件路径
        """
        import matplotlib.pyplot as plt

        plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
        plt.rcParams["axes.unicode_minus"] = False

        if monthly_df.empty:
            return ""

        fig, ax = plt.subplots(1, 1, figsize=(12, 6))
        self._apply_theme(fig, ax)

        months = monthly_df["month"].values
        profits = monthly_df["total_profit"].values
        colors = ["#00c853" if p >= 0 else "#ff4444" for p in profits]

        ax.bar(range(len(months)), profits, color=colors, width=0.6, alpha=0.85)
        ax.set_xticks(range(len(months)))
        ax.set_xticklabels(months, rotation=45)
        ax.axhline(y=0, color="#888888", linestyle="--", linewidth=0.8)
        ax.set_title(title, fontsize=16, fontweight="bold")
        ax.set_ylabel("盈亏 (元)", fontsize=12)
        ax.grid(True, alpha=0.2, axis="y")

        # 标注数值
        for i, v in enumerate(profits):
            ax.text(
                i, v + (max(abs(profits)) * 0.02 if v >= 0 else -max(abs(profits)) * 0.05),
                f"{v:,.0f}",
                ha="center", fontsize=9,
                color="#ffffff" if self.theme == "dark" else "#333333",
            )

        plt.tight_layout()

        filepath = ""
        if save:
            filepath = os.path.join(self.save_dir, "monthly_pnl.png")
            fig.savefig(filepath, dpi=150, bbox_inches="tight")

        plt.show()
        plt.close(fig)
        return filepath

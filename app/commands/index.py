"""命令索引 — stock-ai commands / cmd

`--help` 里 12 个子命令组都是 hidden，用户根本不知道 `ai` / `paper` / `backtest`
这些入口存在。这里把顶层命令、子命令组、缩写一次列全。
"""

from __future__ import annotations

from app.commands import console, Table, Panel, box

# 顶层命令按功能归类（只列代表命令，缩写一并给出）
CATEGORIES = [
    ("交易记录", [
        ("buy / b", "录入买入"), ("sell / s", "录入卖出"),
        ("trades / t", "交易列表"), ("del-trade / dt", "删除交易"),
    ]),
    ("持仓与自选", [
        ("show / w", "当前持仓"), ("rebuild / rb", "重建持仓"),
        ("stars / ss", "自选股"), ("star / sa", "加自选"), ("unstar / sd", "移出自选"),
    ]),
    ("行情", [
        ("q", "实时行情（空格/逗号分隔多只）"), ("k", "K线（-g 出图）"),
        ("f", "财务"), ("pf", "公司简况"), ("fd", "资金流向"),
        ("n", "新闻"), ("sc", "搜索"), ("chip", "筹码分布"),
    ]),
    ("统计与图表", [
        ("sm", "统计摘要"), ("mo", "月度盈亏"), ("rk", "盈亏排名"), ("dd", "最大回撤"),
        ("c-pnl / c-k / c-pf / c-wl / c-mo", "各类图表"),
    ]),
    ("策略实验室", [
        ("signal-report / sr", "策略信号质量（--all 对比 7 策略）"),
        ("optimize / opt", "参数网格 + 滚动窗口验证"),
    ]),
    ("AI", [
        ("p", "AI 预测"), ("a", "LLM 深度分析"), ("train-ai", "训练模型"),
        ("scan", "批量扫描"), ("test-llm", "测试 LLM"),
        ("target-high", "今日目标最高价（统计区间）"),
    ]),
    ("回测与选股", [
        ("bt", "单标的回测"), ("bt-pf", "组合回测"), ("bt-compare", "多策略对比"),
        ("bt-list", "策略列表"), ("sn", "选股扫描"), ("sn-pool-build", "构建全A代码池"),
        ("scan-market", "全市场摘选（预筛→条件→落库）"),
        ("scan-history", "全市场摘选历史记录"),
    ]),
    ("预警与看盘", [
        ("al-a / al-l / al-d / al-t", "预警增删改查"),
        ("al-c / al-h / al-tp", "检测 / 历史 / 条件类型"),
        ("wa", "实时看盘"), ("d", "TUI Dashboard"),
    ]),
    ("推送与日报", [
        ("nt / nl", "推送测试 / 渠道列表"),
        ("dg / dg-p / dg-v", "智能日报 / 推送 / 预览"),
    ]),
    ("报告与其他", [
        ("web", "启动本地 Web 界面（双击 启动.bat 亦可）"),
        ("report / rp", "HTML 可视化报告"), ("commands / cmd", "本索引"),
        ("show --wide / q --wide", "显示全部表格列"),
        ("notify-list", "推送渠道状态"), ("init", "初始化数据库"),
    ]),
]

# 子命令组：名称 → (用途, 示例)
GROUPS = {
    "trade": ("交易记录增删改", "stock-ai trade list"),
    "portfolio": ("持仓管理", "stock-ai portfolio show"),
    "watchlist": ("自选股", "stock-ai watchlist list"),
    "market": ("行情数据", "stock-ai market quote 600519"),
    "analysis": ("统计分析", "stock-ai analysis summary"),
    "chart": ("图表绘制", "stock-ai chart kline 600519"),
    "ai": ("AI 预测 / 训练", "stock-ai ai predict 600519"),
    "alert": ("预警规则", "stock-ai alert list"),
    "backtest": ("策略回测", "stock-ai backtest run 600519"),
    "notify": ("消息推送", "stock-ai notify test"),
    "digest": ("智能日报", "stock-ai digest preview"),
    "paper": ("模拟盘", "stock-ai paper show"),
    "order": ("订单编排（冻结）", "需 features.order_enabled=true"),
}


def _group_commands(group) -> list[str]:
    """从 Typer 子应用里取出已注册的子命令名"""
    typer_app = getattr(group, "typer_instance", None)
    if typer_app is None:
        return []
    return sorted(
        cmd.name or (cmd.callback.__name__ if cmd.callback else "")
        for cmd in getattr(typer_app, "registered_commands", [])
    )


def collect_index() -> dict:
    """收集索引数据（纯函数式，方便测试）"""
    from app.cli import app as cli_app

    groups = []
    for group in cli_app.registered_groups:
        name = group.name or ""
        desc, example = GROUPS.get(name, ("", f"stock-ai {name} --help"))
        groups.append({
            "name": name,
            "description": desc,
            "commands": _group_commands(group),
            "example": example,
        })

    top_level = sorted(
        cmd.name or "" for cmd in cli_app.registered_commands
    )
    return {"groups": groups, "top_level": top_level, "categories": CATEGORIES}


def do_commands(group: str = ""):
    """打印命令索引

    Args:
        group: 只看某个子命令组（如 ai / paper）
    """
    data = collect_index()
    groups = data["groups"]
    if group:
        groups = [g for g in groups if g["name"] == group]
        if not groups:
            console.print(f"[red]❌ 没有这个命令组: {group}[/red]")
            console.print(f"[dim]可用: {', '.join(g['name'] for g in data['groups'])}[/dim]")
            return

    table = Table(
        title="📚 子命令组（这些在 --help 里是隐藏的）",
        box=box.ROUNDED, header_style="bold cyan", show_lines=True,
    )
    table.add_column("组", style="cyan", no_wrap=True)
    table.add_column("用途")
    table.add_column("子命令")
    table.add_column("示例", style="dim")

    for g in groups:
        cmds = ", ".join(g["commands"][:8]) or "-"
        if len(g["commands"]) > 8:
            cmds += f", …(+{len(g['commands']) - 8})"
        table.add_row(g["name"], g["description"], cmds, g["example"])
    console.print(table)

    if group:
        return

    console.print(
        Panel(
            f"顶层命令 {len(data['top_level'])} 个（含缩写别名）；"
            f"子命令组 {len(data['groups'])} 个。\n"
            "[dim]小贴士: q 支持空格分隔多只股票；show --wide / q --wide 显示全部列；\n"
            "report 生成单文件 HTML 报告；订单编排当前冻结不开放。[/dim]",
            title="💡 使用提示",
            border_style="cyan",
        )
    )

    for title, items in data["categories"]:
        lines = []
        for name, desc in items:
            lines.append(f"  [cyan]{name:<36}[/cyan] [dim]{desc}[/dim]")
        console.print(f"\n[bold]{title}[/bold]\n" + "\n".join(lines))

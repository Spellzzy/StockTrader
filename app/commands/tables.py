"""响应式表格：窄终端下优先保留关键列，避免代码/价格被挤成省略号

Rich 的 Table 在列总宽超过终端宽度时会自动压缩列，结果是
`sh00…` / `3599…` 这种没法读的输出。这里的做法是按 priority 裁剪列：
核心列（代码、名称、现价、涨跌幅）永远保留且宽度不被压到 min_width 以下，
次要列按优先级从低到高丢弃。`--wide` 可以强制显示全部列。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from rich import box
from rich.table import Table


@dataclass(frozen=True)
class Column:
    key: str                  # row dict 里的取值键
    title: str
    width: int
    priority: int = 5         # 数字越小越重要，空间不够时先丢大的
    justify: str = "right"
    min_width: int = 6        # 收缩下限


def _needed_width(columns: list[Column]) -> int:
    """Rich 圆角表格的近似开销：左右边框 2 + 每列 padding/分隔 3"""
    return sum(c.width for c in columns) + 2 + 3 * len(columns)


def select_columns(
    columns: list[Column],
    width: int = 120,
    wide: bool = False,
) -> list[Column]:
    """按终端宽度挑选并收缩列

    Args:
        columns: 全部列定义（按显示顺序）
        width: 终端宽度
        wide: True 直接返回全部列，不做裁剪
    """
    if wide or width <= 0:
        return list(columns)

    kept = list(columns)
    while len(kept) > 1 and _needed_width(kept) > width:
        # 丢优先级最低的；同优先级保留靠前的
        idx = max(range(len(kept)), key=lambda i: (kept[i].priority, i))
        kept.pop(idx)

    # 仍放不下时逐格收缩，但不低于每列自己的 min_width
    while _needed_width(kept) > width:
        candidates = [c for c in kept if c.width > c.min_width]
        if not candidates:
            break
        widest = max(candidates, key=lambda c: c.width)
        kept = [
            replace(c, width=c.width - 1) if c is widest else c
            for c in kept
        ]

    return kept


def render_table(
    columns: list[Column],
    rows: list[dict[str, Any]],
    *,
    title: str = "",
    width: int = 120,
    wide: bool = False,
    show_lines: bool = False,
    header_style: str = "bold cyan",
) -> Table:
    """构造一个按终端宽度裁剪过的 Rich 表格"""
    cols = select_columns(columns, width=width, wide=wide)

    needed = _needed_width(columns)
    if wide and needed > width:
        # 物理上放不下时明确告诉用户，而不是默默把内容压成省略号
        title = f"{title} [dim](全部列需终端 ≥ {needed} 列)[/dim]"

    table = Table(
        title=title,
        box=box.ROUNDED,
        show_lines=show_lines,
        header_style=header_style,
    )
    for col in cols:
        table.add_column(
            col.title,
            width=col.width,
            justify=col.justify,
            no_wrap=True,
            overflow="ellipsis",
        )

    for row in rows:
        table.add_row(*(str(row.get(col.key, "")) for col in cols))
    return table

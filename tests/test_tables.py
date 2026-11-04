"""响应式表格：窄终端保住关键列，不把内容压成省略号"""

from app.commands.tables import Column, _needed_width, render_table, select_columns

COLS = [
    Column("code", "代码", 10, priority=0, min_width=10),
    Column("name", "名称", 10, priority=1, min_width=8),
    Column("price", "现价", 10, priority=2, min_width=9),
    Column("chg", "涨跌幅", 10, priority=3, min_width=9),
    Column("change", "涨跌额", 10, priority=4, min_width=8),
    Column("volume", "成交量", 10, priority=5),
    Column("open", "今开", 10, priority=6),
    Column("high", "最高", 10, priority=7),
    Column("low", "最低", 10, priority=8),
    Column("pe", "市盈率", 8, priority=9),
]


def test_wide_terminal_keeps_most_columns():
    kept = select_columns(COLS, width=160)
    assert len(kept) == len(COLS)


def test_narrow_terminal_keeps_core_columns():
    kept = select_columns(COLS, width=80)
    keys = [c.key for c in kept]

    assert "code" in keys
    assert "name" in keys
    assert "price" in keys
    assert "chg" in keys
    assert len(kept) < len(COLS)
    assert "pe" not in keys and "high" not in keys


def test_core_columns_never_shrink_below_min_width():
    kept = select_columns(COLS, width=60)
    for col in kept:
        assert col.width >= col.min_width
        if col.priority <= 2:
            assert col.width >= 8


def test_needed_width_fits_terminal():
    for width in (60, 80, 100, 120, 160):
        kept = select_columns(COLS, width=width)
        assert _needed_width(kept) <= width or all(
            c.width == c.min_width for c in kept
        )


def test_wide_flag_keeps_all_columns():
    kept = select_columns(COLS, width=60, wide=True)
    assert len(kept) == len(COLS)


def test_render_table_only_uses_selected_keys():
    rows = [{"code": "sh600519", "name": "贵州茅台", "price": "1400.00",
             "chg": "+1.00%", "change": "+14.00", "volume": "2.8万",
             "open": "1390", "high": "1410", "low": "1380", "pe": "22.1"}]
    table = render_table(COLS, rows, title="行情", width=80)

    assert len(table.columns) == len(select_columns(COLS, width=80))
    assert table.row_count == 1
    # 关键列不能有省略号标记
    for col in table.columns:
        if col.header in ("代码", "名称", "现价"):
            assert col.width >= 8

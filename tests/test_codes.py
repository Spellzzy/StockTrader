"""股票代码规范化"""

import pytest

from app.models.stock import is_index_code, normalize_stock_code, normalize_stock_codes


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("600519", "sh600519"),      # 沪市主板
        ("688981", "sh688981"),      # 科创板
        ("512880", "sh512880"),      # 沪市 ETF
        ("000001", "sz000001"),      # 深市主板
        ("300750", "sz300750"),      # 创业板
        ("159915", "sz159915"),      # 深市 ETF
        ("sh600519", "sh600519"),    # 已有前缀
        ("SH600519", "sh600519"),    # 大写前缀统一小写
        (" 600519 ", "sh600519"),    # 首尾空白
        ("00700", "hk00700"),        # 5 位 → 港股
        ("AAPL", "usAAPL"),          # 纯字母 → 美股
        ("tsla", "usTSLA"),          # 小写美股
    ],
)
def test_normalize_stock_code(raw, expected):
    assert normalize_stock_code(raw) == expected


def test_normalize_stock_codes_batch():
    assert normalize_stock_codes("600519, 000001,00700") == "sh600519,sz000001,hk00700"


def test_normalize_stock_codes_ignores_empty_parts():
    assert normalize_stock_codes("600519,,000001,") == "sh600519,sz000001"


@pytest.mark.parametrize(
    "code, expected",
    [
        ("sh000001", True),    # 上证指数
        ("sh000300", True),    # 沪深300
        ("sz399001", True),    # 深证成指
        ("sz399006", True),    # 创业板指
        ("sz399101", True),    # 中证1000
        # 裸代码 000001 有歧义：按 normalize_stock_code 规则归属深市（平安银行），不算指数
        ("000001", False),
        ("sh600519", False),   # 贵州茅台
        ("sz000001", False),   # 平安银行（与上证指数同号，但前缀不同）
        ("sz300750", False),
        ("hk00700", False),
        ("usAAPL", False),
    ],
)
def test_is_index_code(code, expected):
    assert is_index_code(code) is expected

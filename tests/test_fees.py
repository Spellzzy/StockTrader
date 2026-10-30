"""统一费率模型"""

import pytest

from app.domain.fees import FeeModel


def test_defaults_match_current_a_share_rates():
    model = FeeModel()
    assert model.commission_rate == pytest.approx(0.0003)   # 万3
    assert model.min_commission == pytest.approx(5.0)       # 最低 5 元
    assert model.stamp_tax_rate == pytest.approx(0.001)     # 印花税千1


def test_commission_uses_floor_for_small_amount():
    assert FeeModel().commission(1000.0) == pytest.approx(5.0)


def test_commission_uses_rate_above_floor():
    assert FeeModel().commission(100_000.0) == pytest.approx(30.0)


def test_commission_is_zero_for_zero_amount():
    assert FeeModel().commission(0.0) == 0.0


def test_stamp_tax_charged_on_sell_only():
    model = FeeModel()
    assert model.tax(10_000.0, action="sell") == pytest.approx(10.0)
    assert model.tax(10_000.0, action="buy") == 0.0


def test_stamp_tax_not_charged_for_hk_and_us():
    model = FeeModel()
    assert model.tax(10_000.0, action="sell", market="HK") == 0.0
    assert model.tax(10_000.0, action="sell", market="US") == 0.0


def test_from_config_overrides_given_keys_only():
    model = FeeModel.from_config(
        {"fees": {"commission_rate": 0.00025, "min_commission": 1.0}}
    )
    assert model.commission_rate == pytest.approx(0.00025)
    assert model.min_commission == pytest.approx(1.0)
    assert model.stamp_tax_rate == pytest.approx(0.001)  # 未配置 → 默认


def test_from_config_without_fees_section_returns_defaults():
    assert FeeModel.from_config({}) == FeeModel()
    assert FeeModel.from_config(None) == FeeModel()

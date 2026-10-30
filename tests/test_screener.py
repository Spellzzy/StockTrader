"""选股条件聚合"""

import pytest

from app.services.screener_service import ConditionResult, _aggregate


def _results(flags):
    return [ConditionResult(flag, f"cond{i}") for i, flag in enumerate(flags)]


@pytest.mark.parametrize(
    "flags, mode, expected_hit, expected_count",
    [
        ([True, True, True], "all", True, 3),
        ([True, False], "all", False, 1),
        ([False, False], "any", False, 0),
        ([False, True], "any", True, 1),
        ([True, True, False], "atleast:2", True, 2),
        ([True, False, False], "atleast:2", False, 1),
        ([True, False], "ATLEAST:1", True, 1),
        ([True, False], "", False, 1),          # 空 mode 回落为 all
        ([], "all", False, 0),                  # 无条件不命中
        ([], "any", False, 0),
    ],
)
def test_aggregate(flags, mode, expected_hit, expected_count):
    assert _aggregate(_results(flags), mode) == (expected_hit, expected_count)

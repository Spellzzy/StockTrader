"""Typer Option 默认值兜底

命令函数被其它命令直接调用时，未传参的 Option 拿到的是 OptionInfo 对象，
它是真值，会让默认关闭的开关意外生效（曾导致 predict 隐式训练模型）。
"""

import typer

from app.commands import as_bool, as_int


def test_option_info_is_truthy():
    """确认这个坑确实存在，兜底函数才有意义"""
    assert bool(typer.Option(False, "--flag")) is True


def test_as_bool_converts_option_info_to_false():
    assert as_bool(typer.Option(False, "--flag")) is False


def test_as_bool_keeps_real_booleans():
    assert as_bool(True) is True
    assert as_bool(False) is False


def test_as_int_converts_option_info_to_default():
    assert as_int(typer.Option(0, "--n")) == 0
    assert as_int(typer.Option(0, "--n"), default=5) == 5


def test_as_int_keeps_real_ints_and_rejects_bools():
    assert as_int(3) == 3
    assert as_int(True) == 0  # bool 是 int 的子类，但不能当作数值

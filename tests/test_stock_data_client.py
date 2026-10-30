"""stock-data 客户端：输出解析与错误处理"""

import pytest

from app.data.stock_data_client import StockDataClient, StockDataError


def _client() -> StockDataClient:
    return StockDataClient(bin_path="stock-data")


def test_run_json_skips_http_request_prefix(monkeypatch):
    client = _client()
    monkeypatch.setattr(
        client,
        "_run",
        lambda *args: '[HTTP Request] http://api.example.com/quote\n{"price": 10.5}',
    )
    assert client._run_json("quote", "sh600519") == {"price": 10.5}


def test_run_json_returns_raw_output_when_no_json(monkeypatch):
    client = _client()
    raw = "[HTTP Request] http://api.example.com/quote\nno data"
    monkeypatch.setattr(client, "_run", lambda *args: raw)
    assert client._run_json("quote", "sh600519") == {"raw_output": raw}


def test_run_json_returns_raw_output_on_invalid_json(monkeypatch):
    client = _client()
    raw = "{不是合法 JSON}"
    monkeypatch.setattr(client, "_run", lambda *args: raw)
    assert client._run_json("quote", "sh600519") == {"raw_output": raw}


def test_run_raises_stock_data_error_when_binary_missing():
    client = StockDataClient(bin_path="definitely-not-a-real-binary")
    with pytest.raises(StockDataError):
        client._run("quote", "sh600519")

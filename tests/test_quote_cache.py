"""实时行情短 TTL 缓存：避免重复启动 stock-data 子进程"""

import pytest
from fastapi.testclient import TestClient

import app.config as config_mod
import app.web.api as api_mod
from app.data.stock_data_client import (
    StockDataClient,
    clear_quote_cache,
    quote_cache_ttl,
)


@pytest.fixture(autouse=True)
def clean_cache(isolate_config):
    clear_quote_cache()
    yield
    clear_quote_cache()


@pytest.fixture
def client_stub(monkeypatch):
    calls = []

    def fake_run_json(self, *args):
        calls.append(args)
        return {
            "sh600519": {"name": "贵州茅台", "price": 1400.0},
            "sz000001": {"name": "平安银行", "price": 12.0},
        }

    monkeypatch.setattr(StockDataClient, "_run_json", fake_run_json)
    return StockDataClient(bin_path="dummy"), calls


def test_default_ttl():
    assert quote_cache_ttl() == 20.0


def test_cache_hits_within_ttl(client_stub):
    client, calls = client_stub

    first = client.quote("sh600519")
    second = client.quote("sh600519")

    assert first == second
    assert len(calls) == 1
    assert calls[0] == ("quote", "sh600519")


def test_cache_key_ignores_code_order(client_stub):
    client, calls = client_stub

    client.quote("sh600519", "sz000001")
    client.quote("sz000001", "sh600519")

    assert len(calls) == 1


def test_different_code_sets_are_not_shared(client_stub):
    client, calls = client_stub

    client.quote("sh600519")
    client.quote("sz000001")

    assert len(calls) == 2


def test_use_cache_false_bypasses(client_stub):
    client, calls = client_stub

    client.quote("sh600519")
    client.quote("sh600519", use_cache=False)

    assert len(calls) == 2


def test_ttl_zero_disables_cache(client_stub):
    client, calls = client_stub
    config_mod._config["market"] = {"quote_cache_seconds": 0}

    assert quote_cache_ttl() == 0.0
    client.quote("sh600519")
    client.quote("sh600519")

    assert len(calls) == 2


def test_clear_cache_forces_refetch(client_stub):
    client, calls = client_stub

    client.quote("sh600519")
    assert clear_quote_cache() == 1
    client.quote("sh600519")

    assert len(calls) == 2


def test_caller_mutation_does_not_poison_cache(client_stub):
    client, _ = client_stub

    first = client.quote("sh600519")
    first["sh600519"]["price"] = 0
    second = client.quote("sh600519")

    assert second["sh600519"]["price"] == 1400.0


def test_clear_quotes_cache_endpoint():
    response = TestClient(api_mod.app).post("/api/cache/clear-quotes")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert "cleared" in response.json()["data"]

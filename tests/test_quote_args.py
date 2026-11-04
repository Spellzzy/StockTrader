"""行情命令的多代码参数：空格与逗号写法等价"""

from typer.testing import CliRunner

from app.models.stock import parse_stock_codes


def test_parse_comma_string():
    assert parse_stock_codes("600519,000001") == ["sh600519", "sz000001"]


def test_parse_list_and_mixed():
    assert parse_stock_codes(["sh600519", "sz000001"]) == ["sh600519", "sz000001"]
    assert parse_stock_codes(["600519,000001", "sz002555"]) == [
        "sh600519", "sz000001", "sz002555",
    ]


def test_parse_dedupes_and_ignores_empty():
    assert parse_stock_codes(["600519", "sh600519", "", "  "]) == ["sh600519"]


def test_parse_invalid_input():
    assert parse_stock_codes(None) == []
    assert parse_stock_codes([]) == []


def _quote_payload(codes):
    return {
        code: {
            "name": f"股票{code}", "price": 10.0, "change_percent": 1.0,
            "change": 0.1, "open": 9.9, "high": 10.2, "low": 9.8,
            "volume": 10000, "pe": 15.0,
        }
        for code in codes
    }


def test_both_cli_forms_are_equivalent(monkeypatch):
    import app.cli as cli_module
    import app.logging_setup as logging_setup

    seen = []

    def fake_get_quote(self, *codes):
        seen.append(list(codes))
        return _quote_payload(codes)

    monkeypatch.setattr(
        "app.services.market_service.MarketService.get_quote", fake_get_quote
    )
    monkeypatch.setattr(cli_module, "init_db", lambda: None)
    monkeypatch.setattr(logging_setup, "setup_logging", lambda *a, **kw: None)

    runner = CliRunner()
    r1 = runner.invoke(cli_module.app, ["q", "sh600519", "sz000001"])
    r2 = runner.invoke(cli_module.app, ["q", "sh600519,sz000001"])

    assert r1.exit_code == 0, r1.output
    assert r2.exit_code == 0, r2.output
    assert seen == [["sh600519", "sz000001"], ["sh600519", "sz000001"]]

from fastapi.testclient import TestClient

from cotacoes import allocation, fundamentals, ledger, storage
from main import app


def test_allocation_never_sums_currencies(tmp_path, monkeypatch):
    monkeypatch.setenv("COTACOES_DB_PATH", str(tmp_path / "portfolio.sqlite3"))
    monkeypatch.setenv("COTACOES_SEED_DEFAULTS", "0")
    storage.initialize()
    fundamentals.initialize()
    ledger.initialize()
    for symbol, price, currency in (
        ("PETR4", 10, "BRL"), ("VALE3", 20, "BRL"), ("AAPL", 100, "USD")
    ):
        storage.save_position(symbol, 10 if currency == "BRL" else 1, price, currency)
        storage.save_prices(symbol, [
            {"observed_at": "2026-11-01T00:00:00+00:00", "close": price}
        ], currency, "test")

    with storage.connection() as conn:
        conn.execute(
            "INSERT INTO fundamentals_cache(symbol,retrieved_at,data_json,provider) "
            "VALUES (?,? ,? ,'test')",
            ("PETR4", "2026-11-01T00:00:00+00:00",
             '{"sector":"Energy","quoteType":"EQUITY"}')
        )
    with TestClient(app) as client:
        response = client.get("/api/analysis/allocation")
        assert response.status_code == 200, response.text
        result = response.json()
    assert [g["currency"] for g in result["by_currency"]] == ["BRL", "USD"]
    brl = result["by_currency"][0]
    usd = result["by_currency"][1]
    assert brl["total_priced_value"] == 300
    assert usd["total_priced_value"] == 100
    assert brl["asset_count"] == 2
    assert brl["largest_position_pct"] == round(200/300*100, 4)
    assert brl["hhi"] == round((1/3)**2+(2/3)**2, 6)
    assert any(x["name"] == "Energy" for x in brl["by_sector"])
    assert any(x["name"] == "Sem classificacao" for x in brl["by_sector"])

import os
os.environ["COTACOES_SEED_DEFAULTS"] = "0"
from fastapi.testclient import TestClient
from cotacoes import storage, service
from main import app

def test_crud(tmp_path, monkeypatch):
    monkeypatch.setenv("COTACOES_DB_PATH", str(tmp_path / "db.sqlite3"))
    storage.initialize()
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert client.post("/api/assets", json={"symbol":"PETR4"}).status_code == 201
        assert client.post("/api/assets", json={"symbol":"PETR4"}).status_code == 409
        assert client.post("/api/assets", json={"symbol":"../bad"}).status_code == 422
        assert client.get("/api/assets/PETR4/history?period=invalid").status_code == 422
        storage.save_prices("PETR4", [{"observed_at":"2024-11-25T10:00:00","close":39.5}], "BRL", "test")
        assert client.put("/api/portfolio/positions", json={"symbol":"PETR4","quantity":10,"avg_cost":35,"currency":"BRL"}).status_code == 200
        assert client.get("/api/portfolio").json()["positions"][0]["pnl"] == 45
        assert client.delete("/api/portfolio/positions/PETR4").status_code == 200
        assert client.delete("/api/assets/PETR4").status_code == 200

def test_refresh_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("COTACOES_DB_PATH", str(tmp_path / "db2.sqlite3"))
    storage.initialize()
    storage.add_asset("BTC-BRL")
    monkeypatch.setattr("cotacoes.market.fetch_prices", lambda _: ([{"observed_at":"2026-11-05T00:00:00+00:00","close":500000}], "BRL"))
    assert service.refresh("BTC-BRL")["status"] == "updated"
    assert service.refresh("BTC-BRL")["status"] == "cached"
    def offline(_):
        raise RuntimeError("offline")
    monkeypatch.setattr("cotacoes.market.fetch_prices", offline)
    assert service.refresh("BTC-BRL", True)["cached_rows"] == 1

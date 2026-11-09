"""Testes deterministas, sem acesso a APIs de mercado."""
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from cotacoes import analysis, fundamentals, ledger, storage
from main import app


@pytest.fixture()
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("COTACOES_DB_PATH", str(tmp_path / "finance.sqlite3"))
    monkeypatch.setenv("COTACOES_SEED_DEFAULTS", "0")
    storage.initialize()
    ledger.initialize()
    fundamentals.initialize()
    return tmp_path


def _seed_series(symbol, scale=1.0, currency="BRL", length=95):
    start = date.today() - timedelta(days=length)
    points = []
    for i in range(length):
        value = (100 + i * 0.32 + (i % 9) * 0.7) * scale
        points.append({
            "observed_at": (start + timedelta(days=i)).isoformat() + "T00:00:00+00:00",
            "close": value,
        })
    storage.add_asset(symbol)
    storage.save_prices(symbol, points, currency, "yfinance")
    return points


def test_daily_statistics_and_events(db):
    points = _seed_series("PETR4")
    _seed_series("VALE3", 2.0)
    # Mesmo dia, CSV intradiario nao substitui fechamento do provedor.
    storage.save_prices("PETR4", [{"observed_at": points[-1]["observed_at"][:10]+"T12:00:00",
                                   "close": 999999}], "BRL", "csv-legado")
    daily = analysis.daily_prices("PETR4", 180)
    assert len(daily) == 95
    assert daily[-1]["close"] != 999999
    result = analysis.asset_risk("PETR4", 180, 0.95)
    assert result["observations"] == 94
    assert result["annualized_volatility_pct"] > 0
    assert result["max_drawdown_pct"] <= 0
    assert result["var_pct"] >= 0
    assert result["cvar_pct"] >= result["var_pct"]
    matches = analysis.correlation_matrix(["PETR4", "VALE3"], 180, 30)
    assert matches["pairs"][0]["correlation"] == pytest.approx(1, abs=1e-3)
    assert matches["pairs"][0]["observations"] == 94
    assert analysis.events("PETR4", 180, 0.1)["total_events"] > 0


def test_no_mixed_currencies(db):
    points = _seed_series("PETR4", length=60)
    storage.save_prices("PETR4", [{"observed_at": points[-1]["observed_at"],
                                   "close": 100.0}], "USD", "yfinance")
    with pytest.raises(ValueError, match="moedas diferentes"):
        analysis.asset_risk("PETR4", 180)


def test_transaction_ledger_and_income(db):
    storage.add_asset("PETR4")
    buy = ledger.add_trade("PETR4", "BUY", 10, 20, 2, "BRL",
                           datetime(2026, 1, 5, tzinfo=timezone.utc))
    assert isinstance(buy["id"], int)
    sell = ledger.add_trade("PETR4", "SELL", 4, 25, 1, "BRL",
                            datetime(2026, 1, 6, tzinfo=timezone.utc))
    assert isinstance(sell["id"], int)
    storage.save_prices("PETR4", [{"observed_at":"2026-11-01T00:00:00+00:00", "close":24}], "BRL", "test")
    inc = ledger.add_income("PETR4", "DIVIDEND", 12, 2, "BRL",
                            datetime(2026, 2, 1, tzinfo=timezone.utc))
    assert inc["id"] > 0
    summary = ledger.portfolio_summary()
    pos = summary["positions"][0]
    group = summary["by_currency"][0]
    assert pos["quantity"] == 6
    assert pos["avg_cost"] == pytest.approx(20.2)
    assert pos["invested"] == pytest.approx(121.2)
    assert pos["pnl"] == pytest.approx(22.8)
    assert group["realized_pnl"] == pytest.approx(18.2)
    assert group["income_net"] == pytest.approx(10)
    assert group["complete"] is True
    with pytest.raises(ValueError, match="excede"):
        ledger.add_trade("PETR4", "SELL", 99, 1, 0, "BRL",
                         datetime(2026, 1, 7, tzinfo=timezone.utc))
    # Excluir compra que sustenta uma venda nao e permitido.
    with pytest.raises(ValueError, match="excede"):
        ledger.delete_trade(buy["id"])
    assert ledger.delete_trade(sell["id"]) is True
    assert ledger.delete_trade(buy["id"]) is True
    assert ledger.delete_income(inc["id"]) is True


def test_backdated_sale_and_currency(db):
    ledger.add_trade("MXRF11", "BUY", 3, 10, 0, "BRL",
                     datetime(2026, 4, 5, tzinfo=timezone.utc))
    with pytest.raises(ValueError, match="excede"):
        ledger.add_trade("MXRF11", "SELL", 1, 11, 0, "BRL",
                         datetime(2026, 4, 4, tzinfo=timezone.utc))
    with pytest.raises(ValueError, match="moeda consistente"):
        ledger.add_trade("MXRF11", "BUY", 1, 10, 0, "USD",
                         datetime(2026, 4, 6, tzinfo=timezone.utc))


def test_manual_position_overridden_by_trades(db):
    storage.save_position("PETR4", 999, 1, "BRL")
    ledger.add_trade("PETR4", "BUY", 10, 25, 0, "BRL",
                     datetime(2026, 6, 1, tzinfo=timezone.utc))
    item = ledger.portfolio_summary()["positions"][0]
    assert item["source"] == "transactions"
    assert item["quantity"] == 10


def test_market_indicators_and_dividends(db, monkeypatch):
    _seed_series("MXRF11")
    fundamentals._fetch_indicators  # required symbol for monkeypatch
    monkeypatch.setattr(fundamentals, "_fetch_indicators",
                        lambda symbol: fundamentals.extract_indicators({
                            "longName": "Fundo Teste", "currency": "BRL",
                            "priceToBook": 0.92, "dividendYield": float("nan"),
                        }, symbol))
    monkeypatch.setattr(fundamentals, "_fetch_dividends",
                        lambda symbol: ([{"ex_date": date.today().isoformat(), "amount": 0.10}], "BRL"))
    with TestClient(app) as client:
        r = client.post("/api/assets/MXRF11/fundamentals/refresh")
        assert r.status_code == 200
        assert r.json()["indicators"]["priceToBook"] == 0.92
        assert r.json()["indicators"]["dividendYield"] is None
        assert client.get("/api/assets/MXRF11/fundamentals").json()["available"] is True
        d = client.post("/api/assets/MXRF11/dividends/refresh")
        assert d.status_code == 200
        assert d.json()["trailing_12m_per_unit"] == 0.10
        assert client.get("/api/assets/MXRF11/dividends").json()["items"][0]["amount"] == 0.10


def test_auth_and_trade_api(db, monkeypatch):
    monkeypatch.setenv("COTACOES_API_TOKEN", "secret-for-test")
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/assets").status_code == 401
        headers = {"X-API-Key": "secret-for-test"}
        assert client.post("/api/assets", json={"symbol":"PETR4"}, headers=headers).status_code == 201
        r = client.post("/api/portfolio/trades", headers=headers, json={
            "symbol": "PETR4", "side": "BUY", "quantity": 10,
            "unit_price": 25, "fee": 2, "currency": "BRL",
            "traded_at": "2026-01-01T10:00:00Z",
        })
        assert r.status_code == 201, r.text
        assert r.json()["id"] > 0
        r = client.post("/api/portfolio/trades", headers=headers, json={
            "symbol": "PETR4", "side": "SELL", "quantity": 11,
            "unit_price": 25, "fee": 0, "currency": "BRL",
            "traded_at": "2026-01-02T10:00:00Z",
        })
        assert r.status_code == 409
        assert client.get("/api/portfolio", headers=headers).json()["positions"][0]["quantity"] == 10
        assert client.get("/api/analysis/risk/PETR4", headers=headers).status_code == 422

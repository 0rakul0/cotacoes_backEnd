"""Treinamento de modelos por ticker, deterministico e sem acesso a rede."""
import json
import math
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from cotacoes import model_registry, model_training, storage
from main import app


@pytest.fixture()
def model_db(tmp_path, monkeypatch):
    monkeypatch.setenv("COTACOES_DB_PATH", str(tmp_path / "test_models.sqlite3"))
    monkeypatch.setenv("COTACOES_MODELS_DIR", str(tmp_path / "weights"))
    monkeypatch.setenv("COTACOES_SEED_DEFAULTS", "0")
    monkeypatch.delenv("COTACOES_API_TOKEN", raising=False)
    storage.initialize()
    model_registry.initialize()
    return tmp_path


def seed(symbol="PETR4", length=340, wave=0.21, days_ago=0):
    storage.add_asset(symbol)
    first = date.today() - timedelta(days=length - 1 + days_ago)
    price = 110.0 if symbol == "PETR4" else 25.0
    series = []
    for index in range(length):
        daily_return = 0.003 * math.sin(index * wave) + 0.0007 * math.cos(index * 0.07)
        price *= math.exp(daily_return)
        series.append({"observed_at": (first + timedelta(days=index)).isoformat()
                       + "T00:00:00+00:00", "close": price})
    storage.save_prices(symbol, series, "BRL", "yfinance")
    return series


def test_own_model_per_ticker(model_db):
    seed("PETR4")
    seed("MXRF11", wave=0.37)
    a = model_training.train("PETR4", family="ridge", days=365)
    b = model_training.train("MXRF11", family="ridge", days=365)
    assert a["model_id"] != b["model_id"]
    assert a["metrics"]["validation"]["samples"] > 25
    assert b["metrics"]["test"]["samples"] > 25
    assert model_registry.versions("PETR4")[0]["symbol"] == "PETR4"
    assert model_registry.versions("MXRF11")[0]["symbol"] == "MXRF11"
    assert a["selected"] is True
    assert b["selected"] is True
    pred_a = model_training.forecast("PETR4")
    pred_b = model_training.forecast("MXRF11")
    assert pred_a["symbol"] == "PETR4"
    assert pred_b["symbol"] == "MXRF11"
    assert pred_a["model_id"] != pred_b["model_id"]
    assert pred_a["predicted_next_close"] > 0
    assert pred_a["currency"] == "BRL"


def test_untrained_status_and_api(model_db):
    storage.add_asset("VALE3")
    with TestClient(app) as client:
        items = client.get("/api/models").json()["assets"]
        assert items[0]["symbol"] == "VALE3"
        assert items[0]["status"] == "not_trained"
        assert client.get("/api/models/VALE3").status_code == 200
        response = client.get("/api/models/VALE3/forecast")
        assert response.status_code == 409
        assert client.get("/api/models/NOEX4").status_code == 404


def test_no_future_leakage_in_normalization(model_db):
    series = seed("PETR4")
    before = model_training.prepare("PETR4", 365)
    # Muda fechamento somente no BLOCO DE TESTE.
    storage.save_prices("PETR4", [{
        "observed_at": series[-1]["observed_at"],
        "close": series[-1]["close"] * 1.25,
    }], "BRL", "yfinance")
    after = model_training.prepare("PETR4", 365)
    assert before["mean"] == after["mean"]
    assert before["std"] == after["std"]
    assert before["fingerprint"] != after["fingerprint"]


def test_missing_data_prevents_training(model_db):
    seed("PETR4", length=70)
    with pytest.raises(ValueError, match="Historico continuo insuficiente"):
        model_training.train("PETR4", "ridge", days=365)


def test_gap_breaks_training_sample(model_db):
    seed("PETR4", length=280, days_ago=170)
    price = 122.0
    storage.save_prices("PETR4", [
        {"observed_at": (date.today() - timedelta(days=i)).isoformat() + "T00:00:00+00:00",
         "close": price + i * 0.1}
        for i in range(20)
    ], "BRL", "yfinance")
    with pytest.raises(ValueError, match="Historico continuo insuficiente"):
        model_training.train("PETR4", "ridge", days=730)


def test_integrity_and_safe_paths(model_db):
    seed("PETR4")
    model_training.train("PETR4", "ridge", days=365)
    row = model_registry.selected("PETR4")
    assert row is not None
    path = model_registry.model_root() / row["artifact_relpath"]
    content = path.read_bytes()
    meta = json.loads(content)
    assert meta["symbol"] == "PETR4"
    path.write_bytes(content + b"tampered")
    with pytest.raises(ValueError, match="Integridade"):
        model_registry.load_artifact(row)
    with pytest.raises(ValueError, match="Caminho"):
        model_registry.read_verified("../../private", "abc")


def test_old_prices_cannot_be_forecast(model_db):
    seed("PETR4", length=340, days_ago=30)
    model_training.train("PETR4", "ridge", days=730)
    with pytest.raises(ValueError, match="Cotacao desatualizada"):
        model_training.forecast("PETR4")


def test_optional_torch_module_loads_if_installed(model_db):
    torch = pytest.importorskip("torch")
    from cotacoes.torch_forecast import make_model
    for family in ("lstm", "autoencoder", "transformer"):
        model = make_model(family, window=20)
        with torch.inference_mode():
            result = model(torch.zeros(2, 20, 1))
        if family == "autoencoder":
            assert result[0].shape == (2, 1)
            assert result[1].shape == (2, 20, 1)
        else:
            assert result.shape == (2, 1)

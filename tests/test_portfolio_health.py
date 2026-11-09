"""Testes de pesquisa documental de FIIs com documento fonte audivel."""
import copy
import json
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cotacoes import document_pipeline, portfolio_health, storage
from main import app

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "mxrf11_2026_09.json"


@pytest.fixture()
def health_db(tmp_path, monkeypatch):
    monkeypatch.setenv("COTACOES_DB_PATH", str(tmp_path / "health.sqlite3"))
    monkeypatch.setenv("COTACOES_SEED_DEFAULTS", "0")
    monkeypatch.setenv("COTACOES_SEED_HEALTH_EXAMPLE", "0")
    monkeypatch.delenv("COTACOES_API_TOKEN", raising=False)
    storage.initialize()
    portfolio_health.initialize()
    return tmp_path


def example():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def test_mxrf11_official_source_and_risks(health_db):
    result = portfolio_health.ingest(example())
    assert result["created"] is True
    report = portfolio_health.report("MXRF11", as_of="2026-11-08")
    assert report["reference_date"] == "2026-09-30"
    assert report["coverage"] == "parcial"
    assert report["summary"]["disclosed_holdings"] == 23
    assert report["summary"]["critical"] >= 2
    assert report["summary"]["attention"] >= 3
    assert report["summary"]["with_reported_vacancy"] == 0
    assert report["overview"]["allocation_pct"]["CRI"] == 75
    assert report["overview"]["cash_distribution_coverage_ratio"] < 1
    assert len([h for h in report["exposures"] if h["category"] == "CRI"]) >= 10
    assert report["source_documents"][0]["url"].startswith(
        "https://fnet.bmfbovespa.com.br/"
    )
    assert portfolio_health.ingest(example())["created"] is False


def test_missing_vacancy_is_unknown_not_zero(health_db):
    portfolio_health.ingest(example())
    report = portfolio_health.report("MXRF11")
    assaí = next(h for h in report["exposures"] if h["id"] == "23H1539646")
    assert assaí.get("vacancy_pct") is None
    assert assaí["has_vacancy_data"] is False
    assert assaí["risk"] == "sem_avaliacao"
    # Status de risco nao deve extrapolar ocupacao do lastro de um CRI.


def test_permuta_stock_and_delivery_flags(health_db):
    portfolio_health.ingest(example())
    report = portfolio_health.report("MXRF11", as_of="2026-11-08")
    garden = next(h for h in report["exposures"] if h["id"] == "perm_jardimeuropa2")
    assert garden["risk"] == "atencao"
    codes = {f["code"] for f in garden["flags"]}
    assert "entrega_prevista_ultrapassada" in codes
    assert "estoque_elevado" in codes
    brooklyn = next(h for h in report["exposures"] if h["id"] == "perm_brooklin2")
    assert brooklyn["risk"] == "sem_avaliacao"


def test_calendar_no_invented_cri_coupon_dates(health_db):
    portfolio_health.ingest(example())
    agenda = portfolio_health.agenda("MXRF11", as_of="2026-11-08")
    assert len(agenda["payments"]) == 2
    announced = next(x for x in agenda["payments"] if x["payment_date"] == "2026-11-16")
    assert announced["amount_per_unit"] == 0.095
    assert announced["kind"] == "rendimento_fundo"
    assert announced["status"] == "futuro"
    monthly_cris = [e for e in agenda["uncertain_coupon_dates"] if e["holding_id"] == "24L1853110"]
    assert len(monthly_cris) == 1
    assert all(x["precision"] == "month_only" for x in agenda["maturities_by_month"])
    assert all(x["kind"] != "cupom" for x in agenda["payments"])


def test_reject_untrusted_documents(health_db):
    for url in ("http://fnet.bmfbovespa.com.br/fnet/publico/exibirDocumento?id=1",
                "https://127.0.0.1/private",
                "https://fnet.bmfbovespa.com.br.evil.example/file",
                "https://evil.example/file"):
        modified = example()
        modified["documents"][0]["url"] = url
        with pytest.raises(ValueError, match="fonte oficial"):
            portfolio_health.ingest(modified)
    with pytest.raises(ValueError, match="ID numerico"):
        document_pipeline._canonical(
            "https://fnet.bmfbovespa.com.br/fnet/publico/exibirDocumento?id=../../private"
        )


def test_vacancy_not_on_cri_and_payment_has_source(health_db):
    modified = example()
    modified["holdings"][0]["vacancy_pct"] = 0
    with pytest.raises(ValueError, match="Vacancia"):
        portfolio_health.ingest(modified)
    modified = example()
    modified["payments"][0]["source"] = "nao_existe"
    with pytest.raises(ValueError, match="Pagamento sem documento"):
        portfolio_health.ingest(modified)


def test_api_health_documentation_and_ledger_unchanged(health_db):
    portfolio_health.ingest(example())
    with TestClient(app) as client:
        assert client.get("/api/funds/MXRF11/health").status_code == 200
        assert client.get("/api/funds/MXRF11/holdings?category=PERMUTA").status_code == 200
        assert client.get("/api/funds/MXRF11/calendar").status_code == 200
        detail = client.get("/api/funds/MXRF11/holdings/21F0568504")
        assert detail.status_code == 200
        assert detail.json()["risk"] == "atencao"
        assert client.get("/api/funds/PETR4/health").json()["status"] == "sem_documentos"
        assert client.get("/api/funds/MXRF11/holdings/NOPE").status_code == 404
        assert client.get("/api/portfolio").status_code == 200

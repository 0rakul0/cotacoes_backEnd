import pytest

from cotacoes import storage
from monitoramento import monitorar


def test_monitor_no_selenium(tmp_path, monkeypatch):
    monkeypatch.setenv("COTACOES_DB_PATH", str(tmp_path / "quotes.sqlite3"))
    monkeypatch.setenv("COTACOES_SEED_DEFAULTS", "0")
    storage.initialize()
    storage.add_asset("PETR4")
    monkeypatch.setattr(monitorar.service, "refresh", lambda symbol, force: {
        "symbol": symbol, "rows": 60, "status": "updated",
    })
    stats = monitorar.run_once()
    assert stats["updated"] == 1
    assert stats["cached"] == 0
    assert stats["errors"] == 0
    stats = monitorar.run_once(["VALE3"])
    assert stats["errors"] == 1
    assert stats["details"][0]["symbol"] == "VALE3"

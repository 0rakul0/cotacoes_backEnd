"""Registro persistente e verificavel de modelos independentes por ativo.

Somente artefatos gerados pelo treinamento local sao registrados. Os pesos
PyTorch antigos permanecem em legacy_sources e NUNCA sao carregados pela API.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from cotacoes import storage

FAMILIES = ("ridge", "lstm", "autoencoder", "transformer")
SAFE = re.compile(r"^[A-Z0-9^][A-Z0-9.^=-]{0,24}$")


def model_root() -> Path:
    return Path(os.getenv("COTACOES_MODELS_DIR", str(storage.ROOT / "data" / "model_artifacts"))).expanduser().resolve()


def initialize() -> None:
    with storage.connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS model_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            family TEXT NOT NULL,
            trained_at TEXT NOT NULL,
            data_fingerprint TEXT NOT NULL,
            data_end TEXT NOT NULL,
            currency TEXT NOT NULL,
            train_samples INTEGER NOT NULL,
            validation_samples INTEGER NOT NULL,
            test_samples INTEGER NOT NULL,
            metrics_json TEXT NOT NULL,
            artifact_relpath TEXT NOT NULL,
            artifact_sha256 TEXT NOT NULL,
            selected INTEGER NOT NULL DEFAULT 0,
            CHECK(family IN ('ridge','lstm','autoencoder','transformer'))
        );
        CREATE INDEX IF NOT EXISTS ix_model_runs_symbol ON model_runs(symbol, id DESC);
        CREATE UNIQUE INDEX IF NOT EXISTS ux_model_selected ON model_runs(symbol)
          WHERE selected = 1;
        """)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _path_for(relative: str) -> Path:
    base = model_root()
    path = (base / relative).resolve()
    if not path.is_relative_to(base) or path == base:
        raise ValueError("Caminho de artefato invalido.")
    return path


def store_bytes(relative: str, payload: bytes) -> str:
    path = _path_for(relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return _sha256(payload)


def read_verified(relative: str, expected_sha: str) -> bytes:
    path = _path_for(relative)
    data = path.read_bytes()
    if _sha256(data) != expected_sha:
        raise ValueError("Integridade de artefato comprometida.")
    return data


def new_paths(symbol: str, family: str) -> tuple[str, str]:
    if not SAFE.fullmatch(symbol) or family not in FAMILIES:
        raise ValueError("Ticker ou familia invalida para artefato.")
    version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:12]
    prefix = f"{symbol}/{family}/{version}"
    return prefix + ".json", prefix + ".pt"


def save_model(symbol: str, family: str, artifact: dict, details: dict,
               weight_bytes: bytes | None = None) -> int:
    """Grava os arquivos antes do registro; sem deserializar objetos externos."""
    json_path, torch_path = new_paths(symbol, family)
    if weight_bytes is not None:
        artifact["weights_relpath"] = torch_path
        artifact["weights_sha256"] = store_bytes(torch_path, weight_bytes)
    if family != "ridge" and weight_bytes is None:
        raise ValueError("Arquitetura neural requer pesos.")
    artifact["family"] = family
    artifact["symbol"] = symbol
    bytes_payload = json.dumps(artifact, allow_nan=False, sort_keys=True).encode("utf-8")
    checksum = store_bytes(json_path, bytes_payload)
    metrics_json = json.dumps(details["metrics"], allow_nan=False, sort_keys=True)
    with storage.connection() as conn:
        cursor = conn.execute("""
            INSERT INTO model_runs(
                symbol, family, trained_at, data_fingerprint, data_end, currency,
                train_samples, validation_samples, test_samples, metrics_json,
                artifact_relpath, artifact_sha256
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            symbol, family, storage.utc_now(), details["fingerprint"],
            details["data_end"], details["currency"], details["train_samples"],
            details["validation_samples"], details["test_samples"], metrics_json,
            json_path, checksum,
        ))
        return int(cursor.lastrowid)


def _public(row: dict) -> dict:
    return {
        "id": row["id"], "symbol": row["symbol"], "family": row["family"],
        "trained_at": row["trained_at"], "data_end": row["data_end"],
        "currency": row["currency"],
        "train_samples": row["train_samples"],
        "validation_samples": row["validation_samples"],
        "test_samples": row["test_samples"],
        "fingerprint": row["data_fingerprint"],
        "metrics": json.loads(row["metrics_json"]),
        "selected": bool(row["selected"]),
    }


def versions(symbol: str, limit: int = 40) -> list[dict]:
    with storage.connection() as conn:
        rows = conn.execute(
            "SELECT * FROM model_runs WHERE symbol=? ORDER BY id DESC LIMIT ?",
            (symbol, limit),
        ).fetchall()
    return [_public(dict(row)) for row in rows]


def selected(symbol: str) -> dict | None:
    with storage.connection() as conn:
        row = conn.execute("SELECT * FROM model_runs WHERE symbol=? AND selected=1",
                           (symbol,)).fetchone()
    return dict(row) if row else None


def choose(symbol: str, fingerprint: str) -> dict | None:
    """Seleciona por VALIDACAO, nunca consultando o erro de teste para escolher."""
    with storage.connection() as conn:
        rows = conn.execute("""
            SELECT * FROM model_runs
            WHERE symbol=? AND data_fingerprint=? ORDER BY id DESC
        """, (symbol, fingerprint)).fetchall()
        if not rows:
            return None
        # Apenas a versao mais nova de cada arquitetura para este dataset.
        latest = {}
        for row in rows:
            if row["family"] not in latest:
                latest[row["family"]] = dict(row)
        qualified = []
        for row in latest.values():
            m = json.loads(row["metrics_json"])
            validation = m["validation"]
            if validation["rmse_pct"] < validation["naive_rmse_pct"] * 0.99:
                qualified.append((validation["rmse_pct"], row["id"]))
        if not qualified:
            # Nao substitui o modelo anterior se o novo treinamento nao melhorar.
            return None
        best_id = min(qualified)[1]
        conn.execute("UPDATE model_runs SET selected=0 WHERE symbol=?", (symbol,))
        conn.execute("UPDATE model_runs SET selected=1 WHERE id=?", (best_id,))
        chosen = conn.execute("SELECT * FROM model_runs WHERE id=?", (best_id,)).fetchone()
    return _public(dict(chosen))


def load_artifact(row: dict) -> dict:
    data = read_verified(row["artifact_relpath"], row["artifact_sha256"])
    artifact = json.loads(data)
    if artifact.get("symbol") != row["symbol"] or artifact.get("family") != row["family"]:
        raise ValueError("Artefato nao pertence ao ativo solicitado.")
    return artifact


def overview(symbol: str) -> dict:
    models = versions(symbol)
    current = next((m for m in models if m["selected"]), None)
    return {
        "symbol": symbol,
        "status": "selected" if current else ("candidate" if models else "not_trained"),
        "selected": current,
        "models": models,
        "note": "Modelos especificos por ativo. Selecionados por validacao temporal versus ultimo preco; os testes permanecem fora da selecao.",
    }


def all_status() -> dict:
    tracked = [x["symbol"] for x in storage.list_assets()]
    return {"assets": [overview(s) for s in tracked], "tracked_count": len(tracked)}

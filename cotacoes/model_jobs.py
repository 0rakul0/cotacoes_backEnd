"""Treinamento por ticker separado do processo web FastAPI.

Exemplos:
    python -m cotacoes.model_jobs train --symbol PETR4 --family ridge
    python -m cotacoes.model_jobs train --all --family ridge
    python -m cotacoes.model_jobs train --symbol PETR4 --family all --epochs 60
    python -m cotacoes.model_jobs status
"""
from __future__ import annotations

import argparse
import json
import logging

from cotacoes import model_registry, model_training, storage

LOG = logging.getLogger(__name__)


def train_batch(symbols: list[str], family: str, days: int = 1825,
                epochs: int = 60, window: int = 20) -> dict:
    families = list(model_registry.FAMILIES) if family == "all" else [family]
    if any(f not in model_registry.FAMILIES for f in families):
        raise ValueError("Familia invalida.")
    results = []
    for symbol in symbols:
        for f in families:
            LOG.info("Treinando %s (%s)...", symbol, f)
            try:
                result = model_training.train(symbol, f, days=days,
                                              window=window, epochs=epochs)
                results.append({"symbol": symbol, "family": f, "status": "trained",
                                "id": result["model_id"],
                                "selected": result["selected"],
                                "validation": result["metrics"]["validation"],
                                "test": result["metrics"]["test"]})
            except (ValueError, RuntimeError, ImportError, OSError) as exc:
                LOG.warning("Treino indisponivel para %s %s: %s", symbol, f, exc)
                results.append({"symbol": symbol, "family": f,
                                "status": "skipped", "reason": str(exc)[:300]})
    return {
        "trained": sum(x["status"] == "trained" for x in results),
        "skipped": sum(x["status"] == "skipped" for x in results),
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    train = sub.add_parser("train", help="Treinar modelos com historico ja armazenado.")
    group = train.add_mutually_exclusive_group(required=True)
    group.add_argument("--symbol", type=str)
    group.add_argument("--all", action="store_true", help="Todos ativos acompanhados.")
    train.add_argument("--family", choices=(*model_registry.FAMILIES, "all"), default="ridge")
    train.add_argument("--days", type=int, default=1825)
    train.add_argument("--window", type=int, default=20)
    train.add_argument("--epochs", type=int, default=60)
    sub.add_parser("status", help="Mostrar situacao do treinamento por ativo.")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    storage.initialize()
    model_registry.initialize()
    if args.action == "status":
        print(json.dumps(model_registry.all_status(), ensure_ascii=False, indent=2))
        return 0
    symbols = [item["symbol"] for item in storage.list_assets()] if args.all else [args.symbol]
    report = train_batch(symbols, args.family, args.days, args.epochs, args.window)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["skipped"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

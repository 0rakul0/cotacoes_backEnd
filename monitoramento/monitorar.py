"""Atualizador opcional de cotacoes (sem Selenium).

Uso:
    python -m monitoramento.monitorar --once
    python -m monitoramento.monitorar --loop --interval-minutes 60

Os dados do yfinance sao fechamentos historicos diarios, nao feed em tempo real.
"""
from __future__ import annotations

import argparse
import logging
import time

from cotacoes import market, service, storage

log = logging.getLogger(__name__)


def run_once(symbols: list[str] | None = None, force: bool = False) -> dict:
    storage.initialize()
    if symbols is None:
        symbols = [row["symbol"] for row in storage.list_assets()]
    else:
        symbols = [market.normalize_symbol(symbol) for symbol in symbols]
    report = {"updated": 0, "cached": 0, "errors": 0, "details": []}
    for symbol in symbols:
        if not storage.asset_exists(symbol):
            log.warning("Ticker nao acompanhado: %s", symbol)
            report["errors"] += 1
            report["details"].append({"symbol": symbol, "status": "error", "error": "Nao cadastrado"})
            continue
        result = service.refresh(symbol, force=force)
        report["details"].append(result)
        status = result["status"]
        if status == "updated":
            report["updated"] += 1
            log.info("%s atualizado (%d pontos)", symbol, result["rows"])
        elif status == "cached":
            report["cached"] += 1
            log.info("%s ainda em cache", symbol)
        else:
            report["errors"] += 1
            log.warning("%s: %s", symbol, result.get("error", "falha desconhecida"))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Atualizar uma vez (padrao).")
    parser.add_argument("--loop", action="store_true", help="Rodar continuamente como processo separado.")
    parser.add_argument("--interval-minutes", type=int, default=60, help="Intervalo no modo loop (minimo 5).")
    parser.add_argument("--force", action="store_true", help="Ignorar TTL do cache.")
    parser.add_argument("--symbols", nargs="+", help="Somente estes tickers ja cadastrados.")
    args = parser.parse_args()
    if args.loop and args.once:
        parser.error("--once e --loop sao modos exclusivos.")
    if args.loop and args.interval_minutes < 5:
        parser.error("O intervalo minimo do loop e 5 minutos.")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        while True:
            result = run_once(args.symbols, args.force)
            log.info("Resultado: atualizados=%s, cache=%s, erros=%s",
                     result["updated"], result["cached"], result["errors"])
            if not args.loop:
                return 1 if result["errors"] else 0
            time.sleep(args.interval_minutes * 60)
    except KeyboardInterrupt:
        log.info("Interrompido pelo operador.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

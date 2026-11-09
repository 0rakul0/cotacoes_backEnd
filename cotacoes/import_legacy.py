"""Importa o arquivo historico CSV de 2024 sem alterar os arquivos originais."""
from __future__ import annotations

import argparse
import csv
import math
import re
from datetime import datetime
from pathlib import Path

from cotacoes import market, storage


def parse_br_number(raw: str) -> float | None:
    value = re.sub(r"[^\d,.\-]", "", (raw or "").strip())
    if not value:
        return None
    if "," in value:
        value = value.replace(".", "").replace(",", ".")
    try:
        number = float(value)
        return number if math.isfinite(number) and number > 0 else None
    except ValueError:
        return None


def import_directory(directory: Path | None = None) -> dict:
    root = Path(directory) if directory is not None else storage.ROOT / "dados" / "csv"
    report = {"files": 0, "rows": 0, "imported": 0, "ignored": 0}
    if not root.is_dir():
        return report

    for path in sorted(root.rglob("*.csv")):
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                if not reader.fieldnames or not {"Data_minute", "Valor"}.issubset(reader.fieldnames):
                    continue
                report["files"] += 1
                buckets: dict[str, list[dict]] = {}
                for row in reader:
                    report["rows"] += 1
                    try:
                        fallback = path.stem.replace("stock_data_", "").replace("_stock_data", "")
                        symbol = market.normalize_symbol(row.get("Ticker") or fallback)
                        stamp = datetime.strptime(
                            (row.get("Data_minute") or "").strip(), "%Y-%m-%d %H:%M"
                        ).isoformat()
                        value = parse_br_number(row.get("Valor", ""))
                        if value is None:
                            raise ValueError("preco invalido")
                        buckets.setdefault(symbol, []).append(
                            {"observed_at": stamp, "close": value}
                        )
                    except (ValueError, TypeError):
                        report["ignored"] += 1
                for symbol, prices in buckets.items():
                    storage.add_asset(symbol)
                    report["imported"] += storage.save_prices(
                        symbol, prices, market.default_currency(symbol), "csv-legado"
                    )
        except (OSError, UnicodeError, csv.Error):
            report["ignored"] += 1
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, default=None, help="Diretorio legado dos CSV")
    args = parser.parse_args()
    storage.initialize()
    print(import_directory(args.dir))

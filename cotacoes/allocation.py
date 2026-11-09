"""Concentracao e alocacao da carteira sem conversao cambial ficticia."""
from __future__ import annotations

import json
from collections import defaultdict

from cotacoes import ledger, storage


def allocation() -> dict:
    positions = ledger.portfolio_summary()["positions"]
    with storage.connection() as conn:
        rows = conn.execute("SELECT symbol, data_json FROM fundamentals_cache").fetchall()
    indicators = {}
    for row in rows:
        try:
            indicators[row["symbol"]] = json.loads(row["data_json"])
        except (TypeError, ValueError):
            continue

    groups: dict[str, list[dict]] = defaultdict(list)
    unpriced = []
    for item in positions:
        value = item["market_value"]
        if value is None or value <= 0:
            unpriced.append({"symbol": item["symbol"], "reason": item.get("warning") or "Sem preco valido"})
            continue
        meta = indicators.get(item["symbol"], {})
        groups[item["currency"]].append({
            "symbol": item["symbol"], "market_value": value,
            "sector": meta.get("sector") or "Sem classificacao",
            "type": meta.get("quoteType") or "Sem classificacao",
            "price_date": item.get("price_date"),
        })

    output = []
    for currency, entries in sorted(groups.items()):
        total = sum(e["market_value"] for e in entries)
        if total <= 0:
            continue
        sectors: dict[str, float] = defaultdict(float)
        types: dict[str, float] = defaultdict(float)
        assets = []
        hhi = 0.0
        for entry in entries:
            weight = entry["market_value"] / total
            hhi += weight * weight
            sectors[entry["sector"]] += entry["market_value"]
            types[entry["type"]] += entry["market_value"]
            assets.append({**entry, "weight_pct": round(100 * weight, 4)})

        def grouped(source: dict[str, float]) -> list[dict]:
            return sorted((
                {"name": name, "market_value": round(value, 2),
                 "weight_pct": round(value / total * 100, 4)}
                for name, value in source.items()
            ), key=lambda x: x["weight_pct"], reverse=True)

        assets.sort(key=lambda a: a["market_value"], reverse=True)
        output.append({
            "currency": currency,
            "total_priced_value": round(total, 2),
            "asset_count": len(assets),
            "assets": assets,
            "by_sector": grouped(sectors),
            "by_type": grouped(types),
            "hhi": round(hhi, 6),
            "effective_number_of_assets": round(1 / hhi, 4) if hhi else None,
            "largest_position_pct": assets[0]["weight_pct"] if assets else None,
        })
    return {
        "by_currency": output, "excluded_positions": unpriced,
        "note": "Pesos calculados a partir dos precos armazenados. Sem conversao cambial, derivativos, look-through de ETFs/FIIs ou verificacao de setor. HHI nao e medida suficiente de risco.",
    }

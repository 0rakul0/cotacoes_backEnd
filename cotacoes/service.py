"""Operacoes de negocio: cache de mercado e visao basica da carteira."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from cotacoes import market, storage

PERIODS = {
    "1mo": 31, "3mo": 93, "6mo": 186,
    "1y": 366, "5y": 1827, "max": None,
}


def history(symbol: str, period: str) -> dict:
    if period not in PERIODS:
        raise ValueError("Periodo invalido.")
    cutoff = None
    if PERIODS[period] is not None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=PERIODS[period])).date().isoformat()
    points = storage.history(symbol, cutoff)
    return {"symbol": symbol, "period": period, "points": points, "count": len(points)}


def refresh(symbol: str, force: bool = False) -> dict:
    if not storage.asset_exists(symbol):
        return {"symbol": symbol, "status": "error", "error": "Ativo nao acompanhado."}

    state = storage.read_refresh(symbol)
    ttl = max(1, int(os.getenv("COTACOES_CACHE_MINUTES", "30")))
    if not force and state and state.get("last_success") and storage.price_count(symbol):
        try:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(state["last_success"])
            if age < timedelta(minutes=ttl):
                return {"symbol": symbol, "status": "cached", "rows": 0}
        except ValueError:
            pass
    try:
        rows, currency = market.fetch_prices(symbol)
        count = storage.save_prices(symbol, rows, currency, "yfinance")
        storage.save_refresh(symbol, None)
        return {"symbol": symbol, "status": "updated", "rows": count, "currency": currency}
    except Exception as exc:
        # Mantem os precos anteriores e sinaliza explicitamente a falha.
        error = str(exc)[:240] or "Falha na consulta ao provedor."
        storage.save_refresh(symbol, error)
        return {"symbol": symbol, "status": "error", "error": error,
                "cached_rows": storage.price_count(symbol)}


def portfolio_summary() -> dict:
    positions = []
    groups: dict[str, dict] = {}
    for item in storage.list_positions():
        symbol = item["symbol"]
        qty = float(item["quantity"])
        cost = float(item["avg_cost"])
        currency = item["currency"]
        quote = item["quote"]
        if quote and quote["currency"] != currency:
            # Evita calcular retorno com custo e cotacao em moedas diferentes.
            price = None
            warning = "Moeda da cotacao difere da moeda de custo."
        else:
            price = float(quote["close"]) if quote else None
            warning = None
        invested = qty * cost
        market_value = qty * price if price is not None else None
        pnl = market_value - invested if market_value is not None else None
        positions.append({
            "symbol": symbol, "quantity": qty, "avg_cost": cost,
            "currency": currency, "invested": round(invested, 2),
            "last_price": price,
            "market_value": round(market_value, 2) if market_value is not None else None,
            "pnl": round(pnl, 2) if pnl is not None else None,
            "pnl_pct": round(100 * pnl / invested, 2) if pnl is not None and invested else None,
            "price_date": quote["observed_at"] if quote else None,
            "warning": warning,
        })
        group = groups.setdefault(currency, {
            "currency": currency, "invested": 0.0, "market_value": 0.0,
            "pnl": 0.0, "priced_positions": 0, "positions": 0
        })
        group["invested"] += invested
        group["positions"] += 1
        if market_value is not None:
            group["market_value"] += market_value
            group["pnl"] += pnl
            group["priced_positions"] += 1

    for group in groups.values():
        for key in ("invested", "market_value", "pnl"):
            group[key] = round(group[key], 2)
        group["complete"] = group["priced_positions"] == group["positions"]

    return {"positions": positions, "by_currency": sorted(groups.values(),
            key=lambda row: row["currency"]), "disclaimer":
            "Valores estimados com fechamentos historicos; nao incluem proventos, impostos, taxas nem corretagem."}

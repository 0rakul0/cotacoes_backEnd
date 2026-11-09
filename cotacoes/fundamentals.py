"""Indicadores fundamentalistas e proventos anunciados, via Yahoo Finance.

Dados de provedores terceiros podem conter campos ausentes ou inconsistentes.
Dividendos de mercado NAO sao recebimentos da carteira pessoal.
"""
from __future__ import annotations

import json
import math
import os
from datetime import date, datetime, timedelta, timezone

from cotacoes import market, storage

NUMERIC_FIELDS = (
    "marketCap", "trailingPE", "forwardPE", "priceToBook", "bookValue",
    "trailingEps", "returnOnEquity", "profitMargins", "operatingMargins",
    "dividendYield", "payoutRatio", "debtToEquity", "totalRevenue",
    "freeCashflow", "beta", "currentPrice", "volume", "averageVolume",
)
TEXT_FIELDS = ("longName", "shortName", "sector", "industry", "quoteType", "financialCurrency")


def initialize() -> None:
    with storage.connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS fundamentals_cache (
                symbol TEXT PRIMARY KEY,
                retrieved_at TEXT NOT NULL,
                data_json TEXT NOT NULL,
                provider TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS market_dividends (
                symbol TEXT NOT NULL,
                ex_date TEXT NOT NULL,
                amount REAL NOT NULL CHECK (amount > 0),
                currency TEXT NOT NULL,
                provider TEXT NOT NULL,
                PRIMARY KEY(symbol, ex_date, provider)
            );
            CREATE INDEX IF NOT EXISTS ix_market_dividends_symbol_date
                ON market_dividends(symbol, ex_date DESC);
            CREATE TABLE IF NOT EXISTS dividend_refresh (
                symbol TEXT PRIMARY KEY,
                retrieved_at TEXT NOT NULL
            );
        """)


def _numeric(data: dict, key: str) -> float | None:
    value = data.get(key)
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError, OverflowError):
        return None


def extract_indicators(info: dict, symbol: str) -> dict:
    if not isinstance(info, dict) or not info:
        raise ValueError("Provedor nao retornou dados fundamentalistas.")
    data = {field: _numeric(info, field) for field in NUMERIC_FIELDS}
    data.update({field: str(info[field])[:200] if isinstance(info.get(field), str) else None
                 for field in TEXT_FIELDS})
    currency = info.get("currency")
    data["currency"] = currency.upper() if isinstance(currency, str) and len(currency) == 3 else market.default_currency(symbol)
    data["symbol"] = symbol
    data["provider_symbol"] = market.provider_symbol(symbol)
    return data


def _fetch_indicators(symbol: str) -> dict:
    import yfinance as yf
    ticker = yf.Ticker(market.provider_symbol(symbol))
    info = ticker.info
    return extract_indicators(info, symbol)


def cached_indicators(symbol: str) -> dict:
    with storage.connection() as conn:
        row = conn.execute(
            "SELECT retrieved_at,data_json,provider FROM fundamentals_cache WHERE symbol=?",
            (symbol,)
        ).fetchone()
    if not row:
        return {"symbol": symbol, "available": False, "status": "not_fetched",
                "note": "Utilize POST /api/assets/{symbol}/fundamentals/refresh para consultar o provedor."}
    return {
        "symbol": symbol, "available": True, "retrieved_at": row["retrieved_at"],
        "provider": row["provider"], "indicators": json.loads(row["data_json"]),
        "note": "Indicadores fornecidos por terceiros; dados podem estar incompletos ou defasados. Datas de balanços nao foram validadas.",
    }


def _fresh(timestamp: str, ttl_hours: int) -> bool:
    try:
        return datetime.now(timezone.utc) - datetime.fromisoformat(timestamp) < timedelta(hours=ttl_hours)
    except (TypeError, ValueError):
        return False


def refresh_indicators(symbol: str, force: bool = False) -> dict:
    previous = cached_indicators(symbol)
    ttl = max(1, int(os.getenv("COTACOES_FUNDAMENTALS_TTL_HOURS", "24")))
    if previous.get("available") and not force and _fresh(previous["retrieved_at"], ttl):
        return {"status": "cached", **previous}
    indicators = _fetch_indicators(symbol)
    timestamp = storage.utc_now()
    with storage.connection() as conn:
        conn.execute("""
            INSERT INTO fundamentals_cache(symbol,retrieved_at,data_json,provider)
            VALUES (?,?,?,'yfinance')
            ON CONFLICT(symbol) DO UPDATE SET
                retrieved_at=excluded.retrieved_at,
                data_json=excluded.data_json,provider=excluded.provider
        """, (symbol, timestamp, json.dumps(indicators, allow_nan=False)))
    return {"status": "updated", **cached_indicators(symbol)}


def _fetch_dividends(symbol: str) -> tuple[list[dict], str]:
    import yfinance as yf
    ticker = yf.Ticker(market.provider_symbol(symbol))
    series = ticker.dividends
    currency = market.default_currency(symbol)
    with storage.connection() as conn:
        fundamental = conn.execute("SELECT data_json FROM fundamentals_cache WHERE symbol=?", (symbol,)).fetchone()
    if fundamental:
        currency = json.loads(fundamental["data_json"]).get("currency") or currency
    quote = storage.quote_rows().get(symbol)
    if quote:
        currency = quote["currency"]

    observations = []
    if series is not None:
        for timestamp, value in series.items():
            try:
                amount = float(value)
                if not math.isfinite(amount) or amount <= 0:
                    continue
                day = timestamp.date().isoformat()
                if day <= date.today().isoformat():
                    observations.append({"ex_date": day, "amount": amount})
            except (TypeError, ValueError, AttributeError):
                continue
    return observations, currency


def refresh_dividends(symbol: str, force: bool = False) -> dict:
    ttl = max(1, int(os.getenv("COTACOES_DIVIDENDS_TTL_HOURS", "24")))
    with storage.connection() as conn:
        row = conn.execute(
            "SELECT retrieved_at FROM dividend_refresh WHERE symbol=?", (symbol,)
        ).fetchone()
    if row and not force and _fresh(row["retrieved_at"], ttl):
        return {"status": "cached", **list_dividends(symbol)}
    observations, currency = _fetch_dividends(symbol)
    with storage.connection() as conn:
        conn.executemany("""
            INSERT INTO market_dividends(symbol,ex_date,amount,currency,provider)
            VALUES (?,?,?,?,'yfinance')
            ON CONFLICT(symbol,ex_date,provider) DO UPDATE SET
                amount=excluded.amount,currency=excluded.currency
        """, [(symbol, p["ex_date"], p["amount"], currency) for p in observations])
        conn.execute("""
            INSERT INTO dividend_refresh(symbol,retrieved_at) VALUES (?,?)
            ON CONFLICT(symbol) DO UPDATE SET retrieved_at=excluded.retrieved_at
        """, (symbol, storage.utc_now()))
    return {"status": "updated", **list_dividends(symbol)}


def list_dividends(symbol: str, days: int = 365) -> dict:
    if not 30 <= days <= 3650:
        raise ValueError("Periodo deve estar entre 30 e 3650 dias.")
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    last_year = (date.today() - timedelta(days=365)).isoformat()
    with storage.connection() as conn:
        rows = conn.execute("""
            SELECT ex_date,amount,currency,provider FROM market_dividends
            WHERE symbol=? AND ex_date>=? ORDER BY ex_date DESC
        """, (symbol, cutoff)).fetchall()
        last = conn.execute(
            "SELECT retrieved_at FROM dividend_refresh WHERE symbol=?", (symbol,)
        ).fetchone()
        total_row = conn.execute("""
            SELECT SUM(amount) FROM market_dividends
            WHERE symbol=? AND ex_date>=?
        """, (symbol, last_year)).fetchone()
    items = [dict(row) for row in rows]
    trailing = float(total_row[0] or 0.0)
    quote = storage.quote_rows().get(symbol)
    currency = items[0]["currency"] if items else market.default_currency(symbol)
    yield_pct = None
    if quote and quote["currency"] == currency and quote["close"] > 0 and last:
        yield_pct = round(100 * trailing / quote["close"], 4)
    return {
        "symbol": symbol, "period_days": days,
        "retrieved_at": last["retrieved_at"] if last else None,
        "items": items, "trailing_12m_per_unit": round(trailing, 8),
        "trailing_12m_yield_pct": yield_pct, "currency": currency,
        "note": "Ex-datas e valores por unidade reportados pelo provedor; podem ser incompletos. Nao sao recebimentos pessoais nem previsoes de rendimento.",
    }

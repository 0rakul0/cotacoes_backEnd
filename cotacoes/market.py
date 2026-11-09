"""Adaptador Yahoo Finance, isolado da API para facilitar testes e troca de provedor."""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone

SYMBOL_RE = re.compile(r"^[A-Z0-9^][A-Z0-9.^=-]{0,24}$")
B3_RE = re.compile(r"^[A-Z]{4}\d{1,2}$")


def normalize_symbol(raw: str) -> str:
    symbol = (raw or "").strip().upper()
    if symbol.endswith(":BVMF"):
        symbol = symbol[:-5]
    if symbol.endswith(".SA"):
        symbol = symbol[:-3]
    if not SYMBOL_RE.fullmatch(symbol):
        raise ValueError("Ticker invalido. Use PETR4, MXRF11, AAPL34, BTC-BRL ou AAPL.")
    return symbol


def provider_symbol(symbol: str) -> str:
    return symbol + ".SA" if B3_RE.fullmatch(symbol) else symbol


def default_currency(symbol: str) -> str:
    if B3_RE.fullmatch(symbol) or symbol.endswith("-BRL") or symbol == "^BVSP":
        return "BRL"
    if symbol.endswith("-USD") or re.fullmatch(r"[A-Z]{1,5}", symbol):
        return "USD"
    return "N/D"


def fetch_prices(symbol: str) -> tuple[list[dict], str]:
    """Consulta fechamentos diarios dos ultimos 5 anos; nao e um feed em tempo real."""
    import yfinance as yf

    ticker = yf.Ticker(provider_symbol(symbol))
    frame = ticker.history(period="5y", interval="1d", auto_adjust=False, actions=False)
    if frame is None or frame.empty or "Close" not in frame.columns:
        raise RuntimeError("O provedor nao retornou precos para este ticker.")

    data = []
    for timestamp, value in frame["Close"].items():
        try:
            close = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(close) or close <= 0:
            continue
        day = timestamp.date() if hasattr(timestamp, "date") else timestamp
        stamp = datetime(day.year, day.month, day.day, tzinfo=timezone.utc).isoformat()
        data.append({"observed_at": stamp, "close": close})
    if not data:
        raise RuntimeError("A consulta nao retornou precos validos.")

    currency = default_currency(symbol)
    try:
        found = ticker.fast_info.get("currency")
        if isinstance(found, str) and re.fullmatch(r"[A-Z]{3}", found.upper()):
            currency = found.upper()
    except Exception:
        pass
    return data, currency

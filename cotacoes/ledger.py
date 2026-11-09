"""Livro de operacoes e visao consolidada da carteira.

Compra e venda usam custo medio ponderado (inclusive taxas de compra).
Rendimentos efetivamente recebidos sao cadastrados separadamente.
"""
from __future__ import annotations

import decimal
import sqlite3
from datetime import datetime, timezone

from cotacoes import storage

D = decimal.Decimal
ZERO = D("0")
EPS = D("0.000000001")


def initialize() -> None:
    with storage.connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL CHECK(side IN ('BUY','SELL')),
            quantity TEXT NOT NULL,
            unit_price TEXT NOT NULL,
            fee TEXT NOT NULL,
            currency TEXT NOT NULL,
            traded_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_trades_symbol_date
            ON trades(symbol, traded_at, id);
        CREATE TABLE IF NOT EXISTS incomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('DIVIDEND','JCP','RENTAL','OTHER')),
            amount TEXT NOT NULL,
            withholding TEXT NOT NULL,
            currency TEXT NOT NULL,
            received_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_incomes_symbol_date
            ON incomes(symbol, received_at, id);
        """)


def canonical_time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Data da operacao deve incluir fuso horario.")
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def _n(value) -> D:
    d = D(str(value))
    if not d.is_finite():
        raise ValueError("Numeros devem ser finitos.")
    return d


def _get_trades(conn, symbol: str | None = None) -> list[dict]:
    if symbol:
        rows = conn.execute(
            "SELECT * FROM trades WHERE symbol = ? ORDER BY traded_at, id", (symbol,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM trades ORDER BY symbol, traded_at, id"
        ).fetchall()
    return [dict(row) for row in rows]


def _replay(rows: list[dict]) -> dict:
    """Reconstrucao deterministica; rejeita posicao negativa no instante da venda."""
    quantity = ZERO
    basis = ZERO
    realized = ZERO
    total_fees = ZERO
    for row in sorted(rows, key=lambda r: (r["traded_at"], r.get("id") or 10**18)):
        qty = _n(row["quantity"])
        unit = _n(row["unit_price"])
        fee = _n(row["fee"])
        if qty <= ZERO or unit <= ZERO or fee < ZERO:
            raise ValueError("Operacao com quantidade, preco ou taxa invalidos.")
        total_fees += fee
        if row["side"] == "BUY":
            basis += qty * unit + fee
            quantity += qty
        elif row["side"] == "SELL":
            if qty > quantity + EPS:
                raise ValueError("Venda excede a quantidade disponivel na data da operacao.")
            avg = basis / quantity if quantity else ZERO
            cost_sold = avg * qty
            basis -= cost_sold
            realized += qty * unit - fee - cost_sold
            quantity -= qty
            if abs(quantity) <= EPS:
                quantity = ZERO
                basis = ZERO
        else:
            raise ValueError("Tipo de operacao invalido.")
    return {"quantity": quantity, "basis": basis, "avg_cost": basis / quantity if quantity else ZERO,
            "realized_pnl": realized, "fees": total_fees}


def add_trade(symbol: str, side: str, quantity, unit_price, fee, currency: str,
              traded_at: datetime) -> dict:
    qty, price, fee_amount = _n(quantity), _n(unit_price), _n(fee)
    if not (ZERO < qty <= D("1000000000000")) or not (ZERO < price <= D("1000000000000")):
        raise ValueError("Quantidade e preco devem ser positivos e limitados.")
    if not ZERO <= fee_amount <= D("1000000000000"):
        raise ValueError("Taxa deve ser nao negativa.")
    if side not in ("BUY", "SELL"):
        raise ValueError("Operacao deve ser BUY ou SELL.")
    stamp = canonical_time(traded_at)
    if traded_at.astimezone(timezone.utc) > datetime.now(timezone.utc):
        raise ValueError("Data futura nao permitida.")
    with storage.connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = _get_trades(conn, symbol)
        if existing and any(row["currency"] != currency for row in existing):
            raise ValueError("Operacoes do mesmo ativo devem usar uma moeda consistente.")
        candidate = {
            "id": None, "symbol": symbol, "side": side, "quantity": str(qty),
            "unit_price": str(price), "fee": str(fee_amount),
            "currency": currency, "traded_at": stamp,
        }
        _replay(existing + [candidate])
        storage_stamp = storage.utc_now()
        cursor = conn.execute("""
            INSERT INTO trades(symbol,side,quantity,unit_price,fee,currency,traded_at,created_at)
            VALUES (?,?,?,?,?,?,?,?)
        """, (symbol, side, str(qty), str(price), str(fee_amount),
              currency, stamp, storage_stamp))
        trade_id = cursor.lastrowid
        conn.execute("INSERT OR IGNORE INTO assets(symbol,created_at) VALUES (?,?)",
                     (symbol, storage_stamp))
    return {**candidate, "id": trade_id}


def delete_trade(trade_id: int) -> bool:
    with storage.connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        old = conn.execute("SELECT symbol FROM trades WHERE id=?", (trade_id,)).fetchone()
        if not old:
            return False
        remaining = [row for row in _get_trades(conn, old["symbol"]) if row["id"] != trade_id]
        _replay(remaining)
        conn.execute("DELETE FROM trades WHERE id=?", (trade_id,))
    return True


def list_trades(symbol: str | None = None, limit: int = 200) -> list[dict]:
    with storage.connection() as conn:
        if symbol:
            rows = conn.execute("""
                SELECT * FROM trades WHERE symbol = ?
                ORDER BY traded_at DESC,id DESC LIMIT ?
            """, (symbol, limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM trades ORDER BY traded_at DESC,id DESC LIMIT ?
            """, (limit,)).fetchall()
    return [dict(row) for row in rows]


def add_income(symbol: str, kind: str, amount, withholding,
               currency: str, received_at: datetime) -> dict:
    gross, tax = _n(amount), _n(withholding)
    if kind not in ("DIVIDEND", "JCP", "RENTAL", "OTHER"):
        raise ValueError("Tipo de rendimento invalido.")
    if gross <= ZERO or tax < ZERO or tax > gross:
        raise ValueError("Rendimento deve ser positivo, com retencao entre zero e valor bruto.")
    stamp = canonical_time(received_at)
    if received_at.astimezone(timezone.utc) > datetime.now(timezone.utc):
        raise ValueError("Data futura nao permitida.")
    with storage.connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.execute("""
            INSERT INTO incomes(symbol,kind,amount,withholding,currency,received_at,created_at)
            VALUES (?,?,?,?,?,?,?)
        """, (symbol, kind, str(gross), str(tax), currency, stamp, storage.utc_now()))
        conn.execute("INSERT OR IGNORE INTO assets(symbol,created_at) VALUES (?,?)",
                     (symbol, storage.utc_now()))
    return {"id": cursor.lastrowid, "symbol": symbol, "kind": kind,
            "amount": str(gross), "withholding": str(tax), "currency": currency,
            "received_at": stamp}


def delete_income(income_id: int) -> bool:
    with storage.connection() as conn:
        return conn.execute("DELETE FROM incomes WHERE id=?", (income_id,)).rowcount > 0


def list_incomes(symbol: str | None = None, limit: int = 200) -> list[dict]:
    with storage.connection() as conn:
        if symbol:
            rows = conn.execute("""
                SELECT * FROM incomes WHERE symbol = ?
                ORDER BY received_at DESC,id DESC LIMIT ?
            """, (symbol, limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM incomes ORDER BY received_at DESC,id DESC LIMIT ?
            """, (limit,)).fetchall()
    return [dict(row) for row in rows]


def _f(value: D) -> float:
    return round(float(value), 8)


def portfolio_summary() -> dict:
    with storage.connection() as conn:
        trades = _get_trades(conn)
        incomes = [dict(row) for row in conn.execute("SELECT * FROM incomes")]
    ledger: dict[str, list[dict]] = {}
    for trade in trades:
        ledger.setdefault(trade["symbol"], []).append(trade)
    state_by_symbol = {symbol: _replay(rows) for symbol, rows in ledger.items()}
    currency_by_symbol = {symbol: rows[0]["currency"] for symbol, rows in ledger.items()}
    legacy_positions = {pos["symbol"]: pos for pos in storage.list_positions()}
    latest = storage.quote_rows()
    groups: dict[str, dict] = {}
    positions = []

    def group_of(currency: str) -> dict:
        return groups.setdefault(currency, {
            "currency": currency, "invested": 0.0, "market_value": 0.0,
            "pnl": 0.0, "realized_pnl": 0.0, "income_net": 0.0,
            "priced_positions": 0, "positions": 0,
        })

    for symbol, state in state_by_symbol.items():
        group = group_of(currency_by_symbol[symbol])
        group["realized_pnl"] += float(state["realized_pnl"])
    for entry in incomes:
        group_of(entry["currency"])["income_net"] += float(_n(entry["amount"]) - _n(entry["withholding"]))

    all_symbols = set(legacy_positions) | set(ledger)
    for symbol in sorted(all_symbols):
        if symbol in ledger:
            state = state_by_symbol[symbol]
            qty = state["quantity"]
            if qty <= ZERO:
                continue
            cost = state["avg_cost"]
            currency = currency_by_symbol[symbol]
            source = "transactions"
        else:
            manual = legacy_positions[symbol]
            qty, cost = _n(manual["quantity"]), _n(manual["avg_cost"])
            currency = manual["currency"]
            source = "manual"
        quote = latest.get(symbol)
        warning = None
        if quote and quote["currency"] != currency:
            warning = "Moeda do preco diferente da moeda de custo."
        elif not quote:
            warning = "Sem cotacao disponivel."
        price = _n(quote["close"]) if quote and warning is None else None
        invested = qty * cost
        mvalue = qty * price if price is not None else None
        pnl = mvalue - invested if mvalue is not None else None
        position = {
            "symbol": symbol, "quantity": _f(qty), "avg_cost": _f(cost),
            "currency": currency, "source": source,
            "invested": round(float(invested), 2),
            "last_price": _f(price) if price is not None else None,
            "market_value": round(float(mvalue), 2) if mvalue is not None else None,
            "pnl": round(float(pnl), 2) if pnl is not None else None,
            "pnl_pct": round(float(pnl / invested * 100), 2)
                       if pnl is not None and invested > ZERO else None,
            "price_date": quote["observed_at"] if quote else None, "warning": warning,
        }
        positions.append(position)
        group = group_of(currency)
        group["positions"] += 1
        group["invested"] += float(invested)
        if mvalue is not None:
            group["priced_positions"] += 1
            group["market_value"] += float(mvalue)
            group["pnl"] += float(pnl)

    for group in groups.values():
        for key in ("invested", "market_value", "pnl", "realized_pnl", "income_net"):
            group[key] = round(group[key], 2)
        group["complete"] = group["positions"] == group["priced_positions"]
    return {
        "positions": positions,
        "by_currency": sorted(groups.values(), key=lambda x: x["currency"]),
        "transactions": len(trades), "income_entries": len(incomes),
        "disclaimer": "Resultados realizados usam custo medio ponderado. Posicoes manuais sao substituidas por operacoes do mesmo ticker. Sem impostos e eventos corporativos automaticos.",
    }

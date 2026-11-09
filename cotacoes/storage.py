"""Persistencia SQLite para ativos, cotacoes e posicoes."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ASSETS = ("BTC-BRL", "PETR4", "MXRF11", "AAPL34", "AMZO34", "NVDC34")


def db_path() -> Path:
    return Path(os.getenv("COTACOES_DB_PATH", str(ROOT / "data" / "cotacoes.sqlite3"))).expanduser()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connection():
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 20000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize() -> bool:
    """Cria tabelas; retorna True se o arquivo do banco ainda nao existia."""
    new_database = not db_path().exists()
    with connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS assets (
            symbol TEXT PRIMARY KEY,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS prices (
            symbol TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            close REAL NOT NULL CHECK (close > 0),
            currency TEXT NOT NULL,
            source TEXT NOT NULL,
            PRIMARY KEY (symbol, observed_at)
        );
        CREATE INDEX IF NOT EXISTS ix_prices_symbol_date
            ON prices(symbol, observed_at DESC);
        CREATE TABLE IF NOT EXISTS refresh_state (
            symbol TEXT PRIMARY KEY,
            last_attempt TEXT NOT NULL,
            last_success TEXT,
            last_error TEXT
        );
        CREATE TABLE IF NOT EXISTS positions (
            symbol TEXT PRIMARY KEY,
            quantity REAL NOT NULL CHECK (quantity > 0),
            avg_cost REAL NOT NULL CHECK (avg_cost >= 0),
            currency TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """)
        if new_database and os.getenv("COTACOES_SEED_DEFAULTS", "1") == "1":
            conn.executemany(
                "INSERT OR IGNORE INTO assets(symbol, created_at) VALUES (?, ?)",
                [(symbol, utc_now()) for symbol in DEFAULT_ASSETS],
            )
    return new_database


def add_asset(symbol: str) -> bool:
    with connection() as conn:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO assets(symbol, created_at) VALUES (?, ?)",
            (symbol, utc_now()),
        )
        return cursor.rowcount > 0


def asset_exists(symbol: str) -> bool:
    with connection() as conn:
        return conn.execute("SELECT 1 FROM assets WHERE symbol = ?", (symbol,)).fetchone() is not None


def remove_asset(symbol: str) -> bool:
    """Nao apaga posicoes nem historico ao remover um ativo da lista."""
    with connection() as conn:
        return conn.execute("DELETE FROM assets WHERE symbol = ?", (symbol,)).rowcount > 0


def quote_rows() -> dict[str, dict]:
    with connection() as conn:
        rows = conn.execute("""
            SELECT p.symbol, p.close, p.observed_at, p.currency, p.source
            FROM prices p
            WHERE p.observed_at = (
                SELECT MAX(p2.observed_at) FROM prices p2 WHERE p2.symbol = p.symbol
            )
        """).fetchall()
        return {row["symbol"]: dict(row) for row in rows}


def list_assets() -> list[dict]:
    with connection() as conn:
        assets = [dict(row) for row in conn.execute(
            "SELECT symbol, created_at FROM assets ORDER BY symbol"
        )]
        states = {
            row["symbol"]: dict(row) for row in conn.execute(
                "SELECT symbol, last_attempt, last_success, last_error FROM refresh_state"
            )
        }
        latest = quote_rows()
        for asset in assets:
            symbol = asset["symbol"]
            asset["quote"] = latest.get(symbol)
            asset["refresh"] = states.get(symbol)
        return assets


def price_count(symbol: str) -> int:
    with connection() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM prices WHERE symbol = ?", (symbol,)
        ).fetchone()[0]


def save_prices(symbol: str, prices: list[dict], currency: str, source: str) -> int:
    if not prices:
        return 0
    with connection() as conn:
        conn.executemany("""
            INSERT INTO prices (symbol, observed_at, close, currency, source)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (symbol, observed_at) DO UPDATE SET
                close = excluded.close,
                currency = excluded.currency,
                source = excluded.source
        """, [
            (symbol, p["observed_at"], p["close"], currency, source)
            for p in prices
        ])
    return len(prices)


def history(symbol: str, cutoff: str | None, limit: int = 2500) -> list[dict]:
    with connection() as conn:
        if cutoff:
            rows = conn.execute("""
                SELECT observed_at, close, currency, source
                FROM prices WHERE symbol = ? AND observed_at >= ?
                ORDER BY observed_at DESC LIMIT ?
            """, (symbol, cutoff, limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT observed_at, close, currency, source
                FROM prices WHERE symbol = ?
                ORDER BY observed_at DESC LIMIT ?
            """, (symbol, limit)).fetchall()
    return list(reversed([dict(row) for row in rows]))


def read_refresh(symbol: str) -> dict | None:
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM refresh_state WHERE symbol = ?", (symbol,)
        ).fetchone()
        return dict(row) if row else None


def save_refresh(symbol: str, error: str | None) -> None:
    stamp = utc_now()
    with connection() as conn:
        conn.execute("""
            INSERT INTO refresh_state(symbol, last_attempt, last_success, last_error)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                last_attempt=excluded.last_attempt,
                last_success=COALESCE(excluded.last_success, refresh_state.last_success),
                last_error=excluded.last_error
        """, (symbol, stamp, stamp if error is None else None, error))


def save_position(symbol: str, quantity: float, avg_cost: float, currency: str) -> None:
    with connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO assets(symbol, created_at) VALUES (?, ?)",
            (symbol, utc_now()),
        )
        conn.execute("""
            INSERT INTO positions(symbol, quantity, avg_cost, currency, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                quantity=excluded.quantity,
                avg_cost=excluded.avg_cost,
                currency=excluded.currency,
                updated_at=excluded.updated_at
        """, (symbol, quantity, avg_cost, currency, utc_now()))


def remove_position(symbol: str) -> bool:
    with connection() as conn:
        return conn.execute(
            "DELETE FROM positions WHERE symbol = ?", (symbol,)
        ).rowcount > 0


def list_positions() -> list[dict]:
    latest = quote_rows()
    with connection() as conn:
        rows = [dict(row) for row in conn.execute(
            "SELECT * FROM positions ORDER BY symbol"
        )]
    for row in rows:
        row["quote"] = latest.get(row["symbol"])
    return rows

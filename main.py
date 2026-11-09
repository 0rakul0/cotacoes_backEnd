"""API de cotacoes, carteira, risco historico e indicadores financeiros."""
from __future__ import annotations

import hmac
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from cotacoes import allocation, analysis, fundamentals, ledger, market, service, storage

app = FastAPI(
    title="Cotacoes API",
    version="0.3.0",
    description="Acompanhamento financeiro e analise historica. Nao e recomendacao de investimento.",
)
FRONTEND = Path(
    os.getenv("COTACOES_FRONTEND_DIR", str(Path(__file__).resolve().parent / "frontend"))
).resolve()


@app.on_event("startup")
def startup():
    storage.initialize()
    ledger.initialize()
    fundamentals.initialize()


@app.middleware("http")
async def optional_api_key(request: Request, call_next):
    """Protege inclusive consultas a carteira quando COTACOES_API_TOKEN esta definido."""
    expected = os.getenv("COTACOES_API_TOKEN", "")
    if expected and request.url.path.startswith("/api/") and request.url.path != "/api/health":
        supplied = request.headers.get("X-API-Key", "")
        if not hmac.compare_digest(supplied, expected):
            return JSONResponse({"detail": "Chave de API ausente ou invalida."}, status_code=401)
    return await call_next(request)


if FRONTEND.is_dir():
    app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")


class AssetPayload(BaseModel):
    symbol: str


class PositionPayload(BaseModel):
    symbol: str
    quantity: float = Field(gt=0, le=1e12, allow_inf_nan=False)
    avg_cost: float = Field(ge=0, le=1e12, allow_inf_nan=False)
    currency: str = Field(default="BRL", pattern=r"^[A-Z]{3}$")


class TradePayload(BaseModel):
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: Decimal = Field(gt=0, le=Decimal("1000000000000"))
    unit_price: Decimal = Field(gt=0, le=Decimal("1000000000000"))
    fee: Decimal = Field(default=Decimal("0"), ge=0)
    currency: str = Field(default="BRL", pattern=r"^[A-Z]{3}$")
    traded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class IncomePayload(BaseModel):
    symbol: str
    kind: Literal["DIVIDEND", "JCP", "RENTAL", "OTHER"] = "DIVIDEND"
    amount: Decimal = Field(gt=0, le=Decimal("1000000000000"))
    withholding: Decimal = Field(default=Decimal("0"), ge=0)
    currency: str = Field(default="BRL", pattern=r"^[A-Z]{3}$")
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def valid_symbol(raw: str) -> str:
    try:
        return market.normalize_symbol(raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def tracked(raw: str) -> str:
    symbol = valid_symbol(raw)
    if not storage.asset_exists(symbol):
        raise HTTPException(status_code=404, detail="Ativo nao acompanhado.")
    return symbol


def user_error(exc: Exception):
    raise HTTPException(status_code=422, detail=str(exc)) from exc


def provider_error(exc: Exception):
    raise HTTPException(status_code=502, detail=f"Falha no provedor: {str(exc)[:200]}") from exc


@app.get("/", include_in_schema=False)
def home():
    index = FRONTEND / "index.html"
    if index.is_file():
        return FileResponse(index)
    return {"name": "Cotacoes API", "docs": "/docs",
            "hint": "Configure COTACOES_FRONTEND_DIR para servir o dashboard."}


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.3.0"}


@app.get("/api/assets")
def list_assets():
    return {"items": storage.list_assets()}


@app.post("/api/assets", status_code=201)
def add_asset(payload: AssetPayload):
    symbol = valid_symbol(payload.symbol)
    if not storage.add_asset(symbol):
        raise HTTPException(status_code=409, detail="Ativo ja cadastrado.")
    return {"symbol": symbol, "created": True}


@app.delete("/api/assets/{symbol}")
def delete_asset(symbol: str):
    symbol = valid_symbol(symbol)
    if not storage.remove_asset(symbol):
        raise HTTPException(status_code=404, detail="Ativo nao encontrado.")
    return {"symbol": symbol, "deleted": True}


@app.get("/api/assets/{symbol}/history")
def asset_history(symbol: str, period: str = Query("6mo")):
    try:
        return service.history(valid_symbol(symbol), period)
    except ValueError as exc:
        user_error(exc)


@app.post("/api/assets/{symbol}/refresh")
def refresh_asset(symbol: str, force: bool = Query(False)):
    symbol = tracked(symbol)
    result = service.refresh(symbol, force)
    if result["status"] == "error":
        raise HTTPException(status_code=502, detail=result)
    return result


@app.get("/api/assets/{symbol}/fundamentals")
def asset_fundamentals(symbol: str):
    return fundamentals.cached_indicators(valid_symbol(symbol))


@app.post("/api/assets/{symbol}/fundamentals/refresh")
def refresh_fundamentals(symbol: str, force: bool = Query(False)):
    symbol = tracked(symbol)
    try:
        return fundamentals.refresh_indicators(symbol, force)
    except Exception as exc:
        provider_error(exc)


@app.get("/api/assets/{symbol}/dividends")
def dividends(symbol: str, days: int = Query(365, ge=30, le=3650)):
    return fundamentals.list_dividends(valid_symbol(symbol), days)


@app.post("/api/assets/{symbol}/dividends/refresh")
def refresh_dividends(symbol: str, force: bool = Query(False)):
    symbol = tracked(symbol)
    try:
        return fundamentals.refresh_dividends(symbol, force)
    except Exception as exc:
        provider_error(exc)


@app.get("/api/analysis/risk/{symbol}")
def asset_risk(symbol: str, days: int = Query(365, ge=30, le=3650),
               confidence: float = Query(0.95, ge=0.8, le=0.99)):
    try:
        return analysis.asset_risk(valid_symbol(symbol), days, confidence)
    except ValueError as exc:
        user_error(exc)


@app.get("/api/analysis/events/{symbol}")
def asset_events(symbol: str, days: int = Query(365, ge=30, le=3650),
                 threshold_pct: float = Query(2.0, ge=0.1, le=100)):
    try:
        return analysis.events(valid_symbol(symbol), days, threshold_pct)
    except ValueError as exc:
        user_error(exc)


@app.get("/api/analysis/correlation")
def correlation(symbols: str = Query(..., description="Tickers separados por virgula"),
                days: int = Query(365, ge=30, le=3650),
                rolling_days: int = Query(30, ge=20, le=252)):
    try:
        symbols_list = [valid_symbol(s) for s in symbols.split(",")]
        return analysis.correlation_matrix(symbols_list, days, rolling_days)
    except ValueError as exc:
        user_error(exc)


@app.get("/api/analysis/allocation")
def portfolio_allocation():
    return allocation.allocation()


@app.get("/api/analysis/portfolio-risk")
def portfolio_risk(days: int = Query(365, ge=30, le=3650),
                   confidence: float = Query(0.95, ge=0.8, le=0.99)):
    try:
        return analysis.portfolio_risk(ledger.portfolio_summary()["positions"], days, confidence)
    except ValueError as exc:
        user_error(exc)


@app.get("/api/portfolio")
def portfolio():
    return ledger.portfolio_summary()


@app.put("/api/portfolio/positions")
def set_position(payload: PositionPayload):
    symbol = valid_symbol(payload.symbol)
    storage.save_position(symbol, payload.quantity, payload.avg_cost, payload.currency)
    return {"symbol": symbol, "saved": True,
            "warning": "Se houver operacoes registradas para este ticker, prevalece o livro de operacoes."}


@app.delete("/api/portfolio/positions/{symbol}")
def delete_position(symbol: str):
    symbol = valid_symbol(symbol)
    if not storage.remove_position(symbol):
        raise HTTPException(status_code=404, detail="Posicao manual nao encontrada.")
    return {"symbol": symbol, "deleted": True}


@app.get("/api/portfolio/trades")
def list_trades(symbol: str | None = Query(None), limit: int = Query(200, ge=1, le=1000)):
    return {"items": ledger.list_trades(valid_symbol(symbol) if symbol else None, limit)}


@app.post("/api/portfolio/trades", status_code=201)
def add_trade(payload: TradePayload):
    try:
        return ledger.add_trade(
            valid_symbol(payload.symbol), payload.side, payload.quantity,
            payload.unit_price, payload.fee, payload.currency, payload.traded_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.delete("/api/portfolio/trades/{trade_id}")
def delete_trade(trade_id: int):
    try:
        if not ledger.delete_trade(trade_id):
            raise HTTPException(status_code=404, detail="Operacao nao encontrada.")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"id": trade_id, "deleted": True}


@app.get("/api/portfolio/incomes")
def list_incomes(symbol: str | None = Query(None), limit: int = Query(200, ge=1, le=1000)):
    return {"items": ledger.list_incomes(valid_symbol(symbol) if symbol else None, limit)}


@app.post("/api/portfolio/incomes", status_code=201)
def add_income(payload: IncomePayload):
    try:
        return ledger.add_income(
            valid_symbol(payload.symbol), payload.kind, payload.amount,
            payload.withholding, payload.currency, payload.received_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.delete("/api/portfolio/incomes/{income_id}")
def delete_income(income_id: int):
    if not ledger.delete_income(income_id):
        raise HTTPException(status_code=404, detail="Rendimento nao encontrado.")
    return {"id": income_id, "deleted": True}


@app.get("/get_data", deprecated=True)
def old_endpoint():
    return {"body": "API ativa. Consulte /api/assets e /docs."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=7777)

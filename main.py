"""API de cotacoes e carteira."""
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from cotacoes import market, service, storage

app = FastAPI(title="Cotacoes API", version="0.2.0")
FRONTEND = Path(os.getenv("COTACOES_FRONTEND_DIR", str(Path(__file__).resolve().parent / "frontend"))).resolve()

@app.on_event("startup")
def startup():
    storage.initialize()

if FRONTEND.is_dir():
    app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")

class AssetPayload(BaseModel):
    symbol: str

class PositionPayload(BaseModel):
    symbol: str
    quantity: float = Field(gt=0, allow_inf_nan=False)
    avg_cost: float = Field(ge=0, allow_inf_nan=False)
    currency: str = Field(default="BRL", pattern=r"^[A-Z]{3}$")

def valid_symbol(raw):
    try:
        return market.normalize_symbol(raw)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

@app.get("/", include_in_schema=False)
def home():
    path = FRONTEND / "index.html"
    if path.is_file():
        return FileResponse(path)
    return {"name": "Cotacoes API", "docs": "/docs", "hint": "Configure COTACOES_FRONTEND_DIR."}

@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.2.0"}

@app.get("/api/assets")
def list_assets():
    return {"items": storage.list_assets()}

@app.post("/api/assets", status_code=201)
def add_asset(data: AssetPayload):
    symbol = valid_symbol(data.symbol)
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
def history(symbol: str, period: str = Query("6mo")):
    try:
        return service.history(valid_symbol(symbol), period)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

@app.post("/api/assets/{symbol}/refresh")
def refresh(symbol: str, force: bool = Query(False)):
    symbol = valid_symbol(symbol)
    if not storage.asset_exists(symbol):
        raise HTTPException(status_code=404, detail="Ativo nao encontrado.")
    result = service.refresh(symbol, force)
    if result["status"] == "error":
        raise HTTPException(status_code=502, detail=result)
    return result

@app.get("/api/portfolio")
def portfolio():
    return service.portfolio_summary()

@app.put("/api/portfolio/positions")
def set_position(data: PositionPayload):
    symbol = valid_symbol(data.symbol)
    storage.save_position(symbol, data.quantity, data.avg_cost, data.currency)
    return {"symbol": symbol, "saved": True}

@app.delete("/api/portfolio/positions/{symbol}")
def delete_position(symbol: str):
    symbol = valid_symbol(symbol)
    if not storage.remove_position(symbol):
        raise HTTPException(status_code=404, detail="Posicao nao encontrada.")
    return {"symbol": symbol, "deleted": True}

@app.get("/get_data", deprecated=True)
def old_endpoint():
    return {"body": "API ativa. Consulte /api/assets e /docs."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=7777)

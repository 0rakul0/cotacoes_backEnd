from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import uvicorn
from cotacoes.grafico import gerar_grafico_html

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.get("/get_data")
async def get_data():
    return {"body": "Texto vindo do back-end"}

@app.get("/ticker/{ticker}", response_class=HTMLResponse)
async def grafico_ticker(ticker: str):
    try:
        # Chama a função para gerar o HTML com o gráfico do ticker
        html = gerar_grafico_html(ticker)
        return HTMLResponse(content=html, status_code=200)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="localhost", port=7777)

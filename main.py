from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.get("/get_data")
async def get_data():
    return {"body": "texto vindo do back end"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7777)
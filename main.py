from fastapi import FastAPI
from src.config import settings
from src.strategy import check_and_decide
from src.database import engine, Base, get_db
from src.models import Trade
from sqlalchemy.orm import Session
from fastapi import Depends

# Crear las tablas en la base de datos al iniciar
Base.metadata.create_all(bind=engine)

app = FastAPI()

@app.get("/status")
def get_status():
    return {"status": "UP"}

@app.get("/trade/analyze/{symbol}")
async def analyze_symbol(symbol: str):
    """
    Analyzes a symbol and returns data from Binance TestNet.
    """
    result = await check_and_decide(symbol.upper())
    return result

@app.on_event("startup")
async def startup_event():
    print("FastAPI application starting up...")
    print(f"Host: {settings.uvicorn_host}")
    print(f"Port: {settings.uvicorn_port}")

@app.on_event("shutdown")
async def shutdown_event():
    print("FastAPI application shutting down...")

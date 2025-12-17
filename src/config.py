from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import Literal

class Settings(BaseSettings):
    # --- Binance API Credentials ---
    binance_api_key: str
    binance_secret_key: str

    # --- Trading Parameters ---
    trade_symbol: str = "BTCUSDT"
    trade_interval: str = "4h"
    trade_sl_percentage: float = 0.02 # Porcentaje de Stop-Loss (ej. 0.02 = 2%)
    
    # --- Strategy Selection ---
    # Estrategia a utilizar: "conservative" (cantidad fija) o "aggressive" (porcentaje de riesgo)
    trading_strategy: Literal["conservative", "aggressive"] = "conservative"

    # --- Conservative Strategy Parameters ---
    trade_quantity: float = 0.003 # Cantidad fija para la estrategia conservadora

    # --- Aggressive Strategy Parameters ---
    trade_risk_percentage: float = 1.0 # Porcentaje del balance a arriesgar (ej. 1.0 = 1%)
    trade_max_holding_hours: int = 24 # Horas máximas para mantener una posición

    # --- Server Configuration ---
    uvicorn_host: str = "0.0.0.0"
    uvicorn_port: int = 8000

    @field_validator('binance_api_key', 'binance_secret_key')
    @classmethod
    def check_not_empty(cls, v: str, field) -> str:
        if not v:
            raise ValueError(
                f"{field.name} no puede estar vacía. "
                "Por favor, añade tus claves en el archivo .env"
            )
        return v

    class Config:
        env_file = ".env"

settings = Settings()
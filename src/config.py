from pydantic_settings import BaseSettings
from pydantic import field_validator

class Settings(BaseSettings):
    # --- Binance API Credentials ---
    binance_api_key: str
    binance_secret_key: str

    # --- Trading Parameters ---
    trade_symbol: str = "BTCUSDT"
    trade_quantity: float = 0.003
    trade_interval: str = "4h"
    trade_sl_percentage: float = 0.02 # Porcentaje de Stop-Loss (ej. 0.02 = 2%)

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
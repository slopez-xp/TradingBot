from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import Literal

class Settings(BaseSettings):
    # --- Binance API Credentials ---
    binance_api_key: str
    binance_secret_key: str

    # --- PostgreSQL Database ---
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str = "db"
    postgres_port: int = 5432

    # --- Trading Parameters ---
    trade_symbol: str = "BTCUSDT"
    trade_interval: str = "4h"
    trade_sl_percentage: float = 0.02 # Stop-Loss percentage (e.g., 0.02 = 2%)

    # --- Bollinger Bands ---
    bb_length: int = 20
    bb_std: float = 2.0

    # --- RSI ---
    rsi_length: int = 14
    rsi_buy_threshold: int = 48
    rsi_sell_threshold: int = 52

    # --- Volume Filter ---
    volume_avg_period: int = 10

    # --- Trailing Stop-Loss ---
    trailing_stop_enabled: bool = True
    trailing_stop_callback: float = 0.005 # Callback for the TSL (e.g., 0.005 = 0.5%)
    
    # --- Strategy Selection ---
    # Strategy to use: "conservative" (fixed amount) or "aggressive" (risk percentage)
    trading_strategy: Literal["conservative", "aggressive"] = "conservative"

    # --- Conservative Strategy Parameters ---
    trade_quantity: float = 0.003 # Fixed amount for the conservative strategy

    # --- Aggressive Strategy Parameters ---
    trade_risk_percentage: float = 1.0 # Percentage of balance to risk (e.g., 1.0 = 1%)
    trade_max_holding_hours: int = 24 # Maximum hours to hold a position

    # --- Server Configuration ---
    uvicorn_host: str = "0.0.0.0"
    uvicorn_port: int = 8000

    @field_validator('binance_api_key', 'binance_secret_key')
    @classmethod
    def check_not_empty(cls, v: str, field) -> str:
        if not v:
            raise ValueError(
                f"{field.name} cannot be empty. "
                "Please add your keys to the .env file"
            )
        return v

    class Config:
        env_file = ".env"

settings = Settings()
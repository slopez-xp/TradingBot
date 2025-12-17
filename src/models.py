from sqlalchemy import Column, Integer, String, Float, DateTime
from datetime import datetime
from .database import Base

class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)          # Ej: BTCUSDT
    strategy = Column(String)                    # Ej: SMA_CROSSOVER
    decision = Column(String)                    # BUY o SELL
    price = Column(Float)                        # Precio al que se ejecutó
    quantity = Column(Float)                     # Cantidad simulada
    timestamp = Column(DateTime, default=datetime.utcnow) # Fecha y hora

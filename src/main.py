import math
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi.responses import Response
from .strategy import check_and_decide, execute_trade, startup_cleanup, close_all_positions
from .database import engine, Base, get_db
from .models import Trade
from .config import settings

# Simple SVG favicon content
FAVICON_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="green">
  <circle cx="8" cy="8" r="8" />
</svg>
"""

# --- Eventos de Inicio y Apagado ---

app = FastAPI()

@app.on_event("startup")
async def on_startup():
    """Se ejecuta al iniciar el servidor."""
    print("--- El servidor de la API se está iniciando ---")
    Base.metadata.create_all(bind=engine)
    startup_cleanup(settings.trade_symbol)
    print("--- Servidor iniciado exitosamente ---")

@app.on_event("shutdown")
async def on_shutdown():
    """Se ejecuta al apagar el servidor."""
    print("--- El servidor de la API se está apagando ---")
    close_all_positions(settings.trade_symbol)
    print("--- Servidor apagado exitosamente ---")


# --- Endpoints de la API ---

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(content=FAVICON_SVG, media_type="image/svg+xml")

@app.get("/trade/analyze")
def analyze():
    """Solo analiza, no guarda nada en la BD."""
    return check_and_decide(settings.trade_symbol)

@app.get("/trade/execute")
def auto_trade(db: Session = Depends(get_db)):
    """
    Analiza el símbolo configurado, ejecuta la orden y guarda el registro.
    """
    # 1. Usar el símbolo de la configuración
    symbol = settings.trade_symbol

    # 2. Ejecutar estrategia de análisis
    analysis = check_and_decide(symbol)
    
    # Manejar errores de la API o del análisis
    if "error" in analysis:
        raise HTTPException(status_code=500, detail=f"Fallo en el análisis: {analysis['error']}")

    decision = analysis["decision"]
    price = float(analysis["last_close_price"])
    quantity_to_trade = analysis["calculated_quantity"] # CORRECCIÓN: Usar cantidad calculada
    current_pos_amt = analysis["current_position_amount"]

    # 3. Si es HOLD, no hacemos nada
    if decision == "HOLD":
        return {
            "status": "Market scanned, no trade executed (HOLD)",
            "data": analysis
        }

    # 4. Ejecutar la orden real con la cantidad y decisión del análisis
    # CORRECCIÓN: Pasar todos los argumentos necesarios a execute_trade
    execution_result = execute_trade(symbol, decision, quantity_to_trade, current_pos_amt)

    if not execution_result:
        # Esto puede pasar si hay un error no capturado o una condición que no retorna nada
        raise HTTPException(status_code=500, detail="Fallo la ejecución del trade por una razón desconocida.")

    if execution_result.get("status") == "ignored":
        # Esto sucede si la lógica de trading decide no operar (ej. ya en posición)
        return {
            "status": f"Trade execution condition not met: {execution_result.get('reason')}",
            "data": analysis
        }

    if "error" in execution_result:
        # Si la ejecución falló (ej. cantidad muy baja, o clave API incorrecta)
        raise HTTPException(status_code=500, detail=f"Fallo al ejecutar orden: {execution_result['error']}")
    
    # 5. Si es BUY o SELL y la ejecución fue exitosa, guardamos en la BD
    new_trade = Trade(
        symbol=symbol,
        strategy=analysis["strategy"],
        decision=decision,
        price=price,
        quantity=quantity_to_trade, # CORRECCIÓN: Usar la cantidad correcta
    )
    
    db.add(new_trade)
    db.commit()
    db.refresh(new_trade)
    
    return {
        "status": f"Trade Executed on Binance ({decision}) & Saved to DB",
        "trade_id": new_trade.id,
        "binance_response": execution_result,
        "data": analysis
    }

@app.get("/db/trades")
def get_trades(db: Session = Depends(get_db)):
    """
    Recupera todas las operaciones guardadas en la Base de Datos.
    """
    trades = db.query(Trade).all()
    return trades
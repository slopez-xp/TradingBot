import math
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi.responses import Response
from .strategy import (
    check_and_decide, 
    execute_trade, 
    startup_cleanup, 
    close_all_positions,
    update_trailing_stop_loss
)
from .database import engine, Base, get_db
from .models import Trade, StatusLog
from .config import settings

# Simple SVG favicon content
FAVICON_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="green">
  <circle cx="8" cy="8" r="8" />
</svg>
"""

# --- Startup and Shutdown Events ---

app = FastAPI()

@app.on_event("startup")
async def on_startup():
    """Runs when the server starts."""
    print("--- The API server is starting up ---")
    Base.metadata.create_all(bind=engine)
    startup_cleanup(settings.trade_symbol)
    print("--- Server started successfully ---")

@app.on_event("shutdown")
async def on_shutdown():
    """Runs when the server shuts down."""
    print("--- The API server is shutting down ---")
    close_all_positions(settings.trade_symbol)
    print("--- Server shut down successfully ---")


# --- API Endpoints ---

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(content=FAVICON_SVG, media_type="image/svg+xml")

@app.get("/trade/analyze")
def analyze():
    """Only analyzes, does not save anything to the DB."""
    return check_and_decide(settings.trade_symbol)

@app.get("/trade/execute")
def auto_trade(db: Session = Depends(get_db)):
    """
    Analyzes the configured symbol, executes the order, and saves the record.
    """
    # 1. Use the symbol from the configuration
    symbol = settings.trade_symbol

    # 2. Execute analysis strategy
    analysis = check_and_decide(symbol)
    
    # Handle API or analysis errors
    if "error" in analysis:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {analysis['error']}")

    decision = analysis["decision"]
    # Extract rsi and usdt_balance from analysis. If they don't exist, assign None.
    rsi_value = analysis.get("rsi")
    usdt_balance = analysis.get("usdt_balance")
    last_close_price = analysis.get("last_close_price")

    # Convert numpy values to native Python floats before saving
    # This prevents type errors with the database (psycopg2)
    db_close_price = float(last_close_price) if last_close_price is not None else None
    db_rsi_value = float(rsi_value) if rsi_value is not None else None
    db_usdt_balance = float(usdt_balance) if usdt_balance is not None else None

    # Save the StatusLog (always, regardless of the decision)
    new_status_log = StatusLog(
        timestamp=datetime.utcnow(),
        strategy=analysis["strategy"],
        signal=decision,
        close_price=db_close_price,
        rsi=db_rsi_value,
        balance_usdt=db_usdt_balance
    )
    db.add(new_status_log)
    db.commit()
    db.refresh(new_status_log)

    price = float(last_close_price) # Use last_close_price as it has been defined
    quantity_to_trade = analysis["calculated_quantity"]
    current_pos_amt = analysis["current_position_amount"]

    # 3. If it's HOLD, do nothing
    if decision == "HOLD":
        return {
            "status": "Market scanned, no trade executed (HOLD)",
            "data": analysis
        }

    # 4. Execute the real order with the quantity and decision from the analysis
    # FIX: Pass all necessary arguments to execute_trade
    execution_result = execute_trade(symbol, decision, quantity_to_trade, current_pos_amt)

    if not execution_result:
        # This can happen if there is an uncaptured error or a condition that returns nothing
        raise HTTPException(status_code=500, detail="Trade execution failed for an unknown reason.")

    if execution_result.get("status") == "ignored":
        # This happens if the trading logic decides not to trade (e.g., already in a position)
        return {
            "status": f"Trade execution condition not met: {execution_result.get('reason')}",
            "data": analysis
        }

    if "error" in execution_result:
        # If the execution failed (e.g., amount too low, or incorrect API key)
        raise HTTPException(status_code=500, detail=f"Failed to execute order: {execution_result['error']}")
    
    # 5. If it's BUY or SELL and the execution was successful, save to the DB
    new_trade = Trade(
        symbol=symbol,
        strategy=analysis["strategy"],
        decision=decision,
        price=price,
        quantity=quantity_to_trade, # FIX: Use the correct quantity
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

@app.get("/trade/update-tsl")
def tsl_update():
    """
    Checks and updates the Trailing Stop-Loss if the conditions are met.
    """
    if not settings.trailing_stop_enabled:
        return {"status": "Trailing Stop-Loss is disabled in settings."}
        
    symbol = settings.trade_symbol
    result = update_trailing_stop_loss(symbol)
    
    if "error" in result:
        raise HTTPException(status_code=500, detail=f"TSL failed: {result['error']}")
        
    return result

@app.get("/db/trades")
def get_trades(db: Session = Depends(get_db)):
    """
    Retrieves all saved operations from the Database.
    """
    trades = db.query(Trade).all()
    return trades
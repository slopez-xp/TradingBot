import os
import pandas as pd
import pandas_ta as ta
import time
from datetime import datetime, timezone
from binance.client import Client
from binance.enums import SIDE_BUY, SIDE_SELL, ORDER_TYPE_MARKET, FUTURE_ORDER_TYPE_STOP_MARKET
from binance.exceptions import BinanceAPIException
from src.config import settings

# --- Client Configuration ---
client = Client(settings.binance_api_key, settings.binance_secret_key, testnet=True)
client.FUTURES_URL = 'https://testnet.binancefuture.com/fapi'

# --- Helper Functions ---

def _get_usdt_balance() -> float:
    """Gets the available USDT balance in the futures account."""
    try:
        balances = client.futures_account_balance()
        for balance in balances:
            if balance['asset'] == 'USDT':
                return float(balance['availableBalance'])
        return 0.0
    except BinanceAPIException as e:
        print(f"Error getting USDT balance: {e}")
        return 0.0

def _calculate_aggressive_quantity(symbol: str, usdt_balance: float) -> float:
    """Calculates the quantity to trade based on a percentage of the balance."""
    if usdt_balance == 0:
        return 0.0
    
    try:
        mark_price = float(client.futures_mark_price(symbol=symbol)['markPrice'])
        risk_per_trade = usdt_balance * (settings.trade_risk_percentage / 100)
        quantity = risk_per_trade / mark_price
        return round(quantity, 3)
    except BinanceAPIException as e:
        print(f"Error calculating quantity for aggressive strategy: {e}")
        return 0.0

def get_market_data(symbol: str):
    """Gets historical market data."""
    klines = client.futures_klines(symbol=symbol, interval=settings.trade_interval, limit=50)
    df = pd.DataFrame(klines, columns=[
        'Open Time', 'Open', 'High', 'Low', 'Close', 'Volume', 'Close Time', 
        'Quote Asset Volume', 'Number of Trades', 'Taker Buy Base Asset Volume', 
        'Taker Buy Quote Asset Volume', 'Ignore'
    ])
    df['Close'] = pd.to_numeric(df['Close'])
    df['Volume'] = pd.to_numeric(df['Volume'])
    df['Open Time'] = pd.to_datetime(df['Open Time'], unit='ms', utc=True)
    return df

# --- Main Strategy Logic ---

def check_and_decide(symbol: str):
    """
    Main function that decides the trading action based on the selected strategy.
    It does NOT execute orders, only analyzes and returns the decision.
    """
    print(f"\n[{datetime.now(timezone.utc).isoformat()}] Checking strategy '{settings.trading_strategy}' for {symbol}...")

    try:
        positions = client.futures_position_information(symbol=symbol)
        position = next((p for p in positions if p['symbol'] == symbol), None)
        current_position_amt = float(position['positionAmt']) if position else 0
    except BinanceAPIException as e:
        print(f"Error getting position information: {e}")
        return {"error": "Failed to get current position."}

    # Get market data for calculations
    df = get_market_data(symbol)
    last_close = df['Close'].iloc[-1]

    # For the aggressive strategy, if a position is already open, it can be closed by time
    if settings.trading_strategy == 'aggressive' and current_position_amt != 0:
        position_closed_by_time = _handle_time_based_exit(symbol, position)
        if position_closed_by_time:
            # If the position was closed, we don't make a new decision until the next cycle
            return {"decision": "HOLD", "status": "Position closed due to time limit."}

    # --- Strategy Decision Logic ---
    usdt_balance = None
    rsi_value = None
    decision = "HOLD" # Initialize decision to a default value

    if settings.trading_strategy == 'aggressive':
        usdt_balance = _get_usdt_balance()
        trade_quantity = _calculate_aggressive_quantity(symbol, usdt_balance)
        print(f"Aggressive Strategy: USDT Balance: {usdt_balance:.2f}. Calculated Quantity: {trade_quantity} {symbol.replace('USDT', '')}.")
        
        # --- Aggressive RSI-based Strategy ---
        df.ta.rsi(length=settings.rsi_length, append=True)
        rsi_col = next((col for col in df.columns if col.startswith('RSI_')), None)
        if not rsi_col:
            print("Error: RSI column not found in DataFrame.")
            return {"error": "Failed to calculate RSI indicator."}
        
        rsi_value = df[rsi_col].iloc[-1]
        
        # Buy Condition: RSI indicates oversold
        if rsi_value < settings.rsi_buy_threshold:
            decision = "BUY"
        # Sell Condition: RSI indicates overbought
        elif rsi_value > settings.rsi_sell_threshold:
            decision = "SELL"
        
        print(f"Signal decision '{decision}'. Close: {last_close}, RSI: {rsi_value:.2f}")

    elif settings.trading_strategy == 'conservative':
        trade_quantity = settings.trade_quantity
        print(f"Conservative Strategy: Using fixed quantity of {trade_quantity} {symbol.replace('USDT', '')}.")

        # --- Conservative Strategy based on Bollinger Bands and Volume ---
        df.ta.bbands(length=settings.bb_length, std=settings.bb_std, append=True)
        df['volume_avg'] = df['Volume'].rolling(window=settings.volume_avg_period).mean()

        bbu_col = next((col for col in df.columns if col.startswith('BBU_')), None)
        bbl_col = next((col for col in df.columns if col.startswith('BBL_')), None)

        if not bbu_col or not bbl_col:
            print("Error: Bollinger Bands columns ('BBU_' or 'BBL_') not found in DataFrame.")
            return {"error": "Failed to calculate Bollinger Bands indicators."}

        last_bbu = df[bbu_col].iloc[-1]
        last_bbl = df[bbl_col].iloc[-1]
        last_volume = df['Volume'].iloc[-1]
        avg_volume = df['volume_avg'].iloc[-1]

        # Buy Condition: Price breaks the upper band
        if last_close > last_bbu:
            decision = "BUY"
        # Sell Condition: Price breaks the lower band AND volume is above average
        elif (last_close < last_bbl) and (last_volume > avg_volume):
            decision = "SELL"
        
        print(f"Signal decision: {decision}. Close: {last_close}, BBU: {last_bbu:.2f}, BBL: {last_bbl:.2f}, Vol: {last_volume}, VolAvg: {avg_volume:.2f}")

    return { 
        "strategy": settings.trading_strategy, 
        "decision": decision, 
        "calculated_quantity": trade_quantity,
        "current_position_amount": current_position_amt,
        "last_close_price": last_close,
        "usdt_balance": usdt_balance,
        "rsi": rsi_value
    }


def _handle_time_based_exit(symbol: str, position: dict) -> bool:
    """Closes a position if it has exceeded the maximum holding time."""
    position_amt = float(position['positionAmt'])
    update_time_ms = int(position['updateTime'])
    
    if position_amt != 0 and update_time_ms > 0:
        position_open_time = datetime.fromtimestamp(update_time_ms / 1000, tz=timezone.utc)
        holding_duration = datetime.now(timezone.utc) - position_open_time
        max_duration_hours = settings.trade_max_holding_hours
        
        print(f"Checking holding time. Position open for {holding_duration}. Limit: {max_duration_hours} hours.")

        if holding_duration.total_seconds() / 3600 > max_duration_hours:
            print(f"Alert! The position has exceeded the {max_duration_hours} hour limit. Closing position...")
            close_all_positions(symbol)
            return True
    return False


def execute_trade(symbol: str, decision: str, quantity: float, current_position_amt: float):
    """Executes a trading order with a position reversal strategy."""
    try:
        log_msg = ""
        if decision == "BUY":
            if current_position_amt < 0:
                quantity_to_trade = abs(current_position_amt) + quantity
                log_msg = f"Closing short ({abs(current_position_amt)}) and opening long ({quantity}) for {symbol}."
            elif current_position_amt == 0:
                quantity_to_trade = quantity
                log_msg = f"Opening new long position ({quantity}) for {symbol}."
            else:
                print(f"BUY decision ignored: a long position already exists for {symbol}.")
                return {"status": "ignored", "reason": "Already in a long position"}
            side = SIDE_BUY

        elif decision == "SELL":
            if current_position_amt > 0:
                quantity_to_trade = current_position_amt + quantity
                log_msg = f"Closing long ({current_position_amt}) and opening short ({quantity}) for {symbol}."
            elif current_position_amt == 0:
                quantity_to_trade = quantity
                log_msg = f"Opening new short position ({quantity}) for {symbol}."
            else:
                print(f"SELL decision ignored: a short position already exists for {symbol}.")
                return {"status": "ignored", "reason": "Already in a short position"}
            side = SIDE_SELL
        else:
            return None # Should not happen

        client.futures_cancel_all_open_orders(symbol=symbol)
        print(log_msg)
        main_order = client.futures_create_order(
            symbol=symbol,
            side=side,
            type=ORDER_TYPE_MARKET,
            quantity=f'{quantity_to_trade:.3f}'
        )
        print("Entry/reversal order executed:", main_order)

        new_position_size = quantity
        mark_price = float(client.futures_mark_price(symbol=symbol)['markPrice'])
        sl_percentage = settings.trade_sl_percentage
        
        sl_side = SIDE_SELL if side == SIDE_BUY else SIDE_BUY
        stop_price = round(mark_price * (1 - sl_percentage if side == SIDE_BUY else 1 + sl_percentage), 2)
        
        print(f"Placing new Stop-Loss at a price of {stop_price}...")
        sl_order = client.futures_create_order(
            symbol=symbol,
            side=sl_side,
            type=FUTURE_ORDER_TYPE_STOP_MARKET,
            stopPrice=f"{stop_price}",
            quantity=f'{new_position_size:.3f}',
            reduceOnly=True
        )
        print("Stop-Loss order placed:", sl_order)
        return {"main_order": main_order, "sl_order": sl_order}

    except BinanceAPIException as e:
        print(f"Error executing trade sequence: {e}")
        return {"error": str(e)}
    except Exception as e:
        print(f"An unexpected error occurred during execute_trade: {e}")
        return {"error": str(e)}


def update_trailing_stop_loss(symbol: str):
    """
    Updates the Stop-Loss to a breakeven point if the profit reaches the threshold.
    """
    if not settings.trailing_stop_enabled:
        return {"status": "disabled", "reason": "Trailing stop-loss is disabled in settings."}

    try:
        positions = client.futures_position_information(symbol=symbol)
        position = next((p for p in positions if p['symbol'] == symbol and float(p['positionAmt']) != 0), None)

        if not position:
            return {"status": "no_position", "reason": "No open position to trail."}

        position_amt = float(position['positionAmt'])
        entry_price = float(position['entryPrice'])
        mark_price = float(client.futures_mark_price(symbol=symbol)['markPrice'])
        
        profit_perc = 0
        if position_amt > 0: # Long
            profit_perc = (mark_price / entry_price) - 1
        elif position_amt < 0: # Short
            profit_perc = (entry_price / mark_price) - 1

        print(f"TSL Check: Position: {position_amt}, Current Profit: {profit_perc:.4%}")

        # If the profit exceeds the threshold, we move the SL to breakeven + a small margin
        if profit_perc >= settings.trailing_stop_callback:
            
            sl_side = SIDE_SELL if position_amt > 0 else SIDE_BUY
            # Move to breakeven + 0.1% to cover fees
            new_stop_price = round(entry_price * (1.001 if position_amt > 0 else 0.999), 2)
            
            # Get current SL to avoid moving it if it's already better
            open_orders = client.futures_get_open_orders(symbol=symbol)
            current_sl_order = next((o for o in open_orders if o['type'] == 'STOP_MARKET'), None)

            if current_sl_order:
                current_stop_price = float(current_sl_order['stopPrice'])
                # If the current SL is already better than breakeven, do nothing
                if (position_amt > 0 and current_stop_price >= new_stop_price) or \
                   (position_amt < 0 and current_stop_price <= new_stop_price):
                    print(f"TSL Ignored: Current Stop-Loss ({current_stop_price}) is already better than the breakeven point ({new_stop_price}).")
                    return {"status": "ignored", "reason": "Current SL is already better."}
            
            print(f"Activating Trailing Stop-Loss! Profit of {profit_perc:.4%} reached the threshold of {settings.trailing_stop_callback:.4%}.")
            print(f"Moving Stop-Loss to a new price of {new_stop_price}...")
            
            # Cancel the previous SL and place the new one
            client.futures_cancel_all_open_orders(symbol=symbol)
            
            tsl_order = client.futures_create_order(
                symbol=symbol,
                side=sl_side,
                type=FUTURE_ORDER_TYPE_STOP_MARKET,
                stopPrice=f"{new_stop_price}",
                quantity=f'{abs(position_amt):.3f}',
                reduceOnly=True
            )
            print("New Trailing Stop-Loss placed:", tsl_order)
            return {"status": "updated", "order": tsl_order}

        return {"status": "profit_not_reached", "current_profit": profit_perc}

    except BinanceAPIException as e:
        print(f"Error updating Trailing Stop-Loss: {e}")
        return {"error": str(e)}
    except Exception as e:
        print(f"An unexpected error occurred during TSL: {e}")
        return {"error": str(e)}


# --- Cleanup and Closing Functions ---

def startup_cleanup(symbol: str):
    """Cancels all open orders for the symbol on startup."""
    try:
        print(f"Canceling all open orders for {symbol} on startup...")
        client.futures_cancel_all_open_orders(symbol=symbol)
        print("Orders canceled successfully.")
    except BinanceAPIException as e:
        print(f"Error during startup cleanup: {e}")

def close_all_positions(symbol: str):
    """Closes any open position for a specific symbol."""
    try:
        positions = client.futures_position_information(symbol=symbol)
        position = next((p for p in positions if p['symbol'] == symbol), None)
        
        if not position or float(position['positionAmt']) == 0:
            print("No open positions to close.")
            return

        current_position_amt = float(position['positionAmt'])
        side = SIDE_SELL if current_position_amt > 0 else SIDE_BUY
        quantity_to_close = abs(current_position_amt)
        
        print(f"Closing position of {quantity_to_close} {symbol}...")
        order = client.futures_create_order(
            symbol=symbol,
            side=side,
            type=ORDER_TYPE_MARKET,
            quantity=f"{quantity_to_close:.3f}",
            reduceOnly=True
        )
        print("Position closed successfully:", order)
        client.futures_cancel_all_open_orders(symbol=symbol)

    except BinanceAPIException as e:
        print(f"Error closing all positions: {e}")
import os
import pandas as pd
import pandas_ta as ta
import time
from datetime import datetime, timezone
from binance.client import Client
from binance.enums import SIDE_BUY, SIDE_SELL, ORDER_TYPE_MARKET, FUTURE_ORDER_TYPE_STOP_MARKET
from binance.exceptions import BinanceAPIException
from src.config import settings

# --- Configuración del Cliente ---
client = Client(settings.binance_api_key, settings.binance_secret_key, testnet=True)
client.FUTURES_URL = 'https://testnet.binancefuture.com/fapi'

# --- Funciones Auxiliares ---

def _get_usdt_balance() -> float:
    """Obtiene el balance de USDT disponible en la cuenta de futuros."""
    try:
        balances = client.futures_account_balance()
        for balance in balances:
            if balance['asset'] == 'USDT':
                return float(balance['availableBalance'])
        return 0.0
    except BinanceAPIException as e:
        print(f"Error al obtener el balance de USDT: {e}")
        return 0.0

def _calculate_aggressive_quantity(symbol: str, usdt_balance: float) -> float:
    """Calcula la cantidad a operar basada en un porcentaje del balance."""
    if usdt_balance == 0:
        return 0.0
    
    try:
        mark_price = float(client.futures_mark_price(symbol=symbol)['markPrice'])
        risk_per_trade = usdt_balance * (settings.trade_risk_percentage / 100)
        quantity = risk_per_trade / mark_price
        return round(quantity, 3)
    except BinanceAPIException as e:
        print(f"Error al calcular la cantidad para la estrategia agresiva: {e}")
        return 0.0

def get_market_data(symbol: str):
    """Obtiene datos históricos del mercado."""
    klines = client.futures_klines(symbol=symbol, interval=settings.trade_interval, limit=50)
    df = pd.DataFrame(klines, columns=[
        'Open Time', 'Open', 'High', 'Low', 'Close', 'Volume', 'Close Time', 
        'Quote Asset Volume', 'Number of Trades', 'Taker Buy Base Asset Volume', 
        'Taker Buy Quote Asset Volume', 'Ignore'
    ])
    df['Close'] = pd.to_numeric(df['Close'])
    df['Open Time'] = pd.to_datetime(df['Open Time'], unit='ms', utc=True)
    return df

# --- Lógica de Estrategia Principal ---

def check_and_decide(symbol: str):
    """
    Función principal que decide la acción de trading basada en la estrategia seleccionada.
    NO ejecuta órdenes, solo analiza y devuelve la decisión.
    """
    print(f"\n[{datetime.now(timezone.utc).isoformat()}] Comprobando estrategia '{settings.trading_strategy}' para {symbol}...")

    try:
        positions = client.futures_position_information(symbol=symbol)
        position = next((p for p in positions if p['symbol'] == symbol), None)
        current_position_amt = float(position['positionAmt']) if position else 0
    except BinanceAPIException as e:
        print(f"Error al obtener información de posición: {e}")
        return {"error": "Fallo al obtener la posición actual."}

    if settings.trading_strategy == 'aggressive' and current_position_amt != 0:
        position_closed_by_time = _handle_time_based_exit(symbol, position)
        if position_closed_by_time:
            return {"decision": "HOLD", "status": "Posición cerrada por límite de tiempo."}

    trade_quantity = 0
    if settings.trading_strategy == 'conservative':
        trade_quantity = settings.trade_quantity
        print(f"Estrategia Conservadora: Usando cantidad fija de {trade_quantity} {symbol.replace('USDT', '')}.")
    elif settings.trading_strategy == 'aggressive':
        usdt_balance = _get_usdt_balance()
        trade_quantity = _calculate_aggressive_quantity(symbol, usdt_balance)
        print(f"Estrategia Agresiva: Balance USDT: {usdt_balance:.2f}. Cantidad calculada: {trade_quantity} {symbol.replace('USDT', '')}.")

    df = get_market_data(symbol)
    df.ta.sma(length=10, append=True)
    df.ta.sma(length=30, append=True)
    df.ta.rsi(length=14, append=True)
    
    last_close = df['Close'].iloc[-1]
    last_sma10 = df['SMA_10'].iloc[-1]
    last_sma30 = df['SMA_30'].iloc[-1]
    last_rsi = df['RSI_14'].iloc[-1]
    
    decision = "HOLD"
    if (last_sma10 > last_sma30) and (last_rsi > 50):
        decision = "BUY"
    elif (last_sma10 < last_sma30) and (last_rsi < 50):
        decision = "SELL"
    
    print(f"Decisión de la señal: {decision}. RSI: {last_rsi:.2f}, SMA10: {last_sma10:.2f}, SMA30: {last_sma30:.2f}")

    return { 
        "strategy": settings.trading_strategy, 
        "decision": decision, 
        "calculated_quantity": trade_quantity,
        "current_position_amount": current_position_amt,
        "last_close_price": last_close,
        "last_sma10": last_sma10,
        "last_sma30": last_sma30,
        "last_rsi": last_rsi
    }


def _handle_time_based_exit(symbol: str, position: dict) -> bool:
    """Cierra una posición si ha excedido el tiempo máximo de tenencia."""
    position_amt = float(position['positionAmt'])
    update_time_ms = int(position['updateTime'])
    
    if position_amt != 0 and update_time_ms > 0:
        position_open_time = datetime.fromtimestamp(update_time_ms / 1000, tz=timezone.utc)
        holding_duration = datetime.now(timezone.utc) - position_open_time
        max_duration_hours = settings.trade_max_holding_hours
        
        print(f"Comprobando tiempo de tenencia. Posición abierta por {holding_duration}. Límite: {max_duration_hours} horas.")

        if holding_duration.total_seconds() / 3600 > max_duration_hours:
            print(f"¡Alerta! La posición ha excedido el límite de {max_duration_hours} horas. Cerrando posición...")
            close_all_positions(symbol)
            return True
    return False


def execute_trade(symbol: str, decision: str, quantity: float, current_position_amt: float):
    """Ejecuta una orden de trading con una estrategia de inversión de posición."""
    try:
        log_msg = ""
        if decision == "BUY":
            if current_position_amt < 0:
                quantity_to_trade = abs(current_position_amt) + quantity
                log_msg = f"Cerrando corta ({abs(current_position_amt)}) y abriendo larga ({quantity}) para {symbol}."
            elif current_position_amt == 0:
                quantity_to_trade = quantity
                log_msg = f"Abriendo nueva posición larga ({quantity}) para {symbol}."
            else:
                print(f"Decisión de COMPRA ignorada: ya existe una posición larga para {symbol}.")
                return {"status": "ignored", "reason": "Already in a long position"}
            side = SIDE_BUY

        elif decision == "SELL":
            if current_position_amt > 0:
                quantity_to_trade = current_position_amt + quantity
                log_msg = f"Cerrando larga ({current_position_amt}) y abriendo corta ({quantity}) para {symbol}."
            elif current_position_amt == 0:
                quantity_to_trade = quantity
                log_msg = f"Abriendo nueva posición corta ({quantity}) para {symbol}."
            else:
                print(f"Decisión de VENTA ignorada: ya existe una posición corta para {symbol}.")
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
        print("Orden de entrada/inversión ejecutada:", main_order)

        new_position_size = quantity
        mark_price = float(client.futures_mark_price(symbol=symbol)['markPrice'])
        sl_percentage = settings.trade_sl_percentage
        
        sl_side = SIDE_SELL if side == SIDE_BUY else SIDE_BUY
        stop_price = round(mark_price * (1 - sl_percentage if side == SIDE_BUY else 1 + sl_percentage), 2)
        
        print(f"Colocando nuevo Stop-Loss a un precio de {stop_price}...")
        sl_order = client.futures_create_order(
            symbol=symbol,
            side=sl_side,
            type=FUTURE_ORDER_TYPE_STOP_MARKET,
            stopPrice=f"{stop_price}",
            quantity=f'{new_position_size:.3f}',
            reduceOnly=True
        )
        print("Orden Stop-Loss colocada:", sl_order)
        return {"main_order": main_order, "sl_order": sl_order}

    except BinanceAPIException as e:
        print(f"Error al ejecutar la secuencia de trade: {e}")
        return {"error": str(e)}
    except Exception as e:
        print(f"Un error inesperado ocurrió durante execute_trade: {e}")
        return {"error": str(e)}

# --- Funciones de Limpieza y Cierre ---

def startup_cleanup(symbol: str):
    """Cancela todas las órdenes abiertas para el símbolo al iniciar."""
    try:
        print(f"Cancelando todas las órdenes abiertas para {symbol} al iniciar...")
        client.futures_cancel_all_open_orders(symbol=symbol)
        print("Órdenes canceladas exitosamente.")
    except BinanceAPIException as e:
        print(f"Error durante la limpieza de inicio: {e}")

def close_all_positions(symbol: str):
    """Cierra cualquier posición abierta para un símbolo específico."""
    try:
        positions = client.futures_position_information(symbol=symbol)
        position = next((p for p in positions if p['symbol'] == symbol), None)
        
        if not position or float(position['positionAmt']) == 0:
            print("No hay posiciones abiertas para cerrar.")
            return

        current_position_amt = float(position['positionAmt'])
        side = SIDE_SELL if current_position_amt > 0 else SIDE_BUY
        quantity_to_close = abs(current_position_amt)
        
        print(f"Cerrando posición de {quantity_to_close} {symbol}...")
        order = client.futures_create_order(
            symbol=symbol,
            side=side,
            type=ORDER_TYPE_MARKET,
            quantity=f"{quantity_to_close:.3f}",
            reduceOnly=True
        )
        print("Posición cerrada exitosamente:", order)
        client.futures_cancel_all_open_orders(symbol=symbol)

    except BinanceAPIException as e:
        print(f"Error al cerrar todas las posiciones: {e}")
import os
import pandas as pd
import pandas_ta as ta
from binance.client import Client
from binance.enums import SIDE_BUY, SIDE_SELL, ORDER_TYPE_MARKET, FUTURE_ORDER_TYPE_STOP_MARKET
from src.config import settings

# --- Configuración del Cliente ---
# Usamos las variables de entorno para las claves
API_KEY = settings.binance_api_key
SECRET_KEY = settings.binance_secret_key

# IMPORTANTE: Usar el URL base de la Testnet para que las órdenes sean ficticias
client = Client(API_KEY, SECRET_KEY, testnet=True)
client.FUTURES_URL = 'https://testnet.binancefuture.com/fapi'

# --- Funciones de Lógica y Trading ---

def get_market_data(symbol: str):
    # Obtener 50 velas del intervalo de tiempo definido en la configuración
    klines = client.futures_klines(symbol=symbol, interval=settings.trade_interval, limit=50)
    
    df = pd.DataFrame(klines, columns=[
        'Open Time', 'Open', 'High', 'Low', 'Close', 'Volume', 'Close Time', 
        'Quote Asset Volume', 'Number of Trades', 'Taker Buy Base Asset Volume', 
        'Taker Buy Quote Asset Volume', 'Ignore'
    ])
    df['Close'] = pd.to_numeric(df['Close'])
    return df

def check_and_decide(symbol: str):
    df = get_market_data(symbol)
    
    # Calcular SMA 10, SMA 30 y RSI 14
    df.ta.sma(length=10, append=True)
    df.ta.sma(length=30, append=True)
    df.ta.rsi(length=14, append=True)
    
    last_close = df['Close'].iloc[-1]
    last_sma10 = df['SMA_10'].iloc[-1]
    last_sma30 = df['SMA_30'].iloc[-1]
    last_rsi = df['RSI_14'].iloc[-1]
    
    decision = "HOLD"
    
    # Lógica de Trading: Cruce de Medias Móviles con confirmación de RSI
    if (last_sma10 > last_sma30) and (last_rsi > 50):
        # Cruce alcista confirmado por momentum alcista
        decision = "BUY"
    elif (last_sma10 < last_sma30) and (last_rsi < 50):
        # Cruce bajista confirmado por momentum bajista
        decision = "SELL"
    
    return {
        "symbol": symbol,
        "decision": decision,
        "last_close_price": last_close,
        "last_sma10": last_sma10,
        "last_sma30": last_sma30,
        "last_rsi": last_rsi
    }

def execute_trade(symbol: str, decision: str, quantity: float):
    """
    Ejecuta una orden de trading con una estrategia de inversión de posición y
    coloca automáticamente una orden de stop-loss.
    """
    try:
        # 1. Obtener la posición actual para el símbolo
        positions = client.futures_position_information(symbol=symbol)
        current_position_amt = 0
        for pos in positions:
            if pos['symbol'] == symbol:
                current_position_amt = float(pos['positionAmt'])
                break

        order_to_execute = None
        # 2. Implementar la lógica de "invertir y continuar"
        if decision == "BUY":
            if current_position_amt < 0:
                quantity_to_trade = abs(current_position_amt) + quantity
                side = SIDE_BUY
                order_to_execute = {"side": side, "qty": quantity_to_trade, "log": f"Cerrando corta y abriendo larga para {symbol}..."}
            elif current_position_amt == 0:
                quantity_to_trade = quantity
                side = SIDE_BUY
                order_to_execute = {"side": side, "qty": quantity_to_trade, "log": f"Abriendo nueva posición larga para {symbol}..."}
            else:
                print(f"Decisión de COMPRA ignorada: ya existe una posición larga para {symbol}.")
                return None
        
        elif decision == "SELL":
            if current_position_amt > 0:
                quantity_to_trade = current_position_amt + quantity
                side = SIDE_SELL
                order_to_execute = {"side": side, "qty": quantity_to_trade, "log": f"Cerrando larga y abriendo corta para {symbol}..."}
            elif current_position_amt == 0:
                quantity_to_trade = quantity
                side = SIDE_SELL
                order_to_execute = {"side": side, "qty": quantity_to_trade, "log": f"Abriendo nueva posición corta para {symbol}..."}
            else:
                print(f"Decisión de VENTA ignorada: ya existe una posición corta para {symbol}.")
                return None
        else:
            return None

        # --- Secuencia de ejecución de órdenes ---
        # 3. Cancelar todas las órdenes abiertas antes de entrar en una nueva posición
        print("Cancelando órdenes abiertas existentes...")
        client.futures_cancel_all_open_orders(symbol=symbol)

        # 4. Ejecutar la orden de entrada principal
        print(order_to_execute["log"])
        main_order = client.futures_create_order(
            symbol=symbol,
            side=order_to_execute["side"],
            type=ORDER_TYPE_MARKET,
            quantity=f'{order_to_execute["qty"]:.3f}'
        )
        print("Orden principal ejecutada:", main_order)

        # 5. Colocar la orden de Stop-Loss
        mark_price = float(client.futures_mark_price(symbol=symbol)['markPrice'])
        sl_percentage = settings.trade_sl_percentage
        
        if order_to_execute["side"] == SIDE_BUY: # Posición larga, el SL es una venta
            stop_price = round(mark_price * (1 - sl_percentage), 2)
            sl_side = SIDE_SELL
        else: # Posición corta, el SL es una compra
            stop_price = round(mark_price * (1 + sl_percentage), 2)
            sl_side = SIDE_BUY
        
        print(f"Colocando Stop-Loss a un precio de {stop_price}...")
        sl_order = client.futures_create_order(
            symbol=symbol,
            side=sl_side,
            type=FUTURE_ORDER_TYPE_STOP_MARKET,
            stopPrice=f"{stop_price}",
            quantity=f'{order_to_execute["qty"]:.3f}',
            reduceOnly=True
        )
        print("Orden Stop-Loss colocada:", sl_order)

        return {"main_order": main_order, "sl_order": sl_order}
    
    except Exception as e:
        print(f"Error al ejecutar la secuencia de trade en Binance Testnet: {e}")
        return {"error": str(e)}

# --- Funciones de Limpieza y Cierre ---

def startup_cleanup(symbol: str):
    """
    Se ejecuta al iniciar la aplicación para limpiar el estado.
    - Cancela todas las órdenes abiertas para el símbolo.
    """
    try:
        print(f"Cancelando todas las órdenes abiertas para {symbol} al iniciar...")
        client.futures_cancel_all_open_orders(symbol=symbol)
        print("Órdenes canceladas exitosamente.")
    except Exception as e:
        print(f"Error durante la limpieza de inicio: {e}")

def close_all_positions(symbol: str):
    """
    Cierra todas las posiciones abiertas para un símbolo específico.
    Esencial para un apagado seguro.
    """
    try:
        # 1. Obtener la posición actual para el símbolo
        positions = client.futures_position_information(symbol=symbol)
        current_position_amt = 0
        for pos in positions:
            if pos['symbol'] == symbol:
                current_position_amt = float(pos['positionAmt'])
                break
        
        if current_position_amt == 0:
            print("No hay posiciones abiertas para cerrar.")
            return

        # 2. Determinar el lado de la orden para cerrar la posición
        if current_position_amt > 0: # Posición larga
            side = SIDE_SELL
            quantity_to_close = current_position_amt
            print(f"Cerrando posición larga de {quantity_to_close} {symbol}...")
        else: # Posición corta
            side = SIDE_BUY
            quantity_to_close = abs(current_position_amt)
            print(f"Cerrando posición corta de {quantity_to_close} {symbol}...")

        # 3. Crear y ejecutar la orden de cierre
        order = client.futures_create_order(
            symbol=symbol,
            side=side,
            type=ORDER_TYPE_MARKET,
            quantity=f"{quantity_to_close:.3f}",
            reduceOnly=True # Importante para asegurar que solo cierre la posición
        )
        print("Posición cerrada exitosamente:", order)

    except Exception as e:
        print(f"Error al cerrar todas las posiciones: {e}")
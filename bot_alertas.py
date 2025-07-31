import os
import time
import ccxt
import pandas as pd
import numpy as np
import requests
from datetime import datetime

# ================= CONFIGURACIÓN =================

API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")

if not all([API_KEY, API_SECRET, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
    print("❌ ERROR: Variables de entorno no configuradas.")
    exit()

binance = ccxt.binance({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'enableRateLimit': True,
    'options': {'defaultType': 'future'}
})

symbols = [
    "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT", "ADA/USDT",
    "MATIC/USDT", "DOT/USDT", "LTC/USDT", "TRX/USDT", "AVAX/USDT", "LINK/USDT", "ATOM/USDT",
    "ETC/USDT", "FIL/USDT", "SAND/USDT", "APE/USDT", "AAVE/USDT", "NEAR/USDT",
    "FTM/USDT", "GALA/USDT", "CHR/USDT", "RUNE/USDT", "XMR/USDT", "EOS/USDT",
    "FLOW/USDT", "HNT/USDT", "WAVES/USDT", "CRV/USDT", "COMP/USDT", "KAVA/USDT",
    "COTI/USDT", "DYDX/USDT", "RNDR/USDT", "IMX/USDT", "LDO/USDT", "SUI/USDT",
    "OP/USDT", "ARB/USDT"
]

# Configuración de trading
CAPITAL_USDT = 20
LEVERAGE = 10
STOP_LOSS = 3      # USD
TAKE_PROFIT = 5    # USD

# ================= FUNCIONES =================

def enviar_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})

def obtener_ohlcv(symbol, tf='15m', limit=200):
    try:
        df = pd.DataFrame(binance.fetch_ohlcv(symbol, timeframe=tf, limit=limit),
                          columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['close'] = df['close'].astype(float)
        return df
    except Exception as e:
        print(f"Error OHLCV {symbol}: {e}")
        return None

def calcular_indicadores(df):
    # RSI
    delta = df['close'].diff()
    up, down = delta.clip(lower=0), -delta.clip(upper=0)
    roll_up = up.ewm(span=14).mean()
    roll_down = down.ewm(span=14).mean()
    rs = roll_up / roll_down
    df['rsi'] = 100 - (100 / (1 + rs))

    # MACD
    ema12 = df['close'].ewm(span=12).mean()
    ema26 = df['close'].ewm(span=26).mean()
    df['macd'] = ema12 - ema26
    df['macd_signal'] = df['macd'].ewm(span=9).mean()

    # EMAs para tendencia
    df['ema50'] = df['close'].ewm(span=50).mean()
    df['ema200'] = df['close'].ewm(span=200).mean()

    return df

def generar_senal(df, symbol):
    precio = df['close'].iloc[-1]
    ema50, ema200 = df['ema50'].iloc[-1], df['ema200'].iloc[-1]
    rsi = df['rsi'].iloc[-1]
    macd, macd_signal = df['macd'].iloc[-1], df['macd_signal'].iloc[-1]

    up_trend = ema50 > ema200
    down_trend = ema50 < ema200

    if up_trend and macd > macd_signal and rsi < 30:
        return {"symbol": symbol, "tipo": "LONG", "precio": round(precio, 4)}
    elif down_trend and macd < macd_signal and rsi > 70:
        return {"symbol": symbol, "tipo": "SHORT", "precio": round(precio, 4)}
    return None

def abrir_posicion(signal):
    symbol = signal['symbol'].replace("/", "")
    lado = "buy" if signal['tipo'] == "LONG" else "sell"

    try:
        # Obtener precio actual
        ticker = binance.fetch_ticker(signal['symbol'])
        price = ticker['last']

        # Calcular cantidad a comprar con leverage
        cantidad = round((CAPITAL_USDT * LEVERAGE) / price, 3)

        # Enviar orden market
        orden = binance.create_market_order(signal['symbol'], lado, cantidad)

        # SL y TP
        sl_price = price - STOP_LOSS if lado == "buy" else price + STOP_LOSS
        tp_price = price + TAKE_PROFIT if lado == "buy" else price - TAKE_PROFIT

        binance.create_order(signal['symbol'], 'TAKE_PROFIT_MARKET', lado, cantidad,
                             params={"stopPrice": tp_price})
        binance.create_order(signal['symbol'], 'STOP_MARKET', 'sell' if lado == "buy" else 'buy',
                             cantidad, params={"stopPrice": sl_price})

        enviar_telegram(f"✅ {signal['tipo']} {signal['symbol']} @ {price}\nSL: {sl_price} | TP: {tp_price}")
    except Exception as e:
        enviar_telegram(f"⚠️ Error al abrir posición {signal['symbol']}: {e}")

# ================= LOOP PRINCIPAL =================

while True:
    for s in symbols:
        df = obtener_ohlcv(s)
        if df is None:
            continue
        df = calcular_indicadores(df)
        signal = generar_senal(df, s)
        if signal:
            abrir_posicion(signal)
    time.sleep(60)  # analiza cada minuto pero solo avisa si abre posición

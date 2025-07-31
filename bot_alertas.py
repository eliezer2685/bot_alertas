import ccxt
import pandas as pd
import numpy as np
import random
import time
from datetime import datetime
import ta
from telegram import Bot
import os

# ==============================
# CONFIGURACIÓN
# ==============================
API_KEY = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if not API_KEY or not CHAT_ID:
    print("❌ ERROR: TELEGRAM_TOKEN o TELEGRAM_CHAT_ID no configurados.")
    exit(1)

INTERVALO_HORAS = 1                     # Analiza cada 1 hora
TIMEFRAMES = ['1h', '4h']               # Temporalidades
SYMBOLS = [
    "BTC/USDT","ETH/USDT","BNB/USDT","XRP/USDT","ADA/USDT",
    "DOGE/USDT","SOL/USDT","MATIC/USDT","DOT/USDT","LTC/USDT",
    "TRX/USDT","AVAX/USDT","SHIB/USDT","UNI/USDT","ATOM/USDT",
    "LINK/USDT","XLM/USDT","ETC/USDT","XMR/USDT","NEAR/USDT",
    "APT/USDT","ARB/USDT","OP/USDT","FTM/USDT","GALA/USDT",
    "AAVE/USDT","SAND/USDT","MANA/USDT","RNDR/USDT","FIL/USDT"
]

bot = Bot(token=API_KEY)
exchange = ccxt.binance()

# ==============================
# INDICADORES
# ==============================
def detectar_divergencia(df):
    df['rsi'] = ta.momentum.RSIIndicator(df['close'], 14).rsi()
    if df['rsi'].iloc[-1] > 70:
        return "⚠️ RSI sobrecompra (>70)"
    elif df['rsi'].iloc[-1] < 30:
        return "⚠️ RSI sobreventa (<30)"
    return None

def detectar_cruce_medias(df):
    df['ema_fast'] = df['close'].ewm(span=9).mean()
    df['ema_slow'] = df['close'].ewm(span=21).mean()
    if df['ema_fast'].iloc[-2] < df['ema_slow'].iloc[-2] and df['ema_fast'].iloc[-1] > df['ema_slow'].iloc[-1]:
        return "✅ Cruce alcista EMA 9/21"
    if df['ema_fast'].iloc[-2] > df['ema_slow'].iloc[-2] and df['ema_fast'].iloc[-1] < df['ema_slow'].iloc[-1]:
        return "⚠️ Cruce bajista EMA 9/21"
    return None

def detectar_macd(df):
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()
    if macd.iloc[-1] > signal.iloc[-1] and macd.iloc[-2] <= signal.iloc[-2]:
        return "✅ Señal MACD Alcista"
    if macd.iloc[-1] < signal.iloc[-1] and macd.iloc[-2] >= signal.iloc[-2]:
        return "⚠️ Señal MACD Bajista"
    return None

def detectar_fibonacci(df):
    max_price = df['high'].max()
    min_price = df['low'].min()
    fib_50 = max_price - (max_price - min_price) * 0.5
    fib_618 = max_price - (max_price - min_price) * 0.618
    current_price = df['close'].iloc[-1]
    if fib_618 <= current_price <= fib_50:
        return f"📐 Precio en zona Fibonacci 50-61.8% ({round(current_price, 4)})"
    return None

# ==============================
# FUNCIÓN PRINCIPAL
# ==============================
def analizar_moneda(symbol):
    analizado = False
    for tf in TIMEFRAMES:
        try:
            print(f"🔹 Descargando {symbol} {tf} ...")
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe=tf, limit=150)
            if not ohlcv:
                print(f"⚠️ No se obtuvieron datos para {symbol} {tf}")
                continue

            df = pd.DataFrame(ohlcv, columns=['timestamp','open','high','low','close','volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

            alertas = [
                detectar_divergencia(df),
                detectar_cruce_medias(df),
                detectar_macd(df),
                detectar_fibonacci(df)
            ]

            for alerta in alertas:
                if alerta:
                    analizado = True
                    mensaje = f"📊 {symbol} | TF {tf} | {alerta} | {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                    print(mensaje)
                    bot.send_message(chat_id=CHAT_ID, text=mensaje)

        except Exception as e:
            print(f"❌ Error en {symbol} {tf}: {e}")
    return analizado

# ==============================
# LOOP PRINCIPAL
# ==============================
if __name__ == "__main__":
    bot.send_message(chat_id=CHAT_ID, text="🚀 Bot de alertas iniciado correctamente")
    while True:
        seleccion = random.sample(SYMBOLS, 30)
        print(f"🔹 Analizando {len(seleccion)} monedas: {seleccion}")

        analizadas = 0
        for symbol in seleccion:
            if analizar_moneda(symbol):
                analizadas += 1

        resumen = f"✅ Se analizaron {len(seleccion)} monedas. Señales detectadas: {analizadas}."
        print(resumen)
        bot.send_message(chat_id=CHAT_ID, text=resumen)

        print(f"⏳ Esperando {INTERVALO_HORAS} horas para próximo análisis...")
        time.sleep(INTERVALO_HORAS * 3600)

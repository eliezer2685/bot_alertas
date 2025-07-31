import ccxt
import pandas as pd
import ta
import os
import time
import datetime
import requests

# === Variables de entorno ===
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")

if not all([API_KEY, API_SECRET, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
    print("❌ ERROR: Variables de entorno no configuradas.")
    exit()

# === Configuración Binance Futures ===
binance = ccxt.binance({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'enableRateLimit': True,
    'options': {'defaultType': 'future'}
})

# === Lista de criptos para análisis ===
symbols = [
    'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT', 'DOGE/USDT', 
    'ADA/USDT', 'MATIC/USDT', 'LTC/USDT', 'DOT/USDT', 'AVAX/USDT', 'TRX/USDT',
    'LINK/USDT', 'ATOM/USDT', 'ETC/USDT', 'XLM/USDT', 'NEAR/USDT', 'APT/USDT',
    'OP/USDT', 'ARB/USDT', 'AAVE/USDT', 'SAND/USDT', 'MANA/USDT', 'EOS/USDT',
    'FTM/USDT', 'GALA/USDT', 'RNDR/USDT', 'RUNE/USDT', 'INJ/USDT', 'LDO/USDT',
    'DYDX/USDT', 'CRO/USDT', 'FIL/USDT', 'THETA/USDT', 'FLOW/USDT', 'IMX/USDT',
    'CHZ/USDT', 'QNT/USDT', 'KAVA/USDT', 'SNX/USDT', '1INCH/USDT'
]

# === Función para enviar mensajes a Telegram ===
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})

# === Estrategia de señal ===
def get_signal(df):
    df['EMA20'] = ta.trend.ema_indicator(df['close'], window=20)
    df['EMA50'] = ta.trend.ema_indicator(df['close'], window=50)
    df['RSI'] = ta.momentum.rsi(df['close'], window=14)
    df['MACD'] = ta.trend.macd(df['close'])
    df['MACD_signal'] = ta.trend.macd_signal(df['close'])
    df['ADX'] = ta.trend.adx(df['high'], df['low'], df['close'], window=14)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # Señal de compra
    if last['EMA20'] > last['EMA50'] and last['RSI'] > 55 and last['MACD'] > last['MACD_signal'] and last['ADX'] > 20:
        return "BUY"
    # Señal de venta
    elif last['EMA20'] < last['EMA50'] and last['RSI'] < 45 and last['MACD'] < last['MACD_signal'] and last['ADX'] > 20:
        return "SELL"
    else:
        return None

# === Loop principal cada 2 horas, solo 06-22 AR ===
while True:
    hora_arg = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-3))).hour
    if 6 <= hora_arg <= 22:
        señales = []
        for symbol in symbols:
            try:
                ohlcv = binance.fetch_ohlcv(symbol, timeframe='15m', limit=100)
                df = pd.DataFrame(ohlcv, columns=['time','open','high','low','close','volume'])
                signal = get_signal(df)
                if signal:
                    señales.append(f"{symbol}: {signal}")
            except Exception as e:
                print(f"Error con {symbol}: {e}")

        if señales:
            mensaje = "🚨 Señales detectadas:\n" + "\n".join(señales)
            send_telegram(mensaje)
            print(mensaje)
        else:
            print("⏳ Sin señales en esta ronda.")

    # Espera 2 horas
    time.sleep(60*60*2)

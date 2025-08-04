import ccxt
import pandas as pd
import numpy as np
import schedule
import time
import datetime
import requests
from textblob import TextBlob

# ==========================
# CONFIGURACIÓN DEL BOT
# ==========================
SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
    "DOGE/USDT", "ADA/USDT", "AVAX/USDT", "DOT/USDT", "TRX/USDT",
    "MATIC/USDT", "SHIB/USDT", "LINK/USDT", "LTC/USDT", "BCH/USDT",
    "OP/USDT", "IMX/USDT", "APT/USDT", "ARB/USDT", "SUI/USDT",
    "RNDR/USDT", "INJ/USDT", "GALA/USDT", "PEPE/USDT", "PYTH/USDT",
    "SEI/USDT", "NEAR/USDT", "JUP/USDT", "ATOM/USDT", "FTM/USDT",
    "ALGO/USDT", "ICP/USDT", "VET/USDT", "QNT/USDT", "FLOW/USDT",
    "EGLD/USDT", "AAVE/USDT", "HBAR/USDT", "CFX/USDT", "GRT/USDT",
    "CHZ/USDT", "SAND/USDT", "MANA/USDT", "AXS/USDT", "THETA/USDT",
    "FIL/USDT", "RUNE/USDT", "KAVA/USDT", "1INCH/USDT", "OCEAN/USDT",
    "JTO/USDT", "BLUR/USDT", "GMT/USDT", "FET/USDT", "DYM/USDT",
    "BONK/USDT", "TWT/USDT", "STX/USDT", "MINA/USDT", "SKL/USDT"
]

TIMEFRAME = "15m"  # Intervalo de análisis
MAX_CANDLES = 200  # Velas a descargar para indicadores
ALERT_COOLDOWN = 30 * 60  # 30 minutos en segundos

# ==========================
# INICIALIZACIÓN
# ==========================
exchange = ccxt.binance()
summary_buffer = []
last_alert_time = {}

print("Bot de alertas iniciado ✅")
print("Analizando pares Spot de Binance cada 15 minutos...")
print("Esperando primera señal...")

# ==========================
# FUNCIONES DE INDICADORES
# ==========================
def calculate_indicators(df):
    """Calcula RSI, EMA y MACD."""
    df["EMA9"] = df["close"].ewm(span=9).mean()
    df["EMA21"] = df["close"].ewm(span=21).mean()
    
    # RSI
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    df["RSI"] = 100 - (100 / (1 + rs))
    
    # MACD
    ema12 = df["close"].ewm(span=12).mean()
    ema26 = df["close"].ewm(span=26).mean()
    df["MACD"] = ema12 - ema26
    df["Signal"] = df["MACD"].ewm(span=9).mean()

    return df

# ==========================
# FUNCIONES DE ALERTAS
# ==========================
def fetch_ohlcv(symbol):
    try:
        candles = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=MAX_CANDLES)
        df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df
    except Exception as e:
        print(f"Error descargando velas para {symbol}: {e}")
        return None

def analyze_symbol(symbol):
    df = fetch_ohlcv(symbol)
    if df is None or len(df) < 50:
        return None

    df = calculate_indicators(df)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    ema_signal = last["EMA9"] > last["EMA21"]
    macd_signal = last["MACD"] > last["Signal"]
    rsi_signal = last["RSI"] < 30 or last["RSI"] > 70

    # Conteo de estrategias activas
    strategies_active = sum([ema_signal, macd_signal, rsi_signal])

    if strategies_active >= 2:
        direction = "LONG" if ema_signal else "SHORT"
        price = last["close"]
        tp = round(price * (1.02 if direction == "LONG" else 0.98), 4)
        sl = round(price * (0.98 if direction == "LONG" else 1.02), 4)
        
        # Filtro anti-alerta repetida
        now = time.time()
        if symbol in last_alert_time and now - last_alert_time[symbol] < ALERT_COOLDOWN:
            return None
        last_alert_time[symbol] = now

        msg = (f"🔔 Señal {direction} en {symbol}\n"
               f"💰 Precio: {price}\n"
               f"🎯 TP: {tp}\n"
               f"🛡 SL: {sl}\n"
               f"📊 Estrategias activas: {strategies_active}/3\n"
               f"⏰ {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
        
        summary_buffer.append(msg)
        print(msg)
        return msg
    return None

def fetch_news():
    """Obtiene titulares de noticias y calcula sentimiento."""
    try:
        url = "https://cryptopanic.com/api/v1/posts/?auth_token=demo&currencies=BTC"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        titles = [r["title"] for r in data["results"][:5]]
        
        sentiment_scores = [TextBlob(t).sentiment.polarity for t in titles]
        sentiment_avg = np.mean(sentiment_scores)
        sentiment_label = "Positivo" if sentiment_avg > 0.1 else "Negativo" if sentiment_avg < -0.1 else "Neutral"
        
        msg = f"📰 Noticias Crypto (sentimiento {sentiment_label}):\n" + "\n".join([f"- {t}" for t in titles])
        return msg
    except:
        return "No se pudieron obtener noticias."

def job():
    for symbol in SYMBOLS:
        analyze_symbol(symbol)

def send_summary():
    print("\n=== RESUMEN ÚLTIMA HORA ===")
    if summary_buffer:
        for msg in summary_buffer:
            print(msg)
        summary_buffer.clear()
    else:
        print("Sin alertas generadas")
    print(fetch_news())
    print("============================\n")

# ==========================
# SCHEDULER
# ==========================
schedule.every(15).minutes.do(job)
schedule.every(1).hours.do(send_summary)

# Primer mensaje inmediato
send_summary()

while True:
    schedule.run_pending()
    time.sleep(5)

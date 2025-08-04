import os
import time
import schedule
import requests
import pandas as pd
import numpy as np
from binance.client import Client
from datetime import datetime
from telegram import Bot

# ===================== CONFIGURACIÓN =====================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

bot = Bot(token=TELEGRAM_TOKEN)

# Binance Spot sin API Key
client = Client()

# Monedas a analizar
SYMBOLS = [
    "BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","AVAXUSDT",
    "DOTUSDT","TRXUSDT","MATICUSDT","LTCUSDT","LINKUSDT","UNIUSDT","ATOMUSDT","XMRUSDT",
    "ALGOUSDT","FTMUSDT","SANDUSDT","AXSUSDT","NEARUSDT","AAVEUSDT","ICPUSDT","GRTUSDT",
    "EGLDUSDT","MANAUSDT","RUNEUSDT","THETAUSDT","VETUSDT","FILUSDT","RNDRUSDT","SUIUSDT",
    "1INCHUSDT","OCEANUSDT","PYTHUSDT","JTOUSDT","APTUSDT","ARBUSDT","OPUSDT","SEIUSDT",
    "INJUSDT","STXUSDT","ETCUSDT","XLMUSDT","PEPEUSDT","BONKUSDT","TIAUSDT","ORDIUSDT",
    "FETUSDT","IMXUSDT","CFXUSDT","MINAUSDT","KAVAUSDT","FLOWUSDT","GALAUSDT","CHZUSDT",
    "DYDXUSDT","LDOUSDT","COMPUSDT","BANDUSDT"
]

# Evitar alertas repetidas
last_alert_time = {}

# ===================== FUNCIONES DE INDICADORES =====================

def get_klines(symbol, interval="15m", limit=200):
    """Descarga velas de Binance"""
    try:
        klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
        df = pd.DataFrame(klines, columns=[
            "timestamp","o","h","l","c","v","close_time","qav","num_trades","tbbav","tbqav","ignore"
        ])
        df["c"] = df["c"].astype(float)
        return df
    except Exception as e:
        print(f"Error al descargar velas {symbol}: {e}")
        return None

def calculate_indicators(df):
    """Calcula EMA, MACD y RSI"""
    df["EMA20"] = df["c"].ewm(span=20).mean()
    df["EMA50"] = df["c"].ewm(span=50).mean()

    # MACD
    ema12 = df["c"].ewm(span=12).mean()
    ema26 = df["c"].ewm(span=26).mean()
    df["MACD"] = ema12 - ema26
    df["Signal"] = df["MACD"].ewm(span=9).mean()

    # RSI
    delta = df["c"].diff()
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = pd.Series(gain).rolling(window=14).mean()
    avg_loss = pd.Series(loss).rolling(window=14).mean()
    rs = avg_gain / avg_loss
    df["RSI"] = 100 - (100 / (1 + rs))
    return df

# ===================== ESTRATEGIAS =====================

def strategy_signals(df):
    """Retorna señal y estrategias cumplidas"""
    latest = df.iloc[-1]
    strategies = []

    # Estrategia 1: EMA
    if latest["EMA20"] > latest["EMA50"]:
        strategies.append("EMA_BULL")
    elif latest["EMA20"] < latest["EMA50"]:
        strategies.append("EMA_BEAR")

    # Estrategia 2: MACD
    if latest["MACD"] > latest["Signal"]:
        strategies.append("MACD_BULL")
    elif latest["MACD"] < latest["Signal"]:
        strategies.append("MACD_BEAR")

    # Estrategia 3: RSI
    if latest["RSI"] < 30:
        strategies.append("RSI_OVERSOLD")
    elif latest["RSI"] > 70:
        strategies.append("RSI_OVERBOUGHT")

    return strategies

# ===================== NOTICIAS =====================

def fetch_news():
    """Obtiene noticias relevantes"""
    try:
        url = "https://cryptopanic.com/api/v1/posts/?auth_token=demo&currencies=BTC,ETH&filter=rising"
        r = requests.get(url, timeout=10)
        data = r.json()
        news = []
        for post in data.get("results", [])[:3]:
            title = post["title"]
            url_post = post["url"]
            news.append(f"- {title} ({url_post})")
        return "\n".join(news)
    except:
        return "No se pudieron obtener noticias en este momento."

# ===================== ALERTAS =====================

def send_alert(symbol, strategies, price):
    """Envía alerta a Telegram"""
    now = datetime.utcnow()
    if symbol in last_alert_time:
        if (now - last_alert_time[symbol]).total_seconds() < 1800:
            return  # evitar alertas repetidas 30min

    last_alert_time[symbol] = now

    direction = "LONG" if any("BULL" in s for s in strategies) else "SHORT"
    tp = round(price * (1.02 if direction=="LONG" else 0.98), 4)
    sl = round(price * (0.98 if direction=="LONG" else 1.02), 4)

    # Calcular confianza
    strategies_count = len(strategies)
    if strategies_count >= 3:
        confidence = "Alta (90%)"
    elif strategies_count == 2:
        confidence = "Media (70%)"
    else:
        confidence = "Baja (50%)"

    msg = (
        f"🚨 ALERTA {direction} {symbol}\n"
        f"💰 Precio: {price}\n"
        f"🎯 TP: {tp}\n"
        f"🛑 SL: {sl}\n"
        f"📊 Estrategias: {', '.join(strategies)}\n"
        f"📈 Confianza: {confidence}\n"
        f"📰 Noticias:\n{fetch_news()}"
    )
    bot.send_message(chat_id=CHAT_ID, text=msg)

# ===================== LOOP PRINCIPAL =====================

def analyze_market():
    print("Analizando mercado...")
    for symbol in SYMBOLS:
        df = get_klines(symbol)
        if df is None or df.empty:
            continue

        df = calculate_indicators(df)
        strategies = strategy_signals(df)
        price = df["c"].iloc[-1]

        # Contar cuántas estrategias coinciden
        bull_count = sum(1 for s in strategies if "BULL" in s or "RSI_OVERSOLD" in s)
        bear_count = sum(1 for s in strategies if "BEAR" in s or "RSI_OVERBOUGHT" in s)
        if bull_count >= 2 or bear_count >= 2:
            send_alert(symbol, strategies, price)

def hourly_summary():
    summary = f"⏰ Resumen {datetime.utcnow().strftime('%H:%M UTC')}\n"
    summary += "Analizando mercado...\n"
    summary += "Noticias:\n" + fetch_news()
    bot.send_message(chat_id=CHAT_ID, text=summary)

def main():
    bot.send_message(chat_id=CHAT_ID, text="✅ Bot de trading iniciado en Render con % de confianza")
    print("Bot iniciado correctamente")

    schedule.every(30).minutes.do(analyze_market)
    schedule.every().hour.do(hourly_summary)

    while True:
        schedule.run_pending()
        print("Bot corriendo...")  # Heartbeat
        time.sleep(60)

if __name__ == "__main__":
    main()

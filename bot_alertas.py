import os
import time
import datetime
import requests
import pandas as pd
import numpy as np
import ta
import feedparser
import csv
from textblob import TextBlob
from telegram import Bot
import schedule
from binance.client import Client

# ========================
# 🔹 Variables de entorno
# ========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")

if not all([TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
    print("❌ ERROR: Variables de entorno no configuradas.")
    exit()

bot = Bot(token=TELEGRAM_TOKEN)

# ========================
# 🔹 CSV para histórico
# ========================
CSV_FILE = "historico_senales.csv"
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Fecha", "Moneda", "Señal", "Precio Entrada", "TP", "SL", "Confianza", "Sentimiento", "Noticias"])

# ========================
# 🔹 Lista de monedas
# ========================
symbols = [
    "BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","SOLUSDT","DOGEUSDT","ADAUSDT","TRXUSDT","MATICUSDT","LTCUSDT",
    "DOTUSDT","SHIBUSDT","AVAXUSDT","UNIUSDT","ATOMUSDT","LINKUSDT","XLMUSDT","FILUSDT","ICPUSDT","APTUSDT",
    "ARBUSDT","SANDUSDT","MANAUSDT","APEUSDT","AXSUSDT","NEARUSDT","EOSUSDT","FLOWUSDT","XTZUSDT","THETAUSDT",
    "AAVEUSDT","GRTUSDT","RUNEUSDT","KAVAUSDT","CRVUSDT","FTMUSDT","CHZUSDT","SNXUSDT","LDOUSDT","OPUSDT",
    "COMPUSDT","DYDXUSDT","BLURUSDT","RNDRUSDT","GMTUSDT","1INCHUSDT","OCEANUSDT","SUIUSDT","PYTHUSDT","JTOUSDT",
    "FTTUSDT","CAKEUSDT","INJUSDT","WOOUSDT","MINAUSDT","CELRUSDT","ENJUSDT","STXUSDT","IMXUSDT","GALAUSDT"
]

# ========================
# 🔹 RSS de noticias
# ========================
news_feeds = [
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
    "https://news.bitcoin.com/feed/",
    "https://cryptoslate.com/feed/",
    "https://decrypt.co/feed",
    "https://bitcoinmagazine.com/feed",
    "https://u.today/rss",
    "https://ambcrypto.com/feed/",
    "https://cryptopotato.com/feed/",
    "https://beincrypto.com/feed/"
]

# ========================
# 🔹 Funciones
# ========================

def get_sentiment_score(keyword):
    """Analiza noticias relacionadas y devuelve puntaje de sentimiento promedio."""
    sentiments = []
    news_list = []
    for feed in news_feeds:
        d = feedparser.parse(feed)
        for entry in d.entries[:5]:
            title = entry.title
            if keyword.lower() in title.lower():
                polarity = TextBlob(title).sentiment.polarity
                sentiments.append(polarity)
                news_list.append(title)
    if sentiments:
        return np.mean(sentiments), news_list[:3]
    return 0, []

def calculate_indicators(symbol):
    """Descarga velas de 15m y calcula RSI, MACD y EMAs."""
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=15m&limit=100"
    data = requests.get(url).json()

    if not isinstance(data, list):
        return None

    df = pd.DataFrame(data, columns=[
        "time","o","h","l","c","v","ct","qv","n","tb","tqv","i"
    ])
    df["c"] = df["c"].astype(float)

    df["rsi"] = ta.momentum.RSIIndicator(df["c"], window=14).rsi()
    macd = ta.trend.MACD(df["c"], window_slow=26, window_fast=12, window_sign=9)
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["ema50"] = ta.trend.EMAIndicator(df["c"], window=50).ema_indicator()
    df["ema200"] = ta.trend.EMAIndicator(df["c"], window=200).ema_indicator()

    return df.iloc[-1]

def analyze_market():
    print(f"🔍 Analizando {len(symbols)} monedas...")
    for symbol in symbols:
        try:
            last = calculate_indicators(symbol)
            if last is None:
                continue

            close_price = last["c"]
            rsi = last["rsi"]
            macd = last["macd"]
            macd_signal = last["macd_signal"]
            ema50 = last["ema50"]
            ema200 = last["ema200"]

            signal = None
            confidence = 0

            # Estrategia base
            if rsi < 30 and macd > macd_signal and ema50 > ema200:
                signal = "LONG"
                confidence = 0.7
            elif rsi > 70 and macd < macd_signal and ema50 < ema200:
                signal = "SHORT"
                confidence = 0.7

            if signal:
                sentiment, news_list = get_sentiment_score(symbol.replace("USDT",""))
                confidence = min(1.0, confidence + abs(sentiment)*0.3)  # Ajuste con noticias

                tp = round(close_price * (1.02 if signal == "LONG" else 0.98), 6)
                sl = round(close_price * (0.98 if signal == "LONG" else 1.02), 6)

                msg = (
                    f"🔔 Señal {signal} {symbol}\n"
                    f"💰 Entrada: {close_price}\n"
                    f"🎯 TP: {tp}\n"
                    f"🛡 SL: {sl}\n"
                    f"📊 Confianza: {confidence*100:.1f}%\n"
                    f"🌎 Sentimiento mercado: {sentiment*100:.1f}%\n"
                )

                if news_list:
                    msg += "📰 Noticias:\n" + "\n".join(f"- {n}" for n in news_list)

                bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
                print(f"📤 Señal enviada: {symbol} {signal}")

                with open(CSV_FILE, mode='a', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        datetime.datetime.now(), symbol, signal, close_price, tp, sl,
                        f"{confidence*100:.1f}%", f"{sentiment*100:.1f}%", "; ".join(news_list)
                    ])

        except Exception as e:
            print(f"⚠️ Error analizando {symbol}: {e}")

def heartbeat():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"✅ Bot activo - {now}")

# ========================
# 🔹 Scheduler
# ========================
schedule.every(15).minutes.do(analyze_market)
schedule.every().hour.do(heartbeat)

bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="🚀 Bot de alertas Binance + Noticias iniciado correctamente...")
print("✅ Bot iniciado. Analiza cada 15 minutos y heartbeat cada 1 hora...")

while True:
    schedule.run_pending()
    time.sleep(1)

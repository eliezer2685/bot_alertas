import os, json, time, datetime, requests, random
import pandas as pd
import numpy as np
import schedule
import feedparser
from textblob import TextBlob
from telegram import Bot
from binance.client import Client
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD

# ===🔧 CONFIGURACIÓN ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    print("❌ Faltan variables de entorno TELEGRAM.")
    exit()

bot = Bot(token=TELEGRAM_TOKEN)

# Binance Spot client sin necesidad de API/Secret
client = Client()

# ===📊 MONEDAS ===
ALL_SYMBOLS = [
    "BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","SOLUSDT","DOGEUSDT","ADAUSDT","TRXUSDT","MATICUSDT","LTCUSDT",
    "DOTUSDT","SHIBUSDT","AVAXUSDT","UNIUSDT","ATOMUSDT","LINKUSDT","XLMUSDT","FILUSDT","ICPUSDT","APTUSDT",
    "ARBUSDT","SANDUSDT","MANAUSDT","APEUSDT","AXSUSDT","NEARUSDT","EOSUSDT","FLOWUSDT","XTZUSDT","THETAUSDT",
    "AAVEUSDT","GRTUSDT","RUNEUSDT","KAVAUSDT","CRVUSDT","FTMUSDT","CHZUSDT","SNXUSDT","LDOUSDT","OPUSDT",
    "COMPUSDT","DYDXUSDT","BLURUSDT","RNDRUSDT","GMTUSDT","1INCHUSDT","OCEANUSDT","SUIUSDT","PYTHUSDT","JTOUSDT",
    "PEPEUSDT","TIAUSDT","ENJUSDT","HOOKUSDT","IDUSDT","MEMEUSDT","STGUSDT","WLDUSDT","BICOUSDT","1000SATSUSDT"
]

LAST_COINS_FILE = "last_coins.json"
SENT_ALERTS_FILE = "sent_alerts.json"
FAILED_COUNT_FILE = "failed_counts.json"

# ===🗞️ FEEDS DE NOTICIAS ===
NEWS_FEEDS = [
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

# ===📁 CARGA Y GUARDADO JSON ===
def save_json(filename, data):
    with open(filename, 'w') as f:
        json.dump(data, f)

def load_json(filename):
    if os.path.exists(filename):
        with open(filename) as f:
            return json.load(f)
    return {}

# ===📉 OBTIENE VELAS Y CALCULA INDICADORES ===
def get_indicators(symbol):
    try:
        klines = client.get_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_15MINUTE, limit=100)
        df = pd.DataFrame(klines, columns=["t","o","h","l","c","v","ct","qv","n","tb","qtb","ignore"])
        df["c"] = df["c"].astype(float)
        df["v"] = df["v"].astype(float)
        close = df["c"]

        rsi = RSIIndicator(close).rsi().iloc[-1]
        ema50 = EMAIndicator(close, window=50).ema_indicator().iloc[-1]
        ema200 = EMAIndicator(close, window=200).ema_indicator().iloc[-1]
        macd_line = MACD(close).macd().iloc[-1]
        macd_signal = MACD(close).macd_signal().iloc[-1]
        volume = df["v"].iloc[-1]
        avg_volume = df["v"].rolling(window=20).mean().iloc[-1]

        return {
            "price": close.iloc[-1],
            "rsi": rsi,
            "ema50": ema50,
            "ema200": ema200,
            "macd": macd_line,
            "macd_signal": macd_signal,
            "volume": volume,
            "avg_volume": avg_volume
        }
    except:
        return None

# ===🧠 ESTRATEGIAS ===
def strategy_1(ind):
    return ind["rsi"] < 30 and ind["macd"] > ind["macd_signal"] and ind["ema50"] > ind["ema200"]

def strategy_2(ind):
    return ind["volume"] > 1.5 * ind["avg_volume"]

def get_news_sentiment(symbol):
    keyword = symbol.replace("USDT", "")
    for url in NEWS_FEEDS:
        feed = feedparser.parse(url)
        for entry in feed.entries[:5]:
            if keyword.lower() in entry.title.lower():
                polarity = TextBlob(entry.title).sentiment.polarity
                if polarity > 0.1:
                    return f"🟢 Noticia positiva: {entry.title}"
                elif polarity < -0.1:
                    return f"🔴 Noticia negativa: {entry.title}"
    return None

# ===🔍 ANÁLISIS DE UNA MONEDA ===
def analyze_symbol(symbol):
    ind = get_indicators(symbol)
    if not ind:
        return None

    score = 0
    details = []

    if strategy_1(ind):
        score += 1
        details.append("MACD+EMA+RSI")

    if strategy_2(ind):
        score += 1
        details.append("Volumen")

    news = get_news_sentiment(symbol)
    if news:
        score += 1
        details.append("Noticias")

    prob = round((score / 3) * 100)

    if score >= 2:
        signal_type = "LONG" if ind["macd"] > ind["macd_signal"] else "SHORT"
        price = ind["price"]
        tp = round(price * (1.02 if signal_type == "LONG" else 0.98), 6)
        sl = round(price * (0.98 if signal_type == "LONG" else 1.02), 6)

        return {
            "symbol": symbol,
            "prob": prob,
            "signal": signal_type,
            "price": price,
            "tp": tp,
            "sl": sl,
            "news": news,
            "details": ", ".join(details)
        }
    return None

# ===📌 SELECCIÓN INICIAL DE 30 MONEDAS ===
def initialize_daily_selection():
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    current = load_json(LAST_COINS_FILE)
    if current.get("date") != today:
        selected = random.sample(ALL_SYMBOLS, 30)
        save_json(LAST_COINS_FILE, {"date": today, "symbols": selected})
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"✅ Monedas del día seleccionadas: {selected}")
        save_json(FAILED_COUNT_FILE, {})

# ===📢 ENVÍO DE ALERTAS ===
def send_alerts():
    data = load_json(LAST_COINS_FILE)
    sent = load_json(SENT_ALERTS_FILE)
    failed = load_json(FAILED_COUNT_FILE)
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    alerts_today = sent.get(today, [])

    if not data.get("symbols"):
        print("⚠️ Aún no hay monedas seleccionadas para hoy.")
        return

    filtered_symbols = []

    for symbol in data["symbols"]:
        result = analyze_symbol(symbol)
        if result and symbol not in alerts_today:
            msg = (
                f"📢 Señal Confirmada\n"
                f"Moneda: {symbol}\n"
                f"Tipo: {result['signal']}\n"
                f"Entrada: {result['price']}\n"
                f"TP: {result['tp']}\n"
                f"SL: {result['sl']}\n"
                f"Probabilidad: {result['prob']}%\n"
                f"Estrategias: {result['details']}\n"
            )
            if result['news']:
                msg += f"📰 {result['news']}\n"

            bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
            alerts_today.append(symbol)
            failed[symbol] = 0
        else:
            failed[symbol] = failed.get(symbol, 0) + 1
            if failed[symbol] < 4:
                filtered_symbols.append(symbol)

    sent[today] = alerts_today
    save_json(SENT_ALERTS_FILE, sent)
    save_json(FAILED_COUNT_FILE, failed)
    save_json(LAST_COINS_FILE, {"date": today, "symbols": filtered_symbols})

# ===📊 RESUMEN CADA HORA ===
def send_summary():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    data = load_json(LAST_COINS_FILE)
    selected = data.get("symbols", [])
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"⏱️ Bot activo {now}. Monedas analizadas: {selected}")

# ===🕓 SCHEDULER ===
schedule.every().day.at("06:00").do(initialize_daily_selection)
schedule.every().hour.do(initialize_daily_selection)
schedule.every(15).minutes.do(send_alerts)
schedule.every().hour.do(send_summary)

# ===🚀 INICIO ===
bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="🚀 Bot de análisis iniciado y funcionando...")
initialize_daily_selection()

while True:
    schedule.run_pending()
    time.sleep(1)
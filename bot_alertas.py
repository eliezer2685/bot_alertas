import os, time, datetime, csv, requests
import pandas as pd
import numpy as np
import ta
import feedparser
from textblob import TextBlob
from telegram import Bot
import schedule
from binance.client import Client

# ===================== CONFIGURACIÓN =====================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    print("❌ ERROR: Variables de entorno no configuradas.")
    exit()

bot = Bot(token=TELEGRAM_TOKEN)

CSV_FILE = "historico_senales.csv"
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Fecha", "Moneda", "Señal", "Precio Entrada", "TP", "SL", "Noticia", "Confianza", "Estrategia"])

# Lista de 60 monedas populares
symbols = [
    "BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","SOLUSDT","DOGEUSDT","ADAUSDT","TRXUSDT","MATICUSDT","LTCUSDT",
    "DOTUSDT","SHIBUSDT","AVAXUSDT","UNIUSDT","ATOMUSDT","LINKUSDT","XLMUSDT","FILUSDT","ICPUSDT","APTUSDT",
    "ARBUSDT","SANDUSDT","MANAUSDT","APEUSDT","AXSUSDT","NEARUSDT","EOSUSDT","FLOWUSDT","XTZUSDT","THETAUSDT",
    "AAVEUSDT","GRTUSDT","RUNEUSDT","KAVAUSDT","CRVUSDT","FTMUSDT","CHZUSDT","SNXUSDT","LDOUSDT","OPUSDT",
    "COMPUSDT","DYDXUSDT","BLURUSDT","RNDRUSDT","GMTUSDT","1INCHUSDT","OCEANUSDT","SUIUSDT","PYTHUSDT","JTOUSDT",
    "FTTUSDT","CFXUSDT","TWTUSDT","INJUSDT","FLUXUSDT","CELRUSDT","IMXUSDT","WAVESUSDT","MINAUSDT","ROSEUSDT"
]

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

client = Client()  # Spot sin API key

# ===================== FUNCIONES =====================
def check_news(symbol):
    keyword = symbol.replace("USDT", "")
    for feed in news_feeds:
        try:
            d = feedparser.parse(feed)
            for entry in d.entries[:5]:
                title = entry.title
                if keyword.lower() in title.lower():
                    sentiment = TextBlob(title).sentiment.polarity
                    if sentiment > 0.1:
                        return f"🟢 Positiva: \"{title}\"", 70
                    elif sentiment < -0.1:
                        return f"🔴 Negativa: \"{title}\"", 30
        except:
            pass
    return None, 50

def get_klines(symbol):
    """Descarga 200 velas de 15m para análisis."""
    candles = client.get_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_15MINUTE, limit=200)
    df = pd.DataFrame(candles, columns=['time','o','h','l','c','v','ct','qv','n','taker_b','taker_q','ignore'])
    df['c'] = df['c'].astype(float)
    df['h'] = df['h'].astype(float)
    df['l'] = df['l'].astype(float)
    return df

def analyze_symbol(symbol):
    df = get_klines(symbol)

    close = df['c']
    rsi = ta.momentum.RSIIndicator(close, window=14).rsi().iloc[-1]
    macd = ta.trend.MACD(close).macd().iloc[-1]
    macd_signal = ta.trend.MACD(close).macd_signal().iloc[-1]
    ema50 = ta.trend.EMAIndicator(close, window=50).ema_indicator().iloc[-1]
    ema200 = ta.trend.EMAIndicator(close, window=200).ema_indicator().iloc[-1]
    price = close.iloc[-1]

    # Estrategia 1
    signal1 = rsi < 30 and macd > macd_signal and ema50 > ema200
    signal2 = rsi > 70 and macd < macd_signal and ema50 < ema200

    # Estrategia 2: RSI extremo + MACD divergente
    signal3 = rsi < 25 and macd > macd_signal
    signal4 = rsi > 75 and macd < macd_signal

    # Estrategia 3: Cruce de EMAs
    signal5 = ema50 > ema200 and macd > macd_signal
    signal6 = ema50 < ema200 and macd < macd_signal

    signal_type = None
    strategy = None
    if signal1 or signal3 or signal5:
        signal_type = "LONG"
    elif signal2 or signal4 or signal6:
        signal_type = "SHORT"

    if signal1: strategy = "RSI+MACD+EMA"
    elif signal2: strategy = "RSI+MACD+EMA"
    elif signal3 or signal4: strategy = "RSI+MACD"
    elif signal5 or signal6: strategy = "Cruce EMA"

    if signal_type:
        tp = round(price * (1.02 if signal_type=="LONG" else 0.98), 6)
        sl = round(price * (0.98 if signal_type=="LONG" else 1.02), 6)
        news, confianza = check_news(symbol)
        msg = (
            f"🔔 Señal {signal_type}\n"
            f"Moneda: {symbol}\n"
            f"Estrategia: {strategy}\n"
            f"Entrada: {price}\n"
            f"TP: {tp}\n"
            f"SL: {sl}\n"
            f"Confianza: {confianza}%\n"
        )
        if news:
            msg += f"{news}\n"

        with open(CSV_FILE, mode='a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([datetime.datetime.now(), symbol, signal_type, price, tp, sl, news if news else "", confianza, strategy])

        return msg
    return None

# ===================== TAREAS =====================
signals_last_hour = []

def analyze_market():
    global signals_last_hour
    print(f"⏳ Analizando {len(symbols)} monedas...")
    for symbol in symbols:
        try:
            msg = analyze_symbol(symbol)
            if msg:
                bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
                signals_last_hour.append(msg)
        except Exception as e:
            print(f"⚠️ Error {symbol}: {e}")

def send_summary():
    global signals_last_hour
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    summary = f"📊 Resumen {now}\nSeñales últimas 1h: {len(signals_last_hour)}"
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=summary)
    signals_last_hour = []

# Scheduler
schedule.every(15).minutes.do(analyze_market)
schedule.every().hour.do(send_summary)

bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="🚀 Bot iniciado correctamente. Analiza cada 15m, resumen 1h.")

print("✅ Bot iniciado")
while True:
    schedule.run_pending()
    time.sleep(1)

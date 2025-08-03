import os
import time
import datetime
import requests
import pandas as pd
import ta
import feedparser
import csv
from textblob import TextBlob
from telegram import Bot
import schedule
from binance.client import Client

# 🔹 Variables de entorno para Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")

if not all([TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
    print("❌ ERROR: Variables de entorno no configuradas.")
    exit()

bot = Bot(token=TELEGRAM_TOKEN)

# 🔹 CSV para histórico
CSV_FILE = "historico_senales.csv"
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Fecha", "Moneda", "Señal", "Precio Entrada", "TP", "SL", "Noticia"])

# 🔹 Lista de 50 monedas spot populares en Binance
symbols = [
    "BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","SOLUSDT","DOGEUSDT","ADAUSDT","TRXUSDT","MATICUSDT","LTCUSDT",
    "DOTUSDT","SHIBUSDT","AVAXUSDT","UNIUSDT","ATOMUSDT","LINKUSDT","XLMUSDT","FILUSDT","ICPUSDT","APTUSDT",
    "ARBUSDT","SANDUSDT","MANAUSDT","APEUSDT","AXSUSDT","NEARUSDT","EOSUSDT","FLOWUSDT","XTZUSDT","THETAUSDT",
    "AAVEUSDT","GRTUSDT","RUNEUSDT","KAVAUSDT","CRVUSDT","FTMUSDT","CHZUSDT","SNXUSDT","LDOUSDT","OPUSDT",
    "COMPUSDT","DYDXUSDT","BLURUSDT","RNDRUSDT","GMTUSDT","1INCHUSDT","OCEANUSDT","SUIUSDT","PYTHUSDT","JTOUSDT"
]

# 🔹 RSS de noticias sobre criptos
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

# 🔹 Inicializamos cliente Binance sin API Key (Spot público)
client = Client()

# 🔹 Analiza noticias y devuelve sentimiento
def check_news(symbol):
    keyword = symbol.replace("USDT", "")
    for feed in news_feeds:
        d = feedparser.parse(feed)
        for entry in d.entries[:5]:
            title = entry.title
            if keyword.lower() in title.lower():
                sentiment = TextBlob(title).sentiment.polarity
                if sentiment > 0.1:
                    return f"🟢 Noticia positiva: \"{title}\""
                elif sentiment < -0.1:
                    return f"🔴 Noticia negativa: \"{title}\""
    return None

# 🔹 Estrategia técnica
def analyze_market():
    print(f"🔍 Analizando mercado... {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    for symbol in symbols:
        try:
            # Descargar últimos 100 candles de 15m
            klines = client.get_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_15MINUTE, limit=100)
            df = pd.DataFrame(klines, columns=[
                'time','o','h','l','c','v','close_time','qav','num_trades','tbbav','tbqav','ignore'
            ])
            df['c'] = df['c'].astype(float)

            # Indicadores técnicos
            close = df['c']
            rsi = ta.momentum.RSIIndicator(close, window=14).rsi().iloc[-1]
            macd = ta.trend.MACD(close).macd().iloc[-1]
            macd_signal = ta.trend.MACD(close).macd_signal().iloc[-1]
            ema50 = ta.trend.EMAIndicator(close, window=50).ema_indicator().iloc[-1]
            ema200 = ta.trend.EMAIndicator(close, window=200).ema_indicator().iloc[-1]
            price = close.iloc[-1]

            # Estrategia
            signal = None
            if rsi < 30 and macd > macd_signal and ema50 > ema200:
                signal = "LONG"
            elif rsi > 70 and macd < macd_signal and ema50 < ema200:
                signal = "SHORT"

            if signal:
                tp = round(price * (1.02 if signal == "LONG" else 0.98), 6)
                sl = round(price * (0.98 if signal == "LONG" else 1.02), 6)
                news = check_news(symbol)
                msg = (
                    f"🔔 Señal Detectada\n"
                    f"Moneda: {symbol}\n"
                    f"Tipo: {signal}\n"
                    f"Entrada: {price}\n"
                    f"TP: {tp}\n"
                    f"SL: {sl}\n"
                    f"Apalancamiento sugerido: x10\n"
                )
                if news:
                    msg += f"{news}\n"

                # Enviar a Telegram
                bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
                print(f"📤 Señal enviada: {symbol} {signal}")

                # Guardar en CSV
                with open(CSV_FILE, mode='a', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([datetime.datetime.now(), symbol, signal, price, tp, sl, news if news else ""])

        except Exception as e:
            print(f"⚠️ Error analizando {symbol}: {e}")

# 🔹 Heartbeat cada 1 hora
def heartbeat():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"✅ Bot activo - {now}")

# 🔹 Scheduler
schedule.every(15).minutes.do(analyze_market)
schedule.every().hour.do(heartbeat)

# 🔹 Aviso inicial
bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="🚀 Bot de alertas Binance Spot iniciado correctamente...")

print("✅ Bot iniciado. Analiza cada 15 minutos y heartbeat cada 1 hora...")
while True:
    schedule.run_pending()
    time.sleep(1)

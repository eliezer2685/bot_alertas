import os, time, datetime, csv
import pandas as pd
import numpy as np
import requests
import feedparser
import schedule
from textblob import TextBlob
from telegram import Bot
from binance.client import Client

# =====================================
# 🔹 CONFIGURACIÓN INICIAL
# =====================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")

if not all([TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
    print("❌ ERROR: Variables de entorno no configuradas (TELEGRAM_TOKEN o CHAT_ID).")
    exit()

bot = Bot(token=TELEGRAM_TOKEN)

CSV_FILE = "historico_senales.csv"
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Fecha", "Moneda", "Tipo", "Señal", "Precio Entrada", "TP", "SL", "Noticia", "Fuerza", "Confianza"])

# 🔹 Lista de 60 monedas spot populares en Binance
symbols = [
    "BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","SOLUSDT","DOGEUSDT","ADAUSDT","TRXUSDT","MATICUSDT","LTCUSDT",
    "DOTUSDT","SHIBUSDT","AVAXUSDT","UNIUSDT","ATOMUSDT","LINKUSDT","XLMUSDT","FILUSDT","ICPUSDT","APTUSDT",
    "ARBUSDT","SANDUSDT","MANAUSDT","APEUSDT","AXSUSDT","NEARUSDT","EOSUSDT","FLOWUSDT","XTZUSDT","THETAUSDT",
    "AAVEUSDT","GRTUSDT","RUNEUSDT","KAVAUSDT","CRVUSDT","FTMUSDT","CHZUSDT","SNXUSDT","LDOUSDT","OPUSDT",
    "COMPUSDT","DYDXUSDT","BLURUSDT","RNDRUSDT","GMTUSDT","1INCHUSDT","OCEANUSDT","SUIUSDT","PYTHUSDT","JTOUSDT",
    "FTTUSDT","WOOUSDT","COTIUSDT","CELRUSDT","ANKRUSDT","STORJUSDT","HOTUSDT","ZILUSDT","ENJUSDT","RVNUSDT"
]

# 🔹 Noticias RSS
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

# Cliente de Binance Spot sin autenticación
client = Client()

# =====================================
# 🔹 Funciones auxiliares
# =====================================
def check_news(symbol):
    """Busca noticias recientes sobre la moneda y devuelve sentimiento."""
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

def get_klines(symbol, interval="15m", limit=100):
    """Obtiene velas históricas para calcular indicadores"""
    data = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    df = pd.DataFrame(data, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'trades', 'tbbav', 'tbqav', 'ignore'
    ])
    df['close'] = df['close'].astype(float)
    df['volume'] = df['volume'].astype(float)
    return df

def calculate_indicators(df):
    """Calcula RSI, MACD y EMAs"""
    close = df['close']

    # EMA
    df['EMA50'] = close.ewm(span=50).mean()
    df['EMA200'] = close.ewm(span=200).mean()

    # RSI
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # MACD
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    df['MACD'] = ema12 - ema26
    df['MACD_signal'] = df['MACD'].ewm(span=9).mean()

    return df

def calculate_confidence(rsi, macd, macd_signal, fuerza):
    """Calcula un puntaje de confianza 0-100"""
    score = 0
    if rsi < 25 or rsi > 75:
        score += 40
    elif rsi < 30 or rsi > 70:
        score += 25
    if abs(macd - macd_signal) > 0.1:
        score += 30
    else:
        score += 15
    score += min(int(fuerza*2), 30)
    return min(score, 100)

def analyze_market():
    """Analiza las 60 monedas y envía solo señales confirmadas, guarda tempranas en CSV"""
    print(f"🔍 Analizando {len(symbols)} monedas a las {datetime.datetime.now()}...")
    signals = []

    for symbol in symbols:
        try:
            df = get_klines(symbol)
            df = calculate_indicators(df)
            last = df.iloc[-1]
            prev = df.iloc[-2]

            price = last['close']
            rsi = last['RSI']
            macd = last['MACD']
            macd_signal = last['MACD_signal']
            ema50 = last['EMA50']
            ema200 = last['EMA200']

            # Señal confirmada
            signal = None
            if rsi < 30 and macd > macd_signal and ema50 > ema200:
                signal = "LONG"
            elif rsi > 70 and macd < macd_signal and ema50 < ema200:
                signal = "SHORT"

            # Señal temprana
            early_signal = None
            if prev['MACD'] < prev['MACD_signal'] and macd > macd_signal and abs(ema50-ema200)/ema200 < 0.01:
                early_signal = "LONG"
            elif prev['MACD'] > prev['MACD_signal'] and macd < macd_signal and abs(ema50-ema200)/ema200 < 0.01:
                early_signal = "SHORT"

            # Guardar fuerza y confianza
            if signal or early_signal:
                tipo = "✅ Confirmada" if signal else "⚡ Temprana"
                fuerza = abs(rsi-50) + abs(macd-macd_signal)
                confidence = calculate_confidence(rsi, macd, macd_signal, fuerza)

                tp = round(price * (1.02 if (signal or early_signal) == "LONG" else 0.98), 6)
                sl = round(price * (0.98 if (signal or early_signal) == "LONG" else 1.02), 6)
                news = check_news(symbol)

                # Guardar todas las señales en CSV
                with open(CSV_FILE, mode='a', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([datetime.datetime.now(), symbol, tipo, signal or early_signal, price, tp, sl, news or "", fuerza, confidence])

                # Solo enviar las confirmadas y con confianza >= 70%
                if signal and confidence >= 70:
                    signals.append({
                        "symbol": symbol,
                        "tipo": tipo,
                        "signal": signal,
                        "price": price,
                        "tp": tp,
                        "sl": sl,
                        "news": news,
                        "confianza": confidence
                    })

        except Exception as e:
            print(f"⚠️ Error analizando {symbol}: {e}")

    # Ordenar y enviar solo top 5
    top_signals = sorted(signals, key=lambda x: x['confianza'], reverse=True)[:5]

    for sig in top_signals:
        msg = (
            f"🔔 Señal {sig['tipo']}\n"
            f"Moneda: {sig['symbol']}\n"
            f"Tipo: {sig['signal']}\n"
            f"Entrada: {sig['price']}\n"
            f"TP: {sig['tp']}\n"
            f"SL: {sig['sl']}\n"
            f"Confianza: {sig['confianza']}%\n"
        )
        if sig['news']:
            msg += f"{sig['news']}\n"

        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
        print(f"📤 Confirmada enviada: {sig['symbol']} {sig['signal']}")

def heartbeat():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"✅ Bot activo - {now}")

# =====================================
# 🔹 Scheduler
# =====================================
schedule.every(15).minutes.do(analyze_market)
schedule.every().hour.do(heartbeat)

bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="🚀 Bot de alertas Binance Spot iniciado. Solo señales confirmadas (≥70% confianza).")
print("✅ Bot iniciado. Analiza cada 15 minutos...")

while True:
    schedule.run_pending()
    time.sleep(1)

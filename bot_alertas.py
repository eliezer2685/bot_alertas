import os, time, datetime, csv
import pandas as pd
import numpy as np
import ccxt
import schedule
from telegram import Bot
from textblob import TextBlob
import feedparser

# ------------------------
# 🔹 Configuración Telegram
# ------------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")

if not all([TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
    print("❌ ERROR: Variables de entorno de Telegram no configuradas.")
    exit()

bot = Bot(token=TELEGRAM_TOKEN)

# ------------------------
# 🔹 Configuración Binance
# ------------------------
BINANCE_KEY = os.getenv("BINANCE_KEY")
BINANCE_SECRET = os.getenv("BINANCE_SECRET")

binance = ccxt.binance({
    "apiKey": BINANCE_KEY,
    "secret": BINANCE_SECRET,
    "enableRateLimit": True,
    "options": {"defaultType": "spot"}  # 🔹 Solo Spot
})

# ------------------------
# 🔹 Lista de 50 monedas spot
# ------------------------
symbols = [
    "BTC/USDT","ETH/USDT","BNB/USDT","XRP/USDT","SOL/USDT","DOGE/USDT","ADA/USDT","TRX/USDT","MATIC/USDT","LTC/USDT",
    "DOT/USDT","SHIB/USDT","AVAX/USDT","UNI/USDT","ATOM/USDT","LINK/USDT","XLM/USDT","FIL/USDT","ICP/USDT","APT/USDT",
    "ARB/USDT","SAND/USDT","MANA/USDT","APE/USDT","AXS/USDT","NEAR/USDT","EOS/USDT","FLOW/USDT","XTZ/USDT","THETA/USDT",
    "AAVE/USDT","GRT/USDT","RUNE/USDT","KAVA/USDT","CRV/USDT","FTM/USDT","CHZ/USDT","SNX/USDT","LDO/USDT","OP/USDT",
    "COMP/USDT","DYDX/USDT","BLUR/USDT","RNDR/USDT","GMT/USDT","1INCH/USDT","OCEAN/USDT","SUI/USDT","PYTH/USDT","JTO/USDT"
]

# ------------------------
# 🔹 CSV histórico
# ------------------------
CSV_FILE = "historico_senales.csv"
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Fecha", "Moneda", "Señal", "Precio Entrada", "TP", "SL", "Noticia"])

# ------------------------
# 🔹 RSS de noticias
# ------------------------
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

def check_news(symbol):
    keyword = symbol.split("/")[0]
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

# ------------------------
# 🔹 Cálculo de indicadores
# ------------------------
def calculate_indicators(df):
    df["EMA50"] = df["close"].ewm(span=50).mean()
    df["EMA200"] = df["close"].ewm(span=200).mean()

    delta = df["close"].diff()
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = pd.Series(gain).rolling(14).mean()
    avg_loss = pd.Series(loss).rolling(14).mean()
    rs = avg_gain / avg_loss
    df["RSI"] = 100 - (100 / (1 + rs))

    short_ema = df["close"].ewm(span=12).mean()
    long_ema = df["close"].ewm(span=26).mean()
    df["MACD"] = short_ema - long_ema
    df["MACD_signal"] = df["MACD"].ewm(span=9).mean()

    return df

# ------------------------
# 🔹 Estrategia principal
# ------------------------
def analyze_market():
    print(f"🔍 Analizando {len(symbols)} monedas Spot...")
    for symbol in symbols:
        try:
            ohlcv = binance.fetch_ohlcv(symbol, timeframe="15m", limit=200)
            df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df = calculate_indicators(df)

            last = df.iloc[-1]
            rsi = last["RSI"]
            macd = last["MACD"]
            macd_signal = last["MACD_signal"]
            ema50 = last["EMA50"]
            ema200 = last["EMA200"]
            volume = last["volume"]
            price = last["close"]

            # Filtramos señales de alta probabilidad
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
                    f"🔔 Señal {signal}\n"
                    f"Moneda: {symbol}\n"
                    f"Entrada: {price}\n"
                    f"TP: {tp}\n"
                    f"SL: {sl}\n"
                    f"RSI: {rsi:.2f}\n"
                )
                if news:
                    msg += f"{news}\n"

                bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
                print(f"📤 Señal enviada: {symbol} {signal}")

                with open(CSV_FILE, mode='a', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([datetime.datetime.now(), symbol, signal, price, tp, sl, news if news else ""])

        except Exception as e:
            print(f"⚠️ Error analizando {symbol}: {e}")

# ------------------------
# 🔹 Heartbeat
# ------------------------
def heartbeat():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"✅ Bot Spot activo - {now}")

# ------------------------
# 🔹 Scheduler
# ------------------------
schedule.every(15).minutes.do(analyze_market)
schedule.every().hour.do(heartbeat)

bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="🚀 Bot Spot Binance iniciado (15 min)...")
print("✅ Bot iniciado. Analiza cada 15 minutos y heartbeat cada 1 hora...")

while True:
    schedule.run_pending()
    time.sleep(1)

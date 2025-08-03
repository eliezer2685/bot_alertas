import os, time, datetime, csv, requests
import pandas as pd
import ta
import feedparser
from textblob import TextBlob
from telegram import Bot
import schedule
from binance.client import Client

# === Variables de entorno ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")

if not all([TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
    print("❌ ERROR: Variables de entorno no configuradas.")
    exit()

bot = Bot(token=TELEGRAM_TOKEN)

# === CSV histórico ===
CSV_FILE = "historico_senales.csv"
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Fecha", "Moneda", "Señal", "Precio Entrada", "TP", "SL", "Noticia"])

# === Lista de monedas (spot) ===
symbols = [
    "BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","SOLUSDT","DOGEUSDT","ADAUSDT","TRXUSDT","MATICUSDT","LTCUSDT",
    "DOTUSDT","SHIBUSDT","AVAXUSDT","UNIUSDT","ATOMUSDT","LINKUSDT","XLMUSDT","FILUSDT","ICPUSDT","APTUSDT",
    "ARBUSDT","SANDUSDT","MANAUSDT","APEUSDT","AXSUSDT","NEARUSDT","EOSUSDT","FLOWUSDT","XTZUSDT","THETAUSDT",
    "AAVEUSDT","GRTUSDT","RUNEUSDT","KAVAUSDT","CRVUSDT","FTMUSDT","CHZUSDT","SNXUSDT","LDOUSDT","OPUSDT",
    "COMPUSDT","DYDXUSDT","BLURUSDT","RNDRUSDT","GMTUSDT","1INCHUSDT","OCEANUSDT","SUIUSDT","PYTHUSDT","JTOUSDT"
]

# === Feeds de noticias ===
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

# === Binance client (solo datos públicos) ===
client = Client()

# === Analiza noticias para una moneda ===
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

# === Estrategia de Trading Segura ===
def analyze_market():
    print(f"🔍 Analizando {len(symbols)} monedas...")
    for symbol in symbols:
        try:
            # Obtener velas de 15m (últimas 200)
            klines = client.get_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_15MINUTE, limit=200)
            df = pd.DataFrame(klines, columns=[
                "timestamp","open","high","low","close","volume","close_time","quote_asset_volume",
                "number_of_trades","taker_buy_base","taker_buy_quote","ignore"
            ])
            df["close"] = df["close"].astype(float)

            # Indicadores
            df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
            macd = ta.trend.MACD(df["close"])
            df["macd"] = macd.macd()
            df["macd_signal"] = macd.macd_signal()
            df["ema50"] = ta.trend.EMAIndicator(df["close"], window=50).ema_indicator()
            df["ema200"] = ta.trend.EMAIndicator(df["close"], window=200).ema_indicator()

            # Último valor
            close_price = df["close"].iloc[-1]
            rsi = df["rsi"].iloc[-1]
            macd_val = df["macd"].iloc[-1]
            macd_signal = df["macd_signal"].iloc[-1]
            ema50 = df["ema50"].iloc[-1]
            ema200 = df["ema200"].iloc[-1]

            signal = None
            # Estrategia segura
            if rsi < 30 and macd_val > macd_signal and ema50 > ema200:
                signal = "LONG"
            elif rsi > 70 and macd_val < macd_signal and ema50 < ema200:
                signal = "SHORT"

            if signal:
                tp = round(close_price * (1.02 if signal == "LONG" else 0.98), 6)
                sl = round(close_price * (0.98 if signal == "LONG" else 1.02), 6)
                news = check_news(symbol)
                msg = (
                    f"🔔 Señal Detectada\n"
                    f"Moneda: {symbol}\n"
                    f"Tipo: {signal}\n"
                    f"Entrada: {close_price}\n"
                    f"TP: {tp}\n"
                    f"SL: {sl}\n"
                    f"Apalancamiento sugerido: x10\n"
                )
                if news:
                    msg += f"{news}\n"

                bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
                print(f"📤 Señal enviada: {symbol} {signal}")

                with open(CSV_FILE, mode='a', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([datetime.datetime.now(), symbol, signal, close_price, tp, sl, news if news else ""])

        except Exception as e:
            print(f"⚠️ Error analizando {symbol}: {e}")

# === Heartbeat cada hora ===
def heartbeat():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"✅ Bot activo - {now}")

# === Scheduler ===
schedule.every(15).minutes.do(analyze_market)
schedule.every().hour.do(heartbeat)

# Aviso inicial
bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="🚀 Bot de alertas Binance Spot iniciado correctamente...")

print("✅ Bot iniciado. Analiza cada 15 minutos y heartbeat cada 1 hora...")

while True:
    schedule.run_pending()
    time.sleep(1)

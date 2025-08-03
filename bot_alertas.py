import os, time, datetime, csv
import pandas as pd
import ta
import feedparser
from textblob import TextBlob
from telegram import Bot
import schedule
from binance.client import Client

# ========= CONFIGURACIÓN =========

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")

if not all([TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
    print("❌ ERROR: Variables de entorno no configuradas.")
    exit()

bot = Bot(token=TELEGRAM_TOKEN)

# Archivo CSV para histórico
CSV_FILE = "historico_senales.csv"
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Fecha", "Moneda", "Señal", "Precio Entrada", "TP", "SL", "Noticia"])

# Cliente Binance (solo spot, sin API key)
client = Client()

# Lista de 50 monedas spot populares
symbols = [
    "BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","SOLUSDT","DOGEUSDT","ADAUSDT","TRXUSDT","MATICUSDT","LTCUSDT",
    "DOTUSDT","SHIBUSDT","AVAXUSDT","UNIUSDT","ATOMUSDT","LINKUSDT","XLMUSDT","FILUSDT","ICPUSDT","APTUSDT",
    "ARBUSDT","SANDUSDT","MANAUSDT","APEUSDT","AXSUSDT","NEARUSDT","EOSUSDT","FLOWUSDT","XTZUSDT","THETAUSDT",
    "AAVEUSDT","GRTUSDT","RUNEUSDT","KAVAUSDT","CRVUSDT","FTMUSDT","CHZUSDT","SNXUSDT","LDOUSDT","OPUSDT",
    "COMPUSDT","DYDXUSDT","BLURUSDT","RNDRUSDT","GMTUSDT","1INCHUSDT","OCEANUSDT","SUIUSDT","PYTHUSDT","JTOUSDT"
]

# RSS de noticias sobre criptos
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

# ========= FUNCIONES =========

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

def get_klines_df(symbol):
    klines = client.get_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_15MINUTE, limit=200)
    df = pd.DataFrame(klines, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume', 
        'close_time', 'qav', 'num_trades', 'tbbav', 'tbqav', 'ignore'
    ])
    df['close'] = df['close'].astype(float)
    return df

def analyze_market():
    for symbol in symbols:
        try:
            df = get_klines_df(symbol)

            # Indicadores técnicos
            df['EMA50'] = ta.trend.EMAIndicator(df['close'], window=50).ema_indicator()
            df['EMA200'] = ta.trend.EMAIndicator(df['close'], window=200).ema_indicator()
            macd = ta.trend.MACD(df['close'])
            df['MACD'] = macd.macd()
            df['MACD_SIGNAL'] = macd.macd_signal()
            df['RSI'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()

            last = df.iloc[-1]
            rsi = last['RSI']
            macd_val = last['MACD']
            macd_signal = last['MACD_SIGNAL']
            ema50 = last['EMA50']
            ema200 = last['EMA200']
            price = last['close']

            signal = None
            if rsi < 30 and macd_val > macd_signal and ema50 > ema200:
                signal = "LONG"
            elif rsi > 70 and macd_val < macd_signal and ema50 < ema200:
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

                bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)

                with open(CSV_FILE, mode='a', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([datetime.datetime.now(), symbol, signal, price, tp, sl, news if news else ""])

        except Exception as e:
            print(f"⚠️ Error analizando {symbol}: {e}")

def heartbeat():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"✅ Bot activo - {now}")

# ========= SCHEDULER =========

schedule.every(15).minutes.do(analyze_market)
schedule.every().hour.do(heartbeat)

bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="🚀 Bot de alertas Binance SPOT iniciado correctamente...")

while True:
    schedule.run_pending()
    time.sleep(1)

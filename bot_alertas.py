import os, time, datetime, requests, ccxt, pandas as pd, ta, feedparser, csv
from textblob import TextBlob
from telegram import Bot
import schedule

# 🔹 Variables de entorno
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")

if not all([API_KEY, API_SECRET, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
    print("❌ ERROR: Variables de entorno no configuradas.")
    exit()

# 🔹 Conexión a Binance Futures
binance = ccxt.binance({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'enableRateLimit': True,
    'options': {'defaultType': 'future'}
})

bot = Bot(token=TELEGRAM_TOKEN)

# 🔹 CSV para histórico
CSV_FILE = "historico_senales.csv"
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Fecha", "Moneda", "Señal", "Precio Entrada", "TP", "SL", "Noticia"])

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

# 🔹 Analiza noticias y devuelve sentimiento
def check_news(symbol):
    keyword = symbol.split("/")[0]
    for feed in news_feeds:
        d = feedparser.parse(feed)
        for entry in d.entries[:5]:  # últimas 5 noticias
            title = entry.title
            if keyword.lower() in title.lower():
                sentiment = TextBlob(title).sentiment.polarity
                if sentiment > 0.1:
                    return f"🟢 Noticia positiva: \"{title}\""
                elif sentiment < -0.1:
                    return f"🔴 Noticia negativa: \"{title}\""
    return None

# 🔹 Obtiene todas las monedas de futuros USDT-M
def get_futures_symbols():
    markets = binance.load_markets()
    return [s for s in markets if s.endswith("/USDT") and markets[s]['type'] == 'future']

# 🔹 Analiza el mercado
def analyze_market():
    symbols = get_futures_symbols()
    print(f"🔍 Analizando {len(symbols)} monedas de futuros...")

    for symbol in symbols:
        try:
            ohlcv = binance.fetch_ohlcv(symbol, '15m', limit=200)
            df = pd.DataFrame(ohlcv, columns=['timestamp','open','high','low','close','volume'])
            df['close'] = df['close'].astype(float)

            # Indicadores técnicos
            df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
            macd = ta.trend.MACD(df['close'])
            df['macd'] = macd.macd()
            df['macd_signal'] = macd.macd_signal()
            df['ema50'] = ta.trend.EMAIndicator(df['close'], window=50).ema_indicator()
            df['ema200'] = ta.trend.EMAIndicator(df['close'], window=200).ema_indicator()

            last = df.iloc[-1]
            signal = None

            # Estrategia combinada
            if last['rsi'] < 30 and last['macd'] > last['macd_signal'] and last['ema50'] > last['ema200']:
                signal = "LONG"
            elif last['rsi'] > 70 and last['macd'] < last['macd_signal'] and last['ema50'] < last['ema200']:
                signal = "SHORT"

            if signal:
                price = last['close']
                tp = round(price * (1.02 if signal == "LONG" else 0.98), 6)
                sl = round(price * (0.98 if signal == "LONG" else 1.02), 6)

                # Revisar noticias
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

                # Enviar Telegram
                bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
                print(f"📤 Señal enviada: {symbol} {signal}")

                # Guardar histórico
                with open(CSV_FILE, mode='a', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([datetime.datetime.now(), symbol, signal, price, tp, sl, news if news else ""])

        except Exception as e:
            print(f"⚠️ Error analizando {symbol}: {e}")

# 🔹 Heartbeat (cada 1 hora)
def heartbeat():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"✅ Bot activo - {now}")

# 🔹 Scheduler
schedule.every(15).minutes.do(analyze_market)  # ⬅️ cada 15 minutos
schedule.every().hour.do(heartbeat)

# 🔹 Aviso inicial
bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="🚀 Bot de alertas iniciado correctamente y en ejecución...")

print("✅ Bot iniciado. Analiza cada 15 minutos y heartbeat cada 1 hora...")
while True:
    schedule.run_pending()
    time.sleep(1)

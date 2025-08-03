import os, time, datetime, requests, pandas as pd, ta, feedparser, csv
from textblob import TextBlob
from telegram import Bot
import schedule

# 🔹 Variables de entorno (solo Telegram)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")

if not all([TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
    print("❌ ERROR: Variables de entorno de Telegram no configuradas.")
    exit()

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

# 🔹 Obtener lista de símbolos de futuros sin API Key
def get_futures_symbols():
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    data = requests.get(url).json()
    symbols = [s['symbol'] for s in data['symbols'] if s['quoteAsset'] == 'USDT']
    return symbols

# 🔹 Obtener OHLCV público sin API Key
def fetch_ohlcv(symbol, interval='15m', limit=200):
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
    data = requests.get(url).json()
    ohlcv = []
    for k in data:
        ohlcv.append([
            k[0], float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])
        ])
    return pd.DataFrame(ohlcv, columns=['timestamp','open','high','low','close','volume'])

# 🔹 Analiza el mercado
def analyze_market():
    symbols = get_futures_symbols()
    print(f"🔍 Analizando {len(symbols)} monedas de futuros...")

    for symbol in symbols:
        try:
            df = fetch_ohlcv(symbol, '15m', 200)
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
                print(f"📤 Señal enviada: {symbol} {signal}")

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
schedule.every(15).minutes.do(analyze_market)
schedule.every().hour.do(heartbeat)

bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="🚀 Bot de alertas iniciado correctamente sin API Key...")

print("✅ Bot iniciado. Analiza cada 15 minutos y heartbeat cada 1 hora...")
while True:
    schedule.run_pending()
    time.sleep(1)

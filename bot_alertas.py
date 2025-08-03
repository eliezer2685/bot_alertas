import os, time, datetime, requests, pandas as pd, ta, feedparser, csv
from textblob import TextBlob
from telegram import Bot
import schedule
import ccxt

# 🔹 Variables de entorno
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

# 🔹 Lista de 50 monedas spot en Binance
symbols = [
    "BTC/USDT","ETH/USDT","BNB/USDT","XRP/USDT","SOL/USDT","DOGE/USDT","ADA/USDT","TRX/USDT","MATIC/USDT","LTC/USDT",
    "DOT/USDT","SHIB/USDT","AVAX/USDT","UNI/USDT","ATOM/USDT","LINK/USDT","XLM/USDT","FIL/USDT","ICP/USDT","APT/USDT",
    "ARB/USDT","SAND/USDT","MANA/USDT","APE/USDT","AXS/USDT","NEAR/USDT","EOS/USDT","FLOW/USDT","XTZ/USDT","THETA/USDT",
    "AAVE/USDT","GRT/USDT","RUNE/USDT","KAVA/USDT","CRV/USDT","FTM/USDT","CHZ/USDT","SNX/USDT","LDO/USDT","OP/USDT",
    "COMP/USDT","DYDX/USDT","BLUR/USDT","RNDR/USDT","GMT/USDT","1INCH/USDT","OCEAN/USDT","SUI/USDT","PYTH/USDT","JTO/USDT"
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

# 🔹 Conexión a Binance Spot (sin API Key)
binance = ccxt.binance()

# 🔹 Analiza noticias y devuelve sentimiento
def check_news(symbol):
    keyword = symbol.replace("/USDT", "")
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

# 🔹 Estrategia técnica usando datos de Binance Spot
def analyze_market():
    print(f"🔍 Analizando {len(symbols)} monedas... {datetime.datetime.now()}", flush=True)
    for symbol in symbols:
        try:
            ohlcv = binance.fetch_ohlcv(symbol, timeframe='15m', limit=50)
            df = pd.DataFrame(ohlcv, columns=['timestamp','open','high','low','close','volume'])
            df['rsi'] = ta.momentum.rsi(df['close'], window=14)
            df['ema50'] = ta.trend.ema_indicator(df['close'], window=50)
            df['ema200'] = ta.trend.ema_indicator(df['close'], window=200)
            df['macd'] = ta.trend.macd(df['close'])
            df['macd_signal'] = ta.trend.macd_signal(df['close'])

            close_price = df['close'].iloc[-1]
            rsi = df['rsi'].iloc[-1]
            macd = df['macd'].iloc[-1]
            macd_signal = df['macd_signal'].iloc[-1]
            ema50 = df['ema50'].iloc[-1]
            ema200 = df['ema200'].iloc[-1]

            # 🔹 Log de precios en Render
            print(f"{symbol}: precio={close_price:.4f}, RSI={rsi:.2f}", flush=True)

            # 🔹 Generar señal simple
            signal = None
            if rsi < 30 and macd > macd_signal and ema50 > ema200:
                signal = "LONG"
            elif rsi > 70 and macd < macd_signal and ema50 < ema200:
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
                print(f"📤 Señal enviada: {symbol} {signal}", flush=True)

                with open(CSV_FILE, mode='a', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([datetime.datetime.now(), symbol, signal, close_price, tp, sl, news if news else ""])

        except Exception as e:
            print(f"⚠️ Error analizando {symbol}: {e}", flush=True)

# 🔹 Heartbeat cada 1 hora
def heartbeat():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"✅ Bot activo - {now}")

# 🔹 Scheduler
schedule.every(15).minutes.do(analyze_market)
schedule.every().hour.do(heartbeat)

# 🔹 Aviso inicial
bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="🚀 Bot de alertas Binance Spot iniciado correctamente...")
print("✅ Bot iniciado. Analiza cada 15 minutos y heartbeat cada 1 hora...", flush=True)

# 🔹 Primer análisis inmediato
analyze_market()

while True:
    schedule.run_pending()
    time.sleep(1)

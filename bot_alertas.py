import os, time, datetime, requests, pandas as pd, numpy as np, ta, csv
from telegram import Bot
import schedule
import feedparser
from textblob import TextBlob

# --- Variables de entorno para Telegram ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")

if not all([TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
    print("❌ ERROR: Variables de entorno no configuradas.")
    exit()

bot = Bot(token=TELEGRAM_TOKEN)

# --- CSV para histórico ---
CSV_FILE = "historico_senales.csv"
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Fecha", "Moneda", "Señal", "Precio Entrada", "TP", "SL", "RSI", "Noticia"])

# --- Lista de 50 monedas Spot ---
symbols = [
    "BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","SOLUSDT","DOGEUSDT","ADAUSDT","TRXUSDT","MATICUSDT","LTCUSDT",
    "DOTUSDT","SHIBUSDT","AVAXUSDT","UNIUSDT","ATOMUSDT","LINKUSDT","XLMUSDT","FILUSDT","ICPUSDT","APTUSDT",
    "ARBUSDT","SANDUSDT","MANAUSDT","APEUSDT","AXSUSDT","NEARUSDT","EOSUSDT","FLOWUSDT","XTZUSDT","THETAUSDT",
    "AAVEUSDT","GRTUSDT","RUNEUSDT","KAVAUSDT","CRVUSDT","FTMUSDT","CHZUSDT","SNXUSDT","LDOUSDT","OPUSDT",
    "COMPUSDT","DYDXUSDT","BLURUSDT","RNDRUSDT","GMTUSDT","1INCHUSDT","OCEANUSDT","SUIUSDT","PYTHUSDT","JTOUSDT"
]

# --- Feeds de noticias ---
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

# --- Últimas señales enviadas para evitar repeticiones ---
last_signals = {}  # { "BTCUSDT_LONG": timestamp }

# --- Función para buscar noticias ---
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

# --- Indicadores técnicos ---
def rsi(series, period=14):
    return ta.momentum.RSIIndicator(series, window=period).rsi()

def ema(series, period):
    return ta.trend.EMAIndicator(series, window=period).ema_indicator()

def atr(df, period=14):
    return ta.volatility.AverageTrueRange(
        df['high'], df['low'], df['close'], window=period
    ).average_true_range()

# --- Obtener datos de Binance Spot ---
def get_klines(symbol, interval="15m", limit=200):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    data = requests.get(url).json()
    if isinstance(data, dict) and data.get("code"):
        print(f"⚠️ Error Binance: {data}")
        return None
    df = pd.DataFrame(data, columns=[
        "timestamp","open","high","low","close","volume",
        "close_time","quote_volume","trades","tb_base","tb_quote","ignore"
    ])
    df = df.astype(float)
    return df[["open","high","low","close","volume"]]

# --- Estrategia de análisis ---
def analyze_market():
    print(f"🔍 Analizando {len(symbols)} pares Spot...")
    candidate_signals = []
    now = time.time()

    for symbol in symbols:
        try:
            df = get_klines(symbol)
            if df is None or len(df) < 50:
                continue

            # Filtrar por volumen
            vol_24h = df['volume'].sum()
            if vol_24h < 1_000_000:
                continue

            # Indicadores
            df['rsi'] = rsi(df['close'])
            df['ema50'] = ema(df['close'], 50)
            df['ema200'] = ema(df['close'], 200)
            df['atr'] = atr(df)

            last = df.iloc[-1]
            rsi_val = last['rsi']
            ema50 = last['ema50']
            ema200 = last['ema200']
            atr_val = last['atr']
            price = last['close']

            signal = None
            score = 0

            # Estrategia filtrada por tendencia
            if rsi_val < 30 and ema50 > ema200:
                signal = "LONG"
                score = 70 - rsi_val  # cuanto más sobrevendido, más score
            elif rsi_val > 70 and ema50 < ema200:
                signal = "SHORT"
                score = rsi_val - 30  # cuanto más sobrecomprado, más score

            if signal:
                # Evitar repetir señal reciente
                key = f"{symbol}_{signal}"
                if key in last_signals and now - last_signals[key] < 3600:
                    continue

                tp = price + (2 * atr_val if signal == "LONG" else -2 * atr_val)
                sl = price - (2 * atr_val if signal == "LONG" else -2 * atr_val)
                candidate_signals.append((score, symbol, signal, price, tp, sl, rsi_val))

        except Exception as e:
            print(f"⚠️ Error analizando {symbol}: {e}")

    # --- Filtrar top 3 señales ---
    candidate_signals.sort(reverse=True, key=lambda x: x[0])
    top_signals = candidate_signals[:3]

    for score, symbol, signal, price, tp, sl, rsi_val in top_signals:
        news = check_news(symbol)
        msg = (
            f"🔔 Señal Detectada\n"
            f"Moneda: {symbol}\n"
            f"Tipo: {signal}\n"
            f"Entrada: {price:.4f}\n"
            f"TP: {tp:.4f}\n"
            f"SL: {sl:.4f}\n"
            f"RSI: {rsi_val:.2f}\n"
        )
        if news:
            msg += f"{news}\n"

        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
        print(f"📤 Señal enviada: {symbol} {signal}")

        last_signals[f"{symbol}_{signal}"] = time.time()

        with open(CSV_FILE, mode='a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.datetime.now(), symbol, signal, price, tp, sl, rsi_val, news if news else ""
            ])

# --- Heartbeat cada 1 hora ---
def heartbeat():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"✅ Bot activo - {now}")

# --- Scheduler ---
schedule.every(15).minutes.do(analyze_market)
schedule.every().hour.do(heartbeat)

# --- Aviso inicial ---
bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="🚀 Bot Spot Binance iniciado correctamente...")

print("✅ Bot Spot iniciado. Analiza cada 15 minutos y heartbeat cada 1 hora...")
while True:
    schedule.run_pending()
    time.sleep(1)

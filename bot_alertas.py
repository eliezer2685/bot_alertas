import os, time, datetime, json, requests, pandas as pd, ta, feedparser, csv
from textblob import TextBlob
from telegram import Bot
from binance.client import Client
import schedule

# === VARIABLES DE ENTORNO ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")

bot = Bot(token=TELEGRAM_TOKEN)

# === LISTA DE MONEDAS ===
ALL_SYMBOLS = [
    "BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","SOLUSDT","DOGEUSDT","ADAUSDT","TRXUSDT","MATICUSDT","LTCUSDT",
    "DOTUSDT","SHIBUSDT","AVAXUSDT","UNIUSDT","ATOMUSDT","LINKUSDT","XLMUSDT","FILUSDT","ICPUSDT","APTUSDT",
    "ARBUSDT","SANDUSDT","MANAUSDT","APEUSDT","AXSUSDT","NEARUSDT","EOSUSDT","FLOWUSDT","XTZUSDT","THETAUSDT",
    "AAVEUSDT","GRTUSDT","RUNEUSDT","KAVAUSDT","CRVUSDT","FTMUSDT","CHZUSDT","SNXUSDT","LDOUSDT","OPUSDT",
    "COMPUSDT","DYDXUSDT","BLURUSDT","RNDRUSDT","GMTUSDT","1INCHUSDT","OCEANUSDT","SUIUSDT","PYTHUSDT","JTOUSDT",
    "PEPEUSDT","WIFUSDT","TIAUSDT","1000SATSUSDT","BOMEUSDT","SEIUSDT","JASMYUSDT","FETUSDT","NOTUSDT","WUSDT"
]

# === ARCHIVO DE TOP10 ===
TOP10_FILE = "last_coins.json"

# === CLIENTE BINANCE ===
binance = Client()

# === FUENTES DE NOTICIAS ===
news_feeds = [
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
    "https://cryptopotato.com/feed/"
]

def check_news(symbol):
    keyword = symbol.replace("USDT", "")
    for feed in news_feeds:
        d = feedparser.parse(feed)
        for entry in d.entries[:5]:
            title = entry.title
            if keyword.lower() in title.lower():
                sentiment = TextBlob(title).sentiment.polarity
                if sentiment > 0.1:
                    return f"🟢 Noticia positiva: \"{title}\"", 10
                elif sentiment < -0.1:
                    return f"🔴 Noticia negativa: \"{title}\"", 10
    return None, 0

def get_klines(symbol, interval, limit=100):
    try:
        klines = binance.get_klines(symbol=symbol, interval=interval, limit=limit)
        df = pd.DataFrame(klines, columns=["timestamp", "o", "h", "l", "c", "v", "close_time", "q", "n", "taker_base", "taker_quote", "ignore"])
        df["c"] = pd.to_numeric(df["c"], errors='coerce')
        df["v"] = pd.to_numeric(df["v"], errors='coerce')
        return df.dropna()
    except:
        return None

def analyze_symbol(symbol):
    df = get_klines(symbol, Client.KLINE_INTERVAL_15MINUTE, limit=100)
    if df is None or df.empty: return None

    score = 0
    last_price = df["c"].iloc[-1]

    rsi = ta.momentum.RSIIndicator(df["c"], window=14).rsi().iloc[-1]
    ema50 = ta.trend.EMAIndicator(df["c"], window=50).ema_indicator().iloc[-1]
    ema200 = ta.trend.EMAIndicator(df["c"], window=200).ema_indicator().iloc[-1]
    macd_line = ta.trend.MACD(df["c"]).macd().iloc[-1]
    macd_signal = ta.trend.MACD(df["c"]).macd_signal().iloc[-1]
    vol_ma = df["v"].rolling(window=20).mean().iloc[-1]
    vol_now = df["v"].iloc[-1]

    # Estrategia 1: RSI, MACD, EMA
    if (rsi < 30 and macd_line > macd_signal and ema50 > ema200) or \
       (rsi > 70 and macd_line < macd_signal and ema50 < ema200):
        score += 35

    # Estrategia 2: Volumen
    if vol_now > vol_ma * 1.5:
        score += 25

    # Estrategia 3: EMA cruzadas sin RSI
    if (ema50 > ema200 and macd_line > macd_signal) or \
       (ema50 < ema200 and macd_line < macd_signal):
        score += 20

    # Estrategia 4: Noticias
    noticia, extra = check_news(symbol)
    score += extra

    tipo = "LONG" if ema50 > ema200 else "SHORT"
    tp = round(last_price * (1.02 if tipo == "LONG" else 0.98), 6)
    sl = round(last_price * (0.98 if tipo == "LONG" else 1.02), 6)

    return {
        "symbol": symbol,
        "tipo": tipo,
        "precio": last_price,
        "tp": tp,
        "sl": sl,
        "noticia": noticia,
        "prob": score
    } if score >= 70 else None

def select_top10():
    print("🔍 Generando Top10...")
    señales = []
    for sym in ALL_SYMBOLS:
        res = analyze_symbol(sym)
        if res:
            señales.append(res)
    señales.sort(key=lambda x: x["prob"], reverse=True)
    top10 = [r["symbol"] for r in señales[:10]]
    with open(TOP10_FILE, 'w') as f:
        json.dump(top10, f)
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"✅ Top10 generado: {top10}")

# === ALERTAS ===
alertadas_hoy = set()

def analyze_intraday():
    if not os.path.exists(TOP10_FILE):
        select_top10()
        return
    with open(TOP10_FILE) as f:
        top10 = json.load(f)
    for sym in top10:
        if sym in alertadas_hoy:
            continue
        res = analyze_symbol(sym)
        if res:
            msg = (
                f"📢 Señal Confirmada
"
                f"Moneda: {res['symbol']}
"
                f"Tipo: {res['tipo']}
"
                f"Entrada: {res['precio']}
"
                f"TP: {res['tp']}
"
                f"SL: {res['sl']}
"
                f"Probabilidad: {res['prob']}%
"
            )
            if res['noticia']:
                msg += f"{res['noticia']}\n"
            bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
            alertadas_hoy.add(sym)

def resumen():
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="📊 Bot activo. Analizando top10 cada 15 min. Resumen cada 1 hora.")

# === VERIFICAR SI FALTA TOP10 AL INICIAR ===
def check_or_generate_top10():
    hoy = datetime.date.today().isoformat()
    if not os.path.exists(TOP10_FILE):
        print("🔁 No hay top10, generando...")
        select_top10()
    else:
        with open(TOP10_FILE) as f:
            monedas = json.load(f)
        if not monedas:
            print("🔁 Archivo top10 vacío, generando...")
            select_top10()

# === PROGRAMACIÓN ===
schedule.every().day.at("06:00").do(select_top10)
schedule.every().hour.do(check_or_generate_top10)
schedule.every(15).minutes.do(analyze_intraday)
schedule.every().hour.at(":00").do(resumen)

# === INICIO ===
check_or_generate_top10()
bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="🚀 Bot iniciado y funcionando correctamente")
print("✅ Bot iniciado...")

while True:
    schedule.run_pending()
    time.sleep(1)

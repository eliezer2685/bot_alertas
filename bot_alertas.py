import os, time, datetime, requests, csv
import pandas as pd
import numpy as np
import schedule
import feedparser
from textblob import TextBlob
from binance.client import Client
from telegram import Bot

# ================== CONFIGURACIÓN ==================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    print("❌ ERROR: Variables de entorno no configuradas.")
    exit()

bot = Bot(token=TELEGRAM_TOKEN)

# Cliente Binance solo para Spot (no necesitamos API Key para precios)
client = Client("", "")

# Lista de 60 monedas Spot populares
symbols = [
    "BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","SOLUSDT","DOGEUSDT","ADAUSDT","TRXUSDT","MATICUSDT","LTCUSDT",
    "DOTUSDT","SHIBUSDT","AVAXUSDT","UNIUSDT","ATOMUSDT","LINKUSDT","XLMUSDT","FILUSDT","ICPUSDT","APTUSDT",
    "ARBUSDT","SANDUSDT","MANAUSDT","APEUSDT","AXSUSDT","NEARUSDT","EOSUSDT","FLOWUSDT","XTZUSDT","THETAUSDT",
    "AAVEUSDT","GRTUSDT","RUNEUSDT","KAVAUSDT","CRVUSDT","FTMUSDT","CHZUSDT","SNXUSDT","LDOUSDT","OPUSDT",
    "COMPUSDT","DYDXUSDT","BLURUSDT","RNDRUSDT","GMTUSDT","1INCHUSDT","OCEANUSDT","SUIUSDT","PYTHUSDT","JTOUSDT",
    "PEPEUSDT","SEIUSDT","WLDUSDT","BONKUSDT","TIAUSDT","BEAMXUSDT","STRKUSDT","STXUSDT","ARKMUSDT","ORDIUSDT"
]

TOP_MONEDAS_DIARIAS = 10
COOLDOWN_ALERTA = 3 * 3600  # 3 horas
INTERVALO_VELAS = "15m"
VELAS_LIMIT = 200  # ≈ 2 días de histórico
TP_PORC = 0.02
SL_PORC = 0.02

# RSS noticias cripto
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

# Variables en memoria
top_monedas = []
ultima_alerta = {}
trades_activos = {}

# ================== FUNCIONES ==================
def obtener_velas(symbol, interval=INTERVALO_VELAS, limit=VELAS_LIMIT):
    """Descarga velas de Binance y retorna DataFrame"""
    try:
        klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
        df = pd.DataFrame(klines, columns=[
            "timestamp","open","high","low","close","volume","close_time","qav","num_trades","taker_base_vol","taker_quote_vol","ignore"
        ])
        df["close"] = df["close"].astype(float)
        df["volume"] = df["volume"].astype(float)
        return df
    except:
        return None

def check_news(symbol):
    """Analiza noticias y devuelve sentimiento"""
    keyword = symbol.replace("USDT", "")
    for feed in news_feeds:
        d = feedparser.parse(feed)
        for entry in d.entries[:5]:
            title = entry.title
            if keyword.lower() in title.lower():
                sentiment = TextBlob(title).sentiment.polarity
                if sentiment > 0.1:
                    return f"🟢 Positiva: \"{title}\""
                elif sentiment < -0.1:
                    return f"🔴 Negativa: \"{title}\""
    return None

def calcular_probabilidad(df):
    """Evalúa las 4 estrategias y devuelve dirección (LONG/SHORT), probabilidad y estrategias activas"""
    estrategias = []
    prob = 0
    direccion = None

    # ===== Estrategia 1: MACD + EMA + RSI =====
    df["EMA50"] = df["close"].ewm(span=50).mean()
    df["EMA200"] = df["close"].ewm(span=200).mean()
    df["RSI"] = calcular_RSI(df["close"])
    macd_line, signal_line = calcular_MACD(df["close"])

    close = df["close"].iloc[-1]
    rsi = df["RSI"].iloc[-1]
    macd_val = macd_line.iloc[-1]
    signal_val = signal_line.iloc[-1]
    ema50 = df["EMA50"].iloc[-1]
    ema200 = df["EMA200"].iloc[-1]

    if rsi < 30 and macd_val > signal_val and ema50 > ema200:
        prob += 30
        estrategias.append("MACD+EMA+RSI")
        direccion = "LONG"
    elif rsi > 70 and macd_val < signal_val and ema50 < ema200:
        prob += 30
        estrategias.append("MACD+EMA+RSI")
        direccion = "SHORT"

    # ===== Estrategia 2: Volumen / Tendencia =====
    vol_prom = df["volume"].iloc[-20:].mean()
    vol_ult = df["volume"].iloc[-1]
    if vol_ult > 1.5 * vol_prom:
        prob += 20
        estrategias.append("Volumen")
        if direccion is None:
            direccion = "LONG" if df["close"].iloc[-1] > df["close"].iloc[-2] else "SHORT"

    # ===== Estrategia 3: Noticias =====
    # Evaluamos afuera en la alerta final

    # ===== Estrategia 4: Confirmación multi-indicadores =====
    if direccion and (
        (direccion=="LONG" and close>ema50 and macd_val>signal_val) or
        (direccion=="SHORT" and close<ema50 and macd_val<signal_val)
    ):
        prob += 25
        estrategias.append("MultiConfirmación")

    return direccion, prob, estrategias

def calcular_RSI(series, period=14):
    delta = series.diff()
    gain = delta.where(delta>0, 0)
    loss = -delta.where(delta<0, 0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain/avg_loss
    return 100 - (100/(1+rs))

def calcular_MACD(series, fast=12, slow=26, signal=9):
    exp1 = series.ewm(span=fast, adjust=False).mean()
    exp2 = series.ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    return macd, signal_line

def enviar_alerta(symbol, direccion, prob, price, estrategias, news):
    tp = price * (1+TP_PORC if direccion=="LONG" else 1-TP_PORC)
    sl = price * (1-SL_PORC if direccion=="LONG" else 1+SL_PORC)
    msg = (
        f"🔔 Señal {direccion}\n"
        f"Moneda: {symbol}\n"
        f"Probabilidad: {prob}%\n"
        f"Precio entrada: {price:.4f}\n"
        f"TP: {tp:.4f} | SL: {sl:.4f}\n"
        f"Estrategias: {', '.join(estrategias)}\n"
    )
    if news:
        msg += f"Noticias: {news}\n"

    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
    ultima_alerta[symbol] = time.time()
    trades_activos[symbol] = {"direccion": direccion, "entrada": price, "tp": tp, "sl": sl}

def seleccionar_top_monedas():
    global top_monedas
    resultados = []
    for sym in symbols:
        df = obtener_velas(sym)
        if df is None: continue
        direccion, prob, estrategias = calcular_probabilidad(df)
        resultados.append((sym, prob))
    resultados.sort(key=lambda x:x[1], reverse=True)
    top_monedas = [r[0] for r in resultados[:TOP_MONEDAS_DIARIAS]]
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"🌅 Top {TOP_MONEDAS_DIARIAS} monedas de hoy: {', '.join(top_monedas)}")

def analizar_monedas():
    ahora = time.time()
    for sym in top_monedas:
        df = obtener_velas(sym)
        if df is None: continue
        price = df["close"].iloc[-1]
        direccion, prob, estrategias = calcular_probabilidad(df)
        news = check_news(sym)
        if news: 
            prob += 25
            estrategias.append("Noticias")

        if prob >= 70 and (sym not in ultima_alerta or ahora-ultima_alerta[sym]>COOLDOWN_ALERTA):
            enviar_alerta(sym, direccion, prob, price, estrategias, news)

def resumen_horario():
    msg = f"⏰ Resumen {datetime.datetime.now().strftime('%H:%M')}\n"
    msg += f"Monedas analizadas: {len(top_monedas)}\n"
    msg += f"Trades activos: {len(trades_activos)}\n"
    for sym, trade in trades_activos.items():
        precio_actual = obtener_velas(sym)["close"].iloc[-1]
        msg += f"- {sym} {trade['direccion']} | Entrada {trade['entrada']:.4f} | Actual {precio_actual:.4f}\n"
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)

# ================== SCHEDULER ==================
schedule.every().day.at("06:00").do(seleccionar_top_monedas)
schedule.every(15).minutes.do(analizar_monedas)
schedule.every().hour.do(resumen_horario)

bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="🚀 Bot de alertas iniciado correctamente.")

print("✅ Bot iniciado. Analiza top monedas cada 15 min y envía resúmenes cada hora.")

while True:
    schedule.run_pending()
    time.sleep(1)

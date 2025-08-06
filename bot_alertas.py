import os
import time
import json
import datetime
import pandas as pd
import requests
import feedparser
import schedule
from textblob import TextBlob
from binance.client import Client
import ta
from telegram import Bot

# ==============================
# Configuración
# ==============================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")

bot = Bot(token=TELEGRAM_TOKEN)

# Monedas a analizar inicialmente (spot)
ALL_SYMBOLS = [
    "BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","SOLUSDT","DOGEUSDT","ADAUSDT","TRXUSDT","MATICUSDT","LTCUSDT",
    "DOTUSDT","SHIBUSDT","AVAXUSDT","UNIUSDT","ATOMUSDT","LINKUSDT","XLMUSDT","FILUSDT","ICPUSDT","APTUSDT",
    "ARBUSDT","SANDUSDT","MANAUSDT","APEUSDT","AXSUSDT","NEARUSDT","EOSUSDT","FLOWUSDT","XTZUSDT","THETAUSDT",
    "AAVEUSDT","GRTUSDT","RUNEUSDT","KAVAUSDT","CRVUSDT","FTMUSDT","CHZUSDT","SNXUSDT","LDOUSDT","OPUSDT",
    "COMPUSDT","DYDXUSDT","BLURUSDT","RNDRUSDT","GMTUSDT","1INCHUSDT","OCEANUSDT","SUIUSDT","PYTHUSDT","JTOUSDT",
    "SEIUSDT","TIAUSDT","BONKUSDT","STXUSDT","FTTUSDT","WOOUSDT","BANDUSDT","KSMUSDT","ZECUSDT","ROSEUSDT"
]

TOP10_FILE = "last_coins.json"
HISTORICO_FILE = "historico_senales.csv"

# Binance client solo para spot
client = Client()

# ==============================
# Funciones de análisis
# ==============================

def get_historical(symbol, interval='15m', lookback='200'):
    """Descarga velas de Binance para calcular indicadores"""
    klines = client.get_klines(symbol=symbol, interval=interval, limit=int(lookback))
    df = pd.DataFrame(klines, columns=[
        'timestamp','open','high','low','close','volume',
        'close_time','quote_av','trades','tb_base_av','tb_quote_av','ignore'
    ])
    df['close'] = pd.to_numeric(df['close'])
    df['volume'] = pd.to_numeric(df['volume'])
    return df

def check_news(symbol):
    """Analiza últimas noticias y devuelve sentimiento"""
    keyword = symbol.replace("USDT", "")
    feeds = [
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://cointelegraph.com/rss",
        "https://news.bitcoin.com/feed/"
    ]
    for feed in feeds:
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

def analyze_symbol(symbol):
    """Calcula indicadores y devuelve señal si aplica"""
    try:
        df = get_historical(symbol)
        if df.empty or len(df) < 50:
            return None

        # Indicadores
        df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
        macd = ta.trend.MACD(df['close'])
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        df['ema50'] = ta.trend.EMAIndicator(df['close'], window=50).ema_indicator()
        df['ema200'] = ta.trend.EMAIndicator(df['close'], window=200).ema_indicator()
        df['vol_ma20'] = df['volume'].rolling(20).mean()

        last = df.iloc[-1]
        price = last['close']
        rsi = last['rsi']
        macd_val = last['macd']
        macd_signal = last['macd_signal']
        ema50 = last['ema50']
        ema200 = last['ema200']
        vol = last['volume']
        vol_ma = last['vol_ma20']

        # Estrategias
        strat1 = (rsi < 30 and macd_val > macd_signal and ema50 > ema200) or \
                 (rsi > 70 and macd_val < macd_signal and ema50 < ema200)
        strat2 = vol > vol_ma * 1.5
        strat3 = check_news(symbol) is not None
        strat4 = (ema50 > ema200 and macd_val > macd_signal) or \
                 (ema50 < ema200 and macd_val < macd_signal)

        active_strats = sum([strat1, strat2, strat3, strat4])
        prob = active_strats / 4 * 100

        if prob >= 70:
            signal = "LONG" if macd_val > macd_signal else "SHORT"
            tp = round(price * (1.02 if signal == "LONG" else 0.98), 6)
            sl = round(price * (0.98 if signal == "LONG" else 1.02), 6)
            return {
                "symbol": symbol,
                "signal": signal,
                "price": price,
                "tp": tp,
                "sl": sl,
                "prob": prob,
                "news": check_news(symbol)
            }
        return None
    except Exception as e:
        print(f"⚠️ Error analizando {symbol}: {e}")
        return None

# ==============================
# Selección diaria
# ==============================

def select_top10():
    print("🔹 Generando lista top10...")
    signals = []
    for sym in ALL_SYMBOLS:
        res = analyze_symbol(sym)
        if res:
            signals.append(res)
    top = sorted(signals, key=lambda x: x['prob'], reverse=True)[:10]
    with open(TOP10_FILE, 'w') as f:
        json.dump([t['symbol'] for t in top], f)
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"✅ Top10 generado: {[t['symbol'] for t in top]}")

# ==============================
# Análisis intradía
# ==============================

def analyze_intraday():
    if not os.path.exists(TOP10_FILE):
        select_top10()

    with open(TOP10_FILE) as f:
        top10 = json.load(f)

    alerts = []
    for sym in top10:
        res = analyze_symbol(sym)
        if res:
            msg = (
                f"🔔 Señal Detectada {res['signal']}\n"
                f"Moneda: {res['symbol']}\n"
                f"Probabilidad: {res['prob']:.0f}%\n"
                f"Precio Entrada: {res['price']}\n"
                f"TP: {res['tp']}\nSL: {res['sl']}\n"
            )
            if res['news']:
                msg += f"{res['news']}\n"
            bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
            alerts.append(res['symbol'])
    print(f"📊 Analizado intradía, alertas: {alerts}")

# ==============================
# Scheduler
# ==============================

schedule.every().day.at("06:00").do(select_top10)
schedule.every(1).hours.do(lambda: select_top10() if not os.path.exists(TOP10_FILE) else None)
schedule.every(15).minutes.do(analyze_intraday)

bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="🚀 Bot de alertas iniciado correctamente...")
print("✅ Bot iniciado")

while True:
    schedule.run_pending()
    time.sleep(1)

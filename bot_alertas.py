import pandas as pd
import numpy as np
import requests
import time
import schedule
from datetime import datetime, timedelta
from binance.client import Client
from binance.exceptions import BinanceAPIException
from textblob import TextBlob
import feedparser

# ===== CONFIGURACIÓN BOT =====
SYMBOLS = ["BTCUSDT","ETHUSDT","BNBUSDT","ADAUSDT","SOLUSDT","XRPUSDT","DOGEUSDT",
           "AVAXUSDT","DOTUSDT","MATICUSDT","SHIBUSDT","LTCUSDT","UNIUSDT","LINKUSDT",
           "XLMUSDT","ATOMUSDT","FILUSDT","SANDUSDT","AAVEUSDT","GALAUSDT",
           "IMXUSDT","RNDRUSDT","FTMUSDT","OPUSDT","APTUSDT","NEARUSDT",
           "FLOWUSDT","CFXUSDT","BLURUSDT","INJUSDT","SEIUSDT","PYTHUSDT",
           "SUIUSDT","MINAUSDT","DYMUSDT","ENAUSDT","TIAUSDT","BEAMXUSDT",
           "JTOUSDT","OCEANUSDT","GMTUSDT","1INCHUSDT","ICPUSDT","PEPEUSDT",
           "WLDUSDT","BONKUSDT","ARKMUSDT","NOTUSDT","ENAUSDT","TNSRUSDT",
           "ALTUSDT","ETHFIUSDT","PORTALUSDT","REZUSDT","ZKUSDT","ZROUSDT",
           "TAOUSDT","JASMYUSDT","XAIUSDT","ONDOUSDT","METISUSDT"][:60]  # 60 monedas

TIMEFRAME = '15m'   # Temporalidad
CANDLE_LIMIT = 200   # Velas para indicadores
ALERT_INTERVAL = 30  # minutos entre alertas por símbolo
SUMMARY_INTERVAL = 60 # resumen cada 60 minutos

# ===== VARIABLES DE ESTADO =====
client = Client()  # Para SPOT no hace falta API Key
last_alerts = {}
last_alert_time = {}
summary_buffer = []
persist_signals = {}

# ===== FUNCIONES =====

def fetch_ohlcv(symbol, interval=TIMEFRAME, limit=CANDLE_LIMIT):
    klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    df = pd.DataFrame(klines, columns=['time','open','high','low','close','volume','close_time',
                                       'qav','num_trades','taker_base','taker_quote','ignore'])
    df[['open','high','low','close','volume']] = df[['open','high','low','close','volume']].astype(float)
    return df

def calculate_indicators(df):
    # EMA
    df['EMA20'] = df['close'].ewm(span=20).mean()
    df['EMA50'] = df['close'].ewm(span=50).mean()
    # RSI
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))
    # MACD
    df['EMA12'] = df['close'].ewm(span=12).mean()
    df['EMA26'] = df['close'].ewm(span=26).mean()
    df['MACD'] = df['EMA12'] - df['EMA26']
    df['Signal'] = df['MACD'].ewm(span=9).mean()
    # ATR
    df["H-L"] = df["high"] - df["low"]
    df["H-C"] = abs(df["high"] - df["close"].shift())
    df["L-C"] = abs(df["low"] - df["close"].shift())
    df["TR"] = df[["H-L","H-C","L-C"]].max(axis=1)
    df["ATR"] = df["TR"].rolling(14).mean()
    return df

def analyze_sentiment():
    feed = feedparser.parse("https://news.google.com/rss/search?q=cryptocurrency")
    scores = []
    for entry in feed.entries[:5]:
        analysis = TextBlob(entry.title)
        scores.append(analysis.sentiment.polarity)
    avg_score = np.mean(scores) if scores else 0
    if avg_score > 0.1:
        return "positivo", 5
    elif avg_score < -0.1:
        return "negativo", -5
    else:
        return "neutral", 0

def generate_signal(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    ema_cross = last.EMA20 > last.EMA50 and prev.EMA20 <= prev.EMA50
    macd_cross = last.MACD > last.Signal and prev.MACD <= prev.Signal
    rsi_signal = last.RSI < 30 or last.RSI > 70
    volume_signal = last.volume > df['volume'].rolling(20).mean().iloc[-1]*1.5

    signals = {
        "long": ema_cross and macd_cross and last.RSI < 70,
        "short": (last.EMA20 < last.EMA50 and last.MACD < last.Signal and last.RSI > 30),
        "ema_macd": ema_cross and macd_cross,
        "rsi": rsi_signal,
        "volumen": volume_signal
    }
    return signals

def send_alert(symbol, direction, price, atr, confidence, sentiment):
    tp = price + (atr*2 if direction=="LONG" else -atr*2)
    sl = price - (atr*1.5 if direction=="LONG" else -atr*1.5)
    msg = (f"🚨 Señal {direction} en {symbol}\n"
           f"Precio: {price:.4f}\n"
           f"TP: {tp:.4f} | SL: {sl:.4f}\n"
           f"Confianza: {confidence}% | Sentimiento: {sentiment}\n")
    print(msg)
    summary_buffer.append(msg)

def analyze_symbol(symbol):
    global last_alerts, persist_signals
    df = fetch_ohlcv(symbol)
    df = calculate_indicators(df)
    signals = generate_signal(df)
    last = df.iloc[-1]
    atr = df["ATR"].iloc[-1]
    price = last.close

    sentiment, sentiment_score = analyze_sentiment()

    # Estrategias combinadas
    active_strategies = sum([signals["ema_macd"], signals["rsi"], signals["volumen"]])
    direction = "LONG" if signals["long"] else "SHORT" if signals["short"] else None

    # Persistencia 2 velas
    prev_signal = persist_signals.get(symbol)
    current_signal = direction
    persist_signals[symbol] = current_signal

    if prev_signal == current_signal and current_signal is not None:
        confidence = 80 if active_strategies >= 2 else 0
        confidence += sentiment_score
        last_time = last_alert_time.get(symbol, datetime.min)
        if confidence >= 75 and datetime.now()-last_time > timedelta(minutes=ALERT_INTERVAL):
            send_alert(symbol, current_signal, price, atr, confidence, sentiment)
            last_alert_time[symbol] = datetime.now()

def analyze_all():
    for symbol in SYMBOLS:
        try:
            analyze_symbol(symbol)
        except BinanceAPIException as e:
            print(f"Error Binance {symbol}: {e}")
        except Exception as e:
            print(f"Error {symbol}: {e}")

def send_summary():
    if summary_buffer:
        print("\n=== RESUMEN ÚLTIMA HORA ===")
        for msg in summary_buffer:
            print(msg)
        print("============================\n")
        summary_buffer.clear()

# Schedulers
schedule.every(15).minutes.do(analyze_all)
schedule.every(SUMMARY_INTERVAL).minutes.do(send_summary)

print("Bot de alertas iniciado ✅")
while True:
    schedule.run_pending()
    time.sleep(1)

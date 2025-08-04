import os
import time
import pandas as pd
import numpy as np
import requests
import schedule
import datetime
from binance.client import Client
from binance.enums import *
from telegram import Bot
from textblob import TextBlob

# ==============================
# CONFIGURACIONES
# ==============================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")

BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")

bot = Bot(token=TELEGRAM_TOKEN)
client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)

# Apalancamiento y riesgo
LEVERAGE = 5
POSITION_SIZE_PERCENT = 0.3  # 30% dinámico

# Timeframe y configuración de velas
TIMEFRAME = '15m'
LIMIT_CANDLES = 500  # más velas para indicadores robustos

# Lista inicial de pares de futuros USDT
SYMBOLS = [
    'BTCUSDT','ETHUSDT','BNBUSDT','SOLUSDT','XRPUSDT','ADAUSDT','DOGEUSDT','MATICUSDT','DOTUSDT','LTCUSDT',
    'AVAXUSDT','TRXUSDT','UNIUSDT','LINKUSDT','ATOMUSDT','FILUSDT','ETCUSDT','ICPUSDT','APTUSDT','NEARUSDT',
    'ARBUSDT','OPUSDT','SUIUSDT','RNDRUSDT','LDOUSDT','STXUSDT','IMXUSDT','INJUSDT','WOOUSDT','FLOWUSDT',
    'KAVAUSDT','GALAUSDT','GMTUSDT','OCEANUSDT','1INCHUSDT','PYTHUSDT','JTOUSDT','APEUSDT','BLURUSDT','MINAUSDT',
    'FTMUSDT','DYDXUSDT','RUNEUSDT','XLMUSDT','C98USDT','WAVESUSDT','ROSEUSDT','CHZUSDT','ENJUSDT','BANDUSDT','SANDUSDT'
]

# Evitar alertas duplicadas por 3 horas
last_alert = {}

# ==============================
# FUNCIONES AUXILIARES
# ==============================

def send_telegram(msg: str):
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
    except Exception as e:
        print("Error enviando Telegram:", e)

def get_klines(symbol):
    try:
        data = client.futures_klines(symbol=symbol, interval=TIMEFRAME, limit=LIMIT_CANDLES)
        df = pd.DataFrame(data, columns=[
            'time','o','h','l','c','v','ct','qv','n','tbb','tbq','ig'
        ])
        df['c'] = df['c'].astype(float)
        df['h'] = df['h'].astype(float)
        df['l'] = df['l'].astype(float)
        df['v'] = df['v'].astype(float)
        return df
    except Exception as e:
        print(f"Error obteniendo velas {symbol}: {e}")
        return None

def calculate_indicators(df):
    # RSI
    delta = df['c'].diff()
    gain = delta.where(delta>0,0)
    loss = -delta.where(delta<0,0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100/(1+rs))

    # EMA
    df['EMA50'] = df['c'].ewm(span=50).mean()
    df['EMA200'] = df['c'].ewm(span=200).mean()

    # MACD
    ema12 = df['c'].ewm(span=12).mean()
    ema26 = df['c'].ewm(span=26).mean()
    df['MACD'] = ema12 - ema26
    df['Signal'] = df['MACD'].ewm(span=9).mean()

    # Volumen estrategia simple
    df['Vol_Avg'] = df['v'].rolling(20).mean()

    return df

def get_news_sentiment():
    try:
        url = "https://news.google.com/rss/search?q=crypto+OR+bitcoin&hl=en-US&gl=US&ceid=US:en"
        import feedparser
        feed = feedparser.parse(url)
        top_titles = [entry.title for entry in feed.entries[:5]]
        sentiment_scores = [TextBlob(t).sentiment.polarity for t in top_titles]
        avg_sentiment = np.mean(sentiment_scores) if sentiment_scores else 0
        return avg_sentiment, top_titles
    except:
        return 0, []

def strategy_analysis(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    long_signals = 0
    short_signals = 0

    # Estrategia 1: RSI + EMA + MACD
    if last['RSI']<30 and last['EMA50']>last['EMA200'] and last['MACD']>last['Signal']:
        long_signals+=1
    if last['RSI']>70 and last['EMA50']<last['EMA200'] and last['MACD']<last['Signal']:
        short_signals+=1

    # Estrategia 2: Volumen
    if last['v']>last['Vol_Avg']*2:
        if last['c']>prev['c']: long_signals+=1
        else: short_signals+=1

    # Estrategia 3: Cruce EMA50/200
    if prev['EMA50']<prev['EMA200'] and last['EMA50']>last['EMA200']:
        long_signals+=1
    if prev['EMA50']>prev['EMA200'] and last['EMA50']<last['EMA200']:
        short_signals+=1

    # Estrategia 4: MACD cruce
    if prev['MACD']<prev['Signal'] and last['MACD']>last['Signal']:
        long_signals+=1
    if prev['MACD']>prev['Signal'] and last['MACD']<last['Signal']:
        short_signals+=1

    prob_long = long_signals/4*100
    prob_short = short_signals/4*100

    return prob_long, prob_short, last['c']

def check_balance_and_open(symbol, side, price):
    try:
        balance = float(client.futures_account_balance()[1]['balance'])
        qty = round((balance*POSITION_SIZE_PERCENT*LEVERAGE)/price, 3)

        if qty<=0:
            send_telegram(f"Saldo insuficiente para abrir {side} en {symbol}")
            return False

        client.futures_change_leverage(symbol=symbol, leverage=LEVERAGE)
        client.futures_create_order(
            symbol=symbol,
            side=SIDE_BUY if side=="LONG" else SIDE_SELL,
            type=FUTURE_ORDER_TYPE_MARKET,
            quantity=qty
        )
        send_telegram(f"✅ Posición {side} abierta en {symbol} ({qty} contratos) @ {price}")
        return True
    except Exception as e:
        send_telegram(f"❌ Error abriendo {side} en {symbol}: {e}")
        return False

def analyze_market():
    global last_alert
    sentiment, news = get_news_sentiment()
    for symbol in SYMBOLS:
        df = get_klines(symbol)
        if df is None: continue
        df = calculate_indicators(df)
        prob_long, prob_short, price = strategy_analysis(df)

        now = datetime.datetime.now()
        if prob_long>=90 or prob_short>=90:
            last_time = last_alert.get(symbol, None)
            if not last_time or (now-last_time).total_seconds()>10800:  # 3h
                side = "LONG" if prob_long>prob_short else "SHORT"
                opened = check_balance_and_open(symbol, side, price)
                send_telegram(
                    f"🚨 ALERTA {side} {symbol}\n"
                    f"Precio: {price}\n"
                    f"Confianza: {max(prob_long,prob_short):.2f}%\n"
                    f"Sentimiento noticias: {sentiment:.2f}\n"
                    f"Top news: {news[:2]}"
                )
                last_alert[symbol] = now

def hourly_summary():
    sentiment, news = get_news_sentiment()
    balance = client.futures_account_balance()
    send_telegram(f"📊 Resumen:\n"
                  f"Balance: {balance[1]['balance']} USDT\n"
                  f"Sentimiento: {sentiment:.2f}\n"
                  f"Noticias: {news[:3]}")

# ==============================
# INICIO DEL BOT
# ==============================
send_telegram("🤖 Bot de Trading iniciado correctamente.")
schedule.every(30).minutes.do(analyze_market)
schedule.every(1).hours.do(hourly_summary)

while True:
    schedule.run_pending()
    time.sleep(5)

import os
import time
import pandas as pd
import numpy as np
import requests
import feedparser
import schedule
from datetime import datetime, timedelta
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD
from binance.client import Client
from binance.enums import *
from telegram import Bot

# ================== CONFIG ==================
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")

client = Client(API_KEY, API_SECRET)
bot = Bot(token=TELEGRAM_TOKEN)

INTERVAL = '15m'
LIMIT = 120  # velas (30 horas)
LEVERAGE = 5
POSITION_SIZE_PCT = 0.30
DUPLICATE_BLOCK_HOURS = 3
NEWS_FEED = "https://cryptopanic.com/rss/"

# Trailing
TRAILING_START = 0.01  # 1% profit para activar trailing
TRAILING_STEP = 0.003  # 0.3% de distancia

# Monedas a analizar (futuros top 60)
SYMBOLS = [
    'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'XRPUSDT', 'ADAUSDT', 'DOGEUSDT', 'SOLUSDT', 'DOTUSDT', 'LTCUSDT', 'MATICUSDT',
    'AVAXUSDT', 'SHIBUSDT', 'TRXUSDT', 'UNIUSDT', 'XLMUSDT', 'ATOMUSDT', 'ICPUSDT', 'FILUSDT', 'SANDUSDT', 'EGLDUSDT',
    'APEUSDT', 'GALAUSDT', 'AAVEUSDT', 'EOSUSDT', 'FLOWUSDT', 'KSMUSDT', 'AXSUSDT', 'NEARUSDT', 'CHZUSDT', 'THETAUSDT',
    'RUNEUSDT', 'GMTUSDT', 'SNXUSDT', 'CRVUSDT', 'ENJUSDT', 'DYDXUSDT', 'RNDRUSDT', 'OCEANUSDT', 'SUIUSDT', 'JTOUSDT',
    'PYTHUSDT', 'ARUSDT', 'STXUSDT', 'INJUSDT', 'CFXUSDT', 'OPUSDT', 'LDOUSDT', 'IMXUSDT', 'MINAUSDT', 'BLURUSDT',
    '1INCHUSDT', 'WOOUSDT', 'PEPEUSDT', 'FETUSDT', 'MAGICUSDT', 'TWTUSDT', 'GMXUSDT', 'HOOKUSDT', 'ROSEUSDT', 'COMPUSDT'
]

# Estado
last_alerts = {}
open_positions = {}  # {symbol: {"side":..., "entry":..., "qty":..., "sl":..., "tp":..., "trailing_active":False}}

# ================== FUNCIONES ==================

def get_klines(symbol):
    """Descarga velas para indicadores"""
    try:
        klines = client.futures_klines(symbol=symbol, interval=INTERVAL, limit=LIMIT)
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_av', 'trades', 'tb_base_av', 'tb_quote_av', 'ignore'
        ])
        df['close'] = df['close'].astype(float)
        return df
    except Exception as e:
        print(f"[ERROR] No se pudo descargar velas {symbol}: {e}")
        return None

def analyze_symbol(symbol):
    """Analiza la moneda y devuelve señal"""
    df = get_klines(symbol)
    if df is None or len(df) < 50:
        return None

    close = df['close']
    rsi = RSIIndicator(close=close, window=14).rsi()
    ema20 = EMAIndicator(close=close, window=20).ema_indicator()
    ema50 = EMAIndicator(close=close, window=50).ema_indicator()
    macd = MACD(close=close, window_slow=26, window_fast=12, window_sign=9)

    last_rsi = rsi.iloc[-1]
    last_ema20 = ema20.iloc[-1]
    last_ema50 = ema50.iloc[-1]
    last_macd = macd.macd().iloc[-1]
    last_signal = macd.macd_signal().iloc[-1]
    price = close.iloc[-1]

    signal = None
    confidence = 0

    if last_rsi < 35 and last_ema20 > last_ema50 and last_macd > last_signal:
        signal = "LONG"
        confidence = 90
    elif last_rsi > 65 and last_ema20 < last_ema50 and last_macd < last_signal:
        signal = "SHORT"
        confidence = 90
    elif (last_rsi < 45 and last_macd > last_signal) or (last_rsi > 55 and last_macd < last_signal):
        signal = "LONG" if last_rsi < 45 else "SHORT"
        confidence = 70

    if not signal:
        return None

    tp = round(price * (1.02 if signal == "LONG" else 0.98), 4)
    sl = round(price * (0.98 if signal == "LONG" else 1.02), 4)

    return {"symbol": symbol, "signal": signal, "price": price, "confidence": confidence, "tp": tp, "sl": sl}

def check_news_sentiment():
    feed = feedparser.parse(NEWS_FEED)
    score = 50
    if not feed.entries:
        return score

    positive = ["bullish", "rise", "up", "surge", "buy"]
    negative = ["bearish", "fall", "down", "drop", "sell"]

    count_pos, count_neg = 0, 0
    for entry in feed.entries[:20]:
        title = entry.title.lower()
        if any(word in title for word in positive):
            count_pos += 1
        if any(word in title for word in negative):
            count_neg += 1

    if count_pos + count_neg > 0:
        score = int((count_pos / (count_pos + count_neg)) * 100)
    return score

def can_alert(symbol):
    last = last_alerts.get(symbol)
    if not last:
        return True
    return datetime.now() - last > timedelta(hours=DUPLICATE_BLOCK_HOURS)

def send_telegram(msg):
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
    except Exception as e:
        print(f"[ERROR] Telegram: {e}")

def place_futures_order(symbol, signal, price, sl, tp):
    try:
        balance = float(client.futures_account_balance()[1]['balance'])
        qty_usdt = balance * POSITION_SIZE_PCT
        qty = round(qty_usdt / price, 3)

        client.futures_change_leverage(symbol=symbol, leverage=LEVERAGE)

        side = SIDE_BUY if signal == "LONG" else SIDE_SELL
        client.futures_create_order(
            symbol=symbol,
            type=ORDER_TYPE_MARKET,
            side=side,
            quantity=qty
        )

        open_positions[symbol] = {
            "side": signal, "entry": price, "qty": qty, "sl": sl, "tp": tp, "trailing_active": False
        }

        return qty
    except Exception as e:
        print(f"[ERROR] Orden {symbol}: {e}")
        return None

def manage_positions():
    """Verifica SL, TP y trailing stop"""
    for symbol, pos in list(open_positions.items()):
        price = float(client.futures_symbol_ticker(symbol=symbol)['price'])
        side = pos["side"]
        entry = pos["entry"]
        sl = pos["sl"]
        tp = pos["tp"]
        qty = pos["qty"]

        profit_pct = (price - entry) / entry if side == "LONG" else (entry - price) / entry

        # SL / TP
        if (side == "LONG" and price <= sl) or (side == "SHORT" and price >= sl):
            send_telegram(f"🔻 SL alcanzado {symbol}, cerrando posición.")
            client.futures_create_order(symbol=symbol, side=SIDE_SELL if side=="LONG" else SIDE_BUY,
                                        type=ORDER_TYPE_MARKET, quantity=qty)
            open_positions.pop(symbol)
            continue

        if (side == "LONG" and price >= tp) or (side == "SHORT" and price <= tp):
            send_telegram(f"✅ TP alcanzado {symbol}, cerrando posición.")
            client.futures_create_order(symbol=symbol, side=SIDE_SELL if side=="LONG" else SIDE_BUY,
                                        type=ORDER_TYPE_MARKET, quantity=qty)
            open_positions.pop(symbol)
            continue

        # Trailing Stop
        if profit_pct >= TRAILING_START:
            if not pos["trailing_active"]:
                pos["trailing_active"] = True
                send_telegram(f"🎯 Trailing Stop activado para {symbol}")

            trail_price = price * (1 - TRAILING_STEP if side=="LONG" else 1 + TRAILING_STEP)
            if (side=="LONG" and trail_price > pos["sl"]) or (side=="SHORT" and trail_price < pos["sl"]):
                pos["sl"] = trail_price

def analyze_all():
    news_score = check_news_sentiment()
    for symbol in SYMBOLS:
        data = analyze_symbol(symbol)
        if not data:
            continue
        if data['confidence'] < 70 or not can_alert(symbol):
            continue

        msg = (f"⚡ Señal {data['signal']} {symbol}\n"
               f"Precio: {data['price']}\nTP: {data['tp']} | SL: {data['sl']}\n"
               f"Confianza: {data['confidence']}%\nSentimiento noticias: {news_score}%")

        qty = None
        if data['confidence'] >= 90:
            qty = place_futures_order(data['symbol'], data['signal'], data['price'], data['sl'], data['tp'])
            msg += f"\n{'✅ Posición abierta' if qty else '⚠️ No se pudo abrir posición'} x{LEVERAGE}"

        send_telegram(msg)
        last_alerts[symbol] = datetime.now()

def hourly_summary():
    balance = float(client.futures_account_balance()[1]['balance'])
    msg = f"📊 Resumen {datetime.now().strftime('%H:%M')}\nBalance USDT: {balance}\nPosiciones abiertas: {len(open_positions)}"
    send_telegram(msg)

# ================== LOOP PRINCIPAL ==================
send_telegram("🤖 Bot de trading con Trailing inicializado correctamente.")

schedule.every(30).minutes.do(analyze_all)
schedule.every(10).minutes.do(manage_positions)
schedule.every().hour.do(hourly_summary)

while True:
    schedule.run_pending()
    time.sleep(10)

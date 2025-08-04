import os
import time
import requests
import pandas as pd
import numpy as np
import ccxt
from datetime import datetime
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD
from telegram import Bot

# =================== CONFIG ===================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")

LEVERAGE = 5
TIMEFRAME = '15m'       # Temporalidad para análisis
LIMIT = 200             # Velas para indicadores
CHECK_INTERVAL = 60*60*3  # Cada 3 horas analiza nuevas entradas
MIN_ALERT_PROB = 70
TRADE_PROB = 90

# Lista de símbolos a analizar
symbols = [
    'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT', 'DOGE/USDT', 'ADA/USDT', 'MATIC/USDT',
    'DOT/USDT', 'LTC/USDT', 'TRX/USDT', 'AVAX/USDT', 'UNI/USDT', 'XLM/USDT', 'ATOM/USDT', 'LINK/USDT',
    'AAVE/USDT', 'SAND/USDT', 'AXS/USDT', 'MANA/USDT', 'ICP/USDT', 'FIL/USDT', 'HBAR/USDT', 'EGLD/USDT',
    'APT/USDT', 'AR/USDT', 'RUNE/USDT', 'FLOW/USDT', 'THETA/USDT', 'XTZ/USDT', 'GRT/USDT', '1INCH/USDT',
    'OCEAN/USDT', 'RNDR/USDT', 'SUI/USDT', 'PYTH/USDT', 'BLUR/USDT', 'JTO/USDT', 'FTM/USDT', 'NEAR/USDT',
    'CHZ/USDT', 'CRV/USDT', 'DYDX/USDT', 'LRC/USDT', 'ZIL/USDT', 'QTUM/USDT', 'BAND/USDT', 'COTI/USDT',
    'ROSE/USDT', 'KAVA/USDT', 'ALGO/USDT', 'MINA/USDT', 'CFX/USDT', 'ANKR/USDT', 'GALA/USDT', 'ENS/USDT',
    'FLUX/USDT', 'PEPE/USDT', '1000SHIB/USDT', 'WOO/USDT', 'FET/USDT', 'OP/USDT'
]

# =================== INIT ===================
bot = Bot(token=TELEGRAM_TOKEN)
exchange = ccxt.binance({
    'apiKey': BINANCE_API_KEY,
    'secret': BINANCE_API_SECRET,
    'enableRateLimit': True,
    'options': {'defaultType': 'future'}
})

sent_alerts = {}  # Para no repetir alertas

# =================== FUNCIONES ===================
def send_telegram(msg):
    try:
        bot.send_message(chat_id=CHAT_ID, text=msg)
    except Exception as e:
        print("Error enviando Telegram:", e)

def fetch_news():
    url = "https://cryptopanic.com/api/v1/posts/?auth_token=demo&currencies=BTC,ETH&kind=news"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            posts = r.json().get("results", [])
            return [f"{p['title']} ({p['domain']})" for p in posts[:3]]
    except:
        return []
    return []

def fetch_klines(symbol):
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=LIMIT)
    df = pd.DataFrame(ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
    df['close'] = df['close'].astype(float)
    return df

def analyze_symbol(symbol):
    df = fetch_klines(symbol)
    if df.empty: return None

    close = df['close']

    # Calcular indicadores
    rsi = RSIIndicator(close).rsi()
    ema_fast = EMAIndicator(close, 9).ema_indicator()
    ema_slow = EMAIndicator(close, 21).ema_indicator()
    macd = MACD(close).macd()
    macd_signal = MACD(close).macd_signal()

    last_rsi = rsi.iloc[-1]
    last_macd = macd.iloc[-1]
    last_signal = macd_signal.iloc[-1]
    last_ema_fast = ema_fast.iloc[-1]
    last_ema_slow = ema_slow.iloc[-1]
    last_price = close.iloc[-1]

    # Estrategias
    strat_rsi = last_rsi < 30 or last_rsi > 70
    strat_ema = last_ema_fast > last_ema_slow
    strat_macd = last_macd > last_signal

    signals = [strat_rsi, strat_ema, strat_macd]
    score = sum(signals)
    prob = round((score / 3) * 100, 2)

    direction = "LONG" if last_ema_fast > last_ema_slow and last_macd > last_signal else "SHORT"
    tp = last_price * (1.02 if direction == "LONG" else 0.98)
    sl = last_price * (0.98 if direction == "LONG" else 1.02)

    return {
        'symbol': symbol,
        'price': last_price,
        'prob': prob,
        'direction': direction,
        'tp': tp,
        'sl': sl
    }

def check_balance_and_trade(signal):
    try:
        balance = exchange.fetch_balance()
        usdt = balance['total'].get('USDT', 0)
        if usdt < 10:
            send_telegram(f"⚠️ No hay saldo para abrir {signal['symbol']} {signal['direction']}")
            return False

        amount = round((usdt * 0.05) / signal['price'], 3)  # 5% capital
        params = {'positionSide': 'LONG' if signal['direction']=="LONG" else 'SHORT'}

        order = exchange.create_market_order(
            signal['symbol'].replace("/", ""),
            'buy' if signal['direction']=="LONG" else 'sell',
            amount,
            params=params
        )
        send_telegram(f"✅ Orden abierta: {signal['symbol']} {signal['direction']} x{LEVERAGE}\n"
                      f"Entrada: {signal['price']}\nTP: {signal['tp']}\nSL: {signal['sl']}")
        return True
    except Exception as e:
        send_telegram(f"❌ Error al abrir {signal['symbol']}: {e}")
        return False

def main_loop():
    news = fetch_news()
    if news:
        send_telegram("📰 Noticias recientes:\n" + "\n".join(news))

    for symbol in symbols:
        signal = analyze_symbol(symbol)
        if not signal: 
            continue

        if signal['prob'] >= MIN_ALERT_PROB:
            alert_key = f"{symbol}_{signal['direction']}"
            if alert_key not in sent_alerts or (time.time() - sent_alerts[alert_key]) > CHECK_INTERVAL:
                sent_alerts[alert_key] = time.time()
                msg = f"📊 {signal['symbol']} {signal['direction']}\n" \
                      f"Prob: {signal['prob']}%\n" \
                      f"Entrada: {signal['price']:.4f}\nTP: {signal['tp']:.4f} SL: {signal['sl']:.4f}"
                send_telegram(msg)

                if signal['prob'] >= TRADE_PROB:
                    check_balance_and_trade(signal)

if __name__ == "__main__":
    send_telegram("🤖 Bot de Trading iniciado correctamente.")
    while True:
        try:
            main_loop()
            time.sleep(CHECK_INTERVAL)
        except Exception as e:
            send_telegram(f"❌ Error en el bot: {e}")
            time.sleep(60)

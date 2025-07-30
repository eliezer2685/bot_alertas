import ccxt
import pandas as pd
import numpy as np
import ta
import json
import os
import asyncio
import datetime
import time
from telegram import Bot

# ===== Configuración del Bot =====
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8130687378:AAFLSy-BVZ3oAtMgft5mC4GwqtYuOZEu8a4")
CHAT_ID = os.getenv("CHAT_ID", "6158517156")
bot = Bot(token=TELEGRAM_TOKEN)

# ===== Conexión a Binance Futures =====
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'adjustForTimeDifference': True},
    'defaultType': 'future'  # <--- FUTUROS
})

# ===== Archivos =====
COINS_FILE = "monedas_hoy.json"
ALERTS_FILE = "alertas_enviadas.json"

# ===== Funciones auxiliares =====
def load_json(file):
    if os.path.exists(file):
        with open(file, "r") as f:
            return json.load(f)
    return []

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f)

def select_daily_coins(n=20):
    markets = exchange.load_markets()
    futures = [m for m in markets if m.endswith("/USDT") and markets[m]['info']['contractType'] == 'PERPETUAL']
    selected = np.random.choice(futures, n, replace=False).tolist()
    save_json(COINS_FILE, selected)
    save_json(ALERTS_FILE, [])  # reset alertas
    return selected

def fetch_ohlcv_safe(symbol, retries=3):
    for attempt in range(retries):
        try:
            return exchange.fetch_ohlcv(symbol, timeframe='1h', limit=150)
        except Exception as e:
            print(f"⚠️ Error {symbol} intento {attempt+1}: {e}")
            time.sleep(2)
    return None

def get_signal(symbol):
    ohlcv = fetch_ohlcv_safe(symbol)
    if ohlcv is None:
        return None

    df = pd.DataFrame(ohlcv, columns=['time','open','high','low','close','volume'])
    close = df['close']

    # Indicadores
    df['rsi'] = ta.momentum.RSIIndicator(close, window=14).rsi()
    df['ema9'] = close.ewm(span=9).mean()
    df['ema21'] = close.ewm(span=21).mean()
    df['ema20'] = close.ewm(span=20).mean()
    df['ema50'] = close.ewm(span=50).mean()
    df['ema200'] = close.ewm(span=200).mean()

    macd = ta.trend.MACD(close)
    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()

    bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    df['bb_low'] = bb.bollinger_lband()

    df['vol_mean20'] = df['volume'].rolling(20).mean()

    atr = ta.volatility.AverageTrueRange(df['high'], df['low'], close, window=14)
    df['atr'] = atr.average_true_range()

    df['cci'] = ta.trend.CCIIndicator(df['high'], df['low'], close, window=20).cci()
    stoch = ta.momentum.StochasticOscillator(df['high'], df['low'], close, window=14, smooth_window=3)
    df['stoch_k'] = stoch.stoch()
    df['stoch_d'] = stoch.stoch_signal()
    adx = ta.trend.ADXIndicator(df['high'], df['low'], close, window=14)
    df['adx'] = adx.adx()
    df['di_plus'] = adx.adx_pos()
    df['di_minus'] = adx.adx_neg()

    # Evaluar última vela
    last = df.iloc[-1]
    prev = df.iloc[-2]
    signals = []

    if last.rsi < 35: signals.append("RSI<35")
    if prev.macd < prev.macd_signal and last.macd > last.macd_signal: signals.append("MACD alcista")
    if last.close < last.bb_low: signals.append("Bollinger baja")
    if last.volume > 2*last.vol_mean20: signals.append("Volumen 2x")
    if last.cci < -100: signals.append("CCI sobreventa")
    if prev.stoch_k < prev.stoch_d and last.stoch_k > last.stoch_d and last.stoch_k < 30: signals.append("Stoch alcista")
    if last.adx > 25 and last.di_plus > last.di_minus: signals.append("ADX fuerte")
    if prev.ema9 < prev.ema21 and last.ema9 > last.ema21: signals.append("EMA9>EMA21")

    # Solo alerta si >=4 señales
    if len(signals) >= 4:
        entry = round(last.close, 4)
        sl = round(entry - last.atr*1.5, 4)
        tp1 = round(entry + last.atr*1.5, 4)
        tp2 = round(entry + last.atr*2.5, 4)
        tp3 = round(entry + last.atr*4, 4)

        return (
            f"📈 {symbol} FUTUROS\n"
            f"Señales: {', '.join(signals)}\n"
            f"🎯 Entrada: {entry}\n"
            f"🛡️ SL: {sl}\n"
            f"TP1: {tp1} | TP2: {tp2} | TP3: {tp3}"
        )
    return None

async def send_alerts():
    coins_today = load_json(COINS_FILE)
    alerts_sent = load_json(ALERTS_FILE)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    await bot.send_message(chat_id=CHAT_ID, text=f"⏰ Analizando {len(coins_today)} monedas - {now}")

    for coin in coins_today:
        signal = get_signal(coin)
        if signal and coin not in alerts_sent:
            await bot.send_message(chat_id=CHAT_ID, text=signal)
            alerts_sent.append(coin)
            save_json(ALERTS_FILE, alerts_sent)
        time.sleep(1)

def loop_trading_bot():
    while True:
        now = datetime.datetime.now()
        hour = now.hour

        # Reset diario a las 6:00
        if hour == 6 and not os.path.exists(COINS_FILE):
            select_daily_coins(20)

        # Analiza cada 2h entre 6 y 22
        if 6 <= hour <= 22 and hour % 2 == 0:
            asyncio.run(send_alerts())
            time.sleep(3600*2)
        else:
            time.sleep(600)  # espera 10min y vuelve a chequear

if __name__ == "__main__":
    loop_trading_bot()

import random
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

# 🔹 Configuración del Bot
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8130687378:AAFLSy-BVZ3oAtMgft5mC4GwqtYuOZEu8a4")
CHAT_ID = os.getenv("CHAT_ID", "6158517156")
bot = Bot(token=TELEGRAM_TOKEN)

# 🔹 Conexión a Binance con rate limit y ajuste de hora
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'adjustForTimeDifference': True}
})

# 🔹 Lista ampliada de criptos (36 monedas)
coins = [
    "BTC/USDT","ETH/USDT","BNB/USDT","ADA/USDT","XRP/USDT","DOGE/USDT",
    "SOL/USDT","DOT/USDT","MATIC/USDT","LTC/USDT","AVAX/USDT","TRX/USDT",
    "SHIB/USDT","ATOM/USDT","FIL/USDT","AAVE/USDT","NEAR/USDT","ICP/USDT",
    "GALA/USDT","FTM/USDT","SAND/USDT","MANA/USDT","VET/USDT","ALGO/USDT",
    "FLOW/USDT","CHZ/USDT","EGLD/USDT","KSM/USDT","THETA/USDT","XTZ/USDT",
    "ENJ/USDT","ZIL/USDT","HNT/USDT","RUNE/USDT","CRV/USDT","1INCH/USDT"
]

# 🔹 Archivo para guardar últimas monedas usadas
HISTORY_FILE = "last_coins.json"

def load_last_coins():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    return []

def save_last_coins(coins_list):
    with open(HISTORY_FILE, "w") as f:
        json.dump(coins_list, f)

def select_random_coins(n=20):
    last_coins = load_last_coins()
    available = [c for c in coins if c not in last_coins]
    if len(available) < n:
        available = coins  # Si se acaban, reinicia
    selected = random.sample(available, n)
    save_last_coins(selected)
    return selected

def fetch_ohlcv_safe(symbol, retries=3):
    """Intenta descargar OHLCV con reintentos"""
    for attempt in range(retries):
        try:
            return exchange.fetch_ohlcv(symbol, timeframe='1h', limit=150)
        except Exception as e:
            print(f"⚠️ Error {symbol} intento {attempt+1}: {e}")
            time.sleep(2)  # espera antes de reintentar
    return None

def get_signal(symbol):
    ohlcv = fetch_ohlcv_safe(symbol)
    if ohlcv is None:
        return None

    df = pd.DataFrame(ohlcv, columns=['time','open','high','low','close','volume'])
    close = df['close']

    # 🔹 Indicadores
    df['rsi'] = ta.momentum.RSIIndicator(close, window=14).rsi()
    df['ema9'] = close.ewm(span=9).mean()
    df['ema21'] = close.ewm(span=21).mean()
    df['ema20'] = close.ewm(span=20).mean()
    df['ema50'] = close.ewm(span=50).mean()
    df['ema200'] = close.ewm(span=200).mean()

    macd = ta.trend.MACD(close)
    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()

    bb = ta.volatility.BollingerBands(close, window=20, ndev=2)
    df['bb_low'] = bb.bollinger_lband()

    df['vol_mean20'] = df['volume'].rolling(20).mean()

    atr = ta.volatility.AverageTrueRange(df['high'], df['low'], close, window=14)
    df['atr'] = atr.average_true_range()

    # Nuevos indicadores
    df['cci'] = ta.trend.CCIIndicator(df['high'], df['low'], close, window=20).cci()
    stoch = ta.momentum.StochasticOscillator(df['high'], df['low'], close, window=14, smooth_window=3)
    df['stoch_k'] = stoch.stoch()
    df['stoch_d'] = stoch.stoch_signal()
    adx = ta.trend.ADXIndicator(df['high'], df['low'], close, window=14)
    df['adx'] = adx.adx()
    df['di_plus'] = adx.adx_pos()
    df['di_minus'] = adx.adx_neg()

    # 🔹 Últimos valores
    last = df.iloc[-1]
    prev = df.iloc[-2]
    signals = []

    # 🔹 Estrategias
    if last.rsi < 35 and last.ema20 > last.ema50 and last.close > last.ema200:
        signals.append("RSI+EMAs (rebote alcista)")

    if prev.macd < prev.macd_signal and last.macd > last.macd_signal:
        signals.append("MACD Alcista")

    if last.close < last.bb_low:
        signals.append("Bollinger Inferior (posible rebote)")

    if last.volume > 2 * last.vol_mean20:
        signals.append("Volumen Explosivo")

    if last.cci < -100:
        signals.append("CCI sobreventa")

    if prev.stoch_k < prev.stoch_d and last.stoch_k > last.stoch_d and last.stoch_k < 30:
        signals.append("Estocástico Alcista")

    if last.adx > 25 and last.di_plus > last.di_minus:
        signals.append("Tendencia Fuerte Alcista (ADX)")

    if prev.ema9 < prev.ema21 and last.ema9 > last.ema21:
        signals.append("Cruce EMA9>EMA21")

    if signals:
        entry = round(last.close, 4)
        sl = round(entry - last.atr*1.5, 4)
        tp1 = round(entry + last.atr*1.5, 4)
        tp2 = round(entry + last.atr*2.5, 4)
        tp3 = round(entry + last.atr*4, 4)

        return (
            f"📈 {symbol}\n"
            f"Señales detectadas: {', '.join(signals)}\n"
            f"🎯 Entrada: {entry}\n"
            f"🛡️ SL: {sl}\n"
            f"TP1: {tp1}\nTP2: {tp2}\nTP3: {tp3}"
        )
    return None

async def send_alerts():
    selected_coins = select_random_coins(20)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    await bot.send_message(
        chat_id=CHAT_ID,
        text=f"📊 Alertas de Trading - {now}\nMonedas: {', '.join(selected_coins)}"
    )

    for coin in selected_coins:
        signal = get_signal(coin)
        if signal:
            await bot.send_message(chat_id=CHAT_ID, text=signal)
        time.sleep(1)  # 🔹 Espera 1s entre requests para no saturar Binance

def loop_trading_bot():
    while True:
        hour = datetime.datetime.now().hour
        if 6 <= hour <= 22:
            asyncio.run(send_alerts())
        time.sleep(3600)

if __name__ == "__main__":
    loop_trading_bot()

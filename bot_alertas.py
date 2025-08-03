import os
import time
import datetime
import pandas as pd
import numpy as np
import requests
import schedule
from telegram import Bot

# ============================
# 🔹 Configuración de Telegram
# ============================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")

if not all([TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
    print("❌ ERROR: Variables de entorno no configuradas.")
    exit()

bot = Bot(token=TELEGRAM_TOKEN)

# ============================
# 🔹 Lista de 50 monedas Spot
# ============================
symbols = [
    "BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","SOLUSDT","DOGEUSDT","ADAUSDT","TRXUSDT","MATICUSDT","LTCUSDT",
    "DOTUSDT","SHIBUSDT","AVAXUSDT","UNIUSDT","ATOMUSDT","LINKUSDT","XLMUSDT","FILUSDT","ICPUSDT","APTUSDT",
    "ARBUSDT","SANDUSDT","MANAUSDT","APEUSDT","AXSUSDT","NEARUSDT","EOSUSDT","FLOWUSDT","XTZUSDT","THETAUSDT",
    "AAVEUSDT","GRTUSDT","RUNEUSDT","KAVAUSDT","CRVUSDT","FTMUSDT","CHZUSDT","SNXUSDT","LDOUSDT","OPUSDT",
    "COMPUSDT","DYDXUSDT","BLURUSDT","RNDRUSDT","GMTUSDT","1INCHUSDT","OCEANUSDT","SUIUSDT","PYTHUSDT","JTOUSDT"
]

# ============================
# 🔹 Obtener velas de Binance
# ============================
def get_klines(symbol, interval="15m", limit=200):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        data = requests.get(url, timeout=10).json()
        if isinstance(data, dict) and "code" in data:
            print(f"⚠️ Error Binance: {data}")
            return None
        df = pd.DataFrame(data, columns=[
            'time','open','high','low','close','volume','close_time','qav','num_trades','taker_base','taker_quote','ignore'
        ])
        df['time'] = pd.to_datetime(df['time'], unit='ms')
        df['close'] = df['close'].astype(float)
        df['volume'] = df['volume'].astype(float)
        return df[['time','close','volume']]
    except Exception as e:
        print(f"⚠️ Error obteniendo velas para {symbol}: {e}")
        return None

# ============================
# 🔹 Indicadores Técnicos
# ============================
def calculate_indicators(df):
    df['EMA50'] = df['close'].ewm(span=50).mean()
    df['EMA200'] = df['close'].ewm(span=200).mean()

    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    return df

# ============================
# 🔹 Analizar mercado
# ============================
last_signals = {}

def analyze_market():
    print(f"\n🔍 Analizando {len(symbols)} monedas Spot... {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    candidate_signals = []

    for symbol in symbols:
        df = get_klines(symbol)
        if df is None or len(df) < 50:
            continue

        df = calculate_indicators(df)
        last_row = df.iloc[-1]

        close_price = last_row['close']
        rsi = last_row['RSI']
        ema50 = last_row['EMA50']
        ema200 = last_row['EMA200']

        # Log de depuración
        print(f"{symbol} → Precio: {close_price:.4f}, RSI: {rsi:.2f}, EMA50: {ema50:.2f}, EMA200: {ema200:.2f}")

        signal = None
        if rsi < 30 and ema50 > ema200:
            signal = "LONG"
        elif rsi > 70 and ema50 < ema200:
            signal = "SHORT"

        if signal:
            # Evita repetir señal reciente
            last_signal_time = last_signals.get(symbol)
            if last_signal_time and (datetime.datetime.now() - last_signal_time).seconds < 3600:
                continue

            tp = round(close_price * (1.02 if signal == "LONG" else 0.98), 6)
            sl = round(close_price * (0.98 if signal == "LONG" else 1.02), 6)
            candidate_signals.append((symbol, signal, close_price, tp, sl))

    # Enviar señales
    if candidate_signals:
        for sym, sig, price, tp, sl in candidate_signals:
            msg = (
                f"🔔 Señal Detectada\n"
                f"Moneda: {sym}\n"
                f"Tipo: {sig}\n"
                f"Entrada: {price}\n"
                f"TP: {tp}\n"
                f"SL: {sl}\n"
                f"Apalancamiento sugerido: x10\n"
            )
            bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
            last_signals[sym] = datetime.datetime.now()
            print(f"📤 Señal enviada: {sym} {sig}")
    else:
        print("⚠️ No se detectaron señales en este ciclo")
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="⚠️ No se detectaron señales en este ciclo")

# ============================
# 🔹 Scheduler
# ============================
schedule.every(15).minutes.do(analyze_market)

bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="🚀 Bot Spot Binance iniciado correctamente...")
print("✅ Bot Spot Binance iniciado. Analiza cada 15 minutos...")

while True:
    schedule.run_pending()
    time.sleep(1)

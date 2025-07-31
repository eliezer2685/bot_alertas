import ccxt
import pandas as pd
import random
import time
from datetime import datetime
import ta
from telegram import Bot
import os

# ==============================
# CONFIGURACIÓN
# ==============================
API_KEY = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if not API_KEY or not CHAT_ID:
    print("❌ ERROR: Variables de entorno TELEGRAM_TOKEN o TELEGRAM_CHAT_ID no configuradas.")
    exit(1)

INTERVALO_HORAS = 1             # Cada 1 hora
TIMEFRAMES = ['1h', '4h']       # Temporalidades medias

SYMBOLS = [
    "BTC/USDT","ETH/USDT","BNB/USDT","XRP/USDT","ADA/USDT","DOGE/USDT","SOL/USDT",
    "MATIC/USDT","DOT/USDT","LTC/USDT","TRX/USDT","AVAX/USDT","SHIB/USDT","UNI/USDT",
    "ATOM/USDT","LINK/USDT","XLM/USDT","ETC/USDT","XMR/USDT","NEAR/USDT","APT/USDT",
    "ARB/USDT","FIL/USDT","SAND/USDT","AAVE/USDT","EOS/USDT","MANA/USDT","THETA/USDT",
    "FTM/USDT","KAVA/USDT"
]

bot = Bot(token=API_KEY)
exchange = ccxt.binance()

ultimas_alertas = set()  # Para evitar alertas repetidas

# ==============================
# FUNCIONES DE INDICADORES Y SEÑALES
# ==============================
def calcular_indicadores(df):
    df['rsi'] = ta.momentum.RSIIndicator(df['close'], 14).rsi()
    df['ema_fast'] = df['close'].ewm(span=9).mean()
    df['ema_slow'] = df['close'].ewm(span=21).mean()
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = exp1 - exp2
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    return df

def generar_senal(df, symbol):
    """Evalúa RSI + cruce EMA + MACD para generar señal"""
    score = 0
    signal_type = None  # long o short

    # RSI
    if df['rsi'].iloc[-1] < 30:
        score += 1
        signal_type = "long"
    elif df['rsi'].iloc[-1] > 70:
        score += 1
        signal_type = "short"

    # Cruce EMA
    if df['ema_fast'].iloc[-2] < df['ema_slow'].iloc[-2] and df['ema_fast'].iloc[-1] > df['ema_slow'].iloc[-1]:
        score += 2
        signal_type = "long"
    if df['ema_fast'].iloc[-2] > df['ema_slow'].iloc[-2] and df['ema_fast'].iloc[-1] < df['ema_slow'].iloc[-1]:
        score += 2
        signal_type = "short"

    # MACD
    if df['macd'].iloc[-1] > df['macd_signal'].iloc[-1] and df['macd'].iloc[-2] <= df['macd_signal'].iloc[-2]:
        score += 2
        signal_type = "long"
    if df['macd'].iloc[-1] < df['macd_signal'].iloc[-1] and df['macd'].iloc[-2] >= df['macd_signal'].iloc[-2]:
        score += 2
        signal_type = "short"

    # Solo señales fuertes
    if score >= 3 and signal_type:
        price = df['close'].iloc[-1]
        if signal_type == "long":
            sl = round(price * 0.98, 4)
            tp1 = round(price * 1.02, 4)
            tp2 = round(price * 1.04, 4)
        else:
            sl = round(price * 1.02, 4)
            tp1 = round(price * 0.98, 4)
            tp2 = round(price * 0.96, 4)

        mensaje = (
            f"📊 Señal {signal_type.upper()} para {symbol}\n"
            f"💵 Entrada: {price}\n"
            f"🛑 Stop Loss: {sl}\n"
            f"🎯 TP1: {tp1}\n"
            f"🎯 TP2: {tp2}\n"
            f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        return mensaje
    return None

def analizar_moneda(symbol):
    senales = []
    for tf in TIMEFRAMES:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe=tf, limit=150)
            if not ohlcv:
                continue

            df = pd.DataFrame(ohlcv, columns=['timestamp','open','high','low','close','volume'])
            df = calcular_indicadores(df)

            mensaje = generar_senal(df, symbol)
            if mensaje:
                senales.append(mensaje)
        except:
            continue
    return senales

# ==============================
# LOOP PRINCIPAL
# ==============================
if __name__ == "__main__":
    while True:
        seleccion = random.sample(SYMBOLS, 30)
        print(f"🔹 Analizando {len(seleccion)} monedas...")

        todas_senales = []
        for symbol in seleccion:
            todas_senales.extend(analizar_moneda(symbol))

        # Tomar solo 10 señales nuevas
        nuevas = [s for s in todas_senales if s not in ultimas_alertas][:10]

        for alerta in nuevas:
            bot.send_message(chat_id=CHAT_ID, text=alerta)
            ultimas_alertas.add(alerta)

        print(f"✅ Enviadas {len(nuevas)} nuevas señales.")
        print(f"⏳ Esperando {INTERVALO_HORAS} horas...")
        time.sleep(INTERVALO_HORAS * 3600)

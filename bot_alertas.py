import ccxt
import pandas as pd
import ta
import random
import time
import os
from datetime import datetime
from telegram import Bot

# ==============================
# DEBUG DE VARIABLES
# ==============================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")

print("=== DEBUG VARIABLES DE ENTORNO ===")
print("TELEGRAM_TOKEN:", "OK" if TELEGRAM_TOKEN else "❌ NONE")
print("CHAT_ID:", CHAT_ID if CHAT_ID else "❌ NONE")
print("BINANCE_API_KEY:", BINANCE_API_KEY[:4]+"****" if BINANCE_API_KEY else "❌ NONE")
print("BINANCE_API_SECRET:", BINANCE_API_SECRET[:4]+"****" if BINANCE_API_SECRET else "❌ NONE")
print("=================================")

if not TELEGRAM_TOKEN or not CHAT_ID or not BINANCE_API_KEY or not BINANCE_API_SECRET:
    print("❌ ERROR: Variables de entorno no configuradas correctamente.")
    # Si tenemos token y chat, avisamos por Telegram
    if TELEGRAM_TOKEN and CHAT_ID:
        bot = Bot(token=TELEGRAM_TOKEN)
        bot.send_message(chat_id=CHAT_ID, text="❌ ERROR: Variables de entorno no configuradas.")
    exit(1)

bot = Bot(token=TELEGRAM_TOKEN)

# ==============================
# CONFIGURACIÓN DEL BOT
# ==============================
INTERVALO_HORAS = 1
TIMEFRAMES = ['1h', '4h']
SYMBOLS = [
    "BTC/USDT","ETH/USDT","BNB/USDT","XRP/USDT","ADA/USDT",
    "DOGE/USDT","SOL/USDT","MATIC/USDT","DOT/USDT","LTC/USDT",
    "TRX/USDT","AVAX/USDT","SHIB/USDT","UNI/USDT","ATOM/USDT",
    "LINK/USDT","XLM/USDT","ETC/USDT","XMR/USDT","NEAR/USDT",
    "APT/USDT","ARB/USDT","SUI/USDT","OP/USDT","AAVE/USDT",
    "FIL/USDT","EOS/USDT","THETA/USDT","FLOW/USDT","ALGO/USDT"
]

exchange = ccxt.binance({
    'apiKey': BINANCE_API_KEY,
    'secret': BINANCE_API_SECRET,
    'options': {'defaultType': 'future'}  # FUTUROS
})

ultimas_senales = set()

# ==============================
# INICIO DEL BOT
# ==============================
bot.send_message(chat_id=CHAT_ID, text="✅ Bot de Trading iniciado. Variables de entorno OK.")

# ==============================
# FUNCIONES DE INDICADORES
# ==============================
def calcular_indicadores(df):
    df['ema_fast'] = df['close'].ewm(span=9).mean()
    df['ema_slow'] = df['close'].ewm(span=21).mean()
    df['rsi'] = ta.momentum.RSIIndicator(df['close'], 14).rsi()
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = exp1 - exp2
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    return df

def generar_senal(df, symbol, tf):
    precio_actual = df['close'].iloc[-1]
    ema_fast, ema_slow = df['ema_fast'].iloc[-1], df['ema_slow'].iloc[-1]
    rsi = df['rsi'].iloc[-1]
    macd, macd_signal = df['macd'].iloc[-1], df['macd_signal'].iloc[-1]

    if ema_fast > ema_slow and macd > macd_signal and rsi < 70:
        tipo = "LONG"
        fuerza = (rsi / 70) * 0.4 + 0.6
    elif ema_fast < ema_slow and macd < macd_signal and rsi > 30:
        tipo = "SHORT"
        fuerza = ((100 - rsi) / 70) * 0.4 + 0.6
    else:
        return None

    if tipo == "LONG":
        sl = round(precio_actual * 0.985, 4)
        tp1 = round(precio_actual * 1.015, 4)
        tp2 = round(precio_actual * 1.03, 4)
    else:
        sl = round(precio_actual * 1.015, 4)
        tp1 = round(precio_actual * 0.985, 4)
        tp2 = round(precio_actual * 0.97, 4)

    return {
        "symbol": symbol,
        "tf": tf,
        "tipo": tipo,
        "precio": round(precio_actual, 4),
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "fuerza": fuerza
    }

def analizar_moneda(symbol):
    señales = []
    for tf in TIMEFRAMES:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe=tf, limit=150)
            if not ohlcv:
                continue

            df = pd.DataFrame(ohlcv, columns=['timestamp','open','high','low','close','volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df = calcular_indicadores(df)

            señal = generar_senal(df, symbol, tf)
            if señal:
                señales.append(señal)

        except Exception as e:
            print(f"❌ Error en {symbol} {tf}: {e}")
    return señales

# ==============================
# LOOP PRINCIPAL
# ==============================
while True:
    seleccion = random.sample(SYMBOLS, 30)
    print(f"🔹 Analizando {len(seleccion)} monedas: {seleccion}")

    todas_senales = []
    for symbol in seleccion:
        todas_senales.extend(analizar_moneda(symbol))

    nuevas_senales = [s for s in todas_senales if f"{s['symbol']}_{s['tf']}_{s['tipo']}" not in ultimas_senales]
    nuevas_senales.sort(key=lambda x: x['fuerza'], reverse=True)
    top_senales = nuevas_senales[:10]

    if not top_senales:
        bot.send_message(chat_id=CHAT_ID, text=f"⏳ Bot activo, sin señales detectadas. {datetime.now().strftime('%H:%M')}")

    for s in top_senales:
        mensaje = (f"📊 {s['symbol']} | {s['tf']} | {s['tipo']}\n"
                   f"💰 Entrada: {s['precio']}\n"
                   f"⛔ SL: {s['sl']}\n"
                   f"🎯 TP1: {s['tp1']} | TP2: {s['tp2']}\n"
                   f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(mensaje)
        bot.send_message(chat_id=CHAT_ID, text=mensaje)
        ultimas_senales.add(f"{s['symbol']}_{s['tf']}_{s['tipo']}")

    print(f"✅ {len(top_senales)} señales enviadas.")
    print(f"⏳ Esperando {INTERVALO_HORAS} horas para próximo análisis...")
    time.sleep(INTERVALO_HORAS * 3600)

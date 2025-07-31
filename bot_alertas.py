import ccxt
import pandas as pd
import ta
import random
import time
import os
from datetime import datetime
from telegram import Bot

# ==============================
# VARIABLES DE ENTORNO
# ==============================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")

if not TELEGRAM_TOKEN or not CHAT_ID or not BINANCE_API_KEY or not BINANCE_API_SECRET:
    print("❌ ERROR: Variables de entorno no configuradas.")
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

# Configuración de trading
MONTO_USD = 20           # Monto por operación
APALANCAMIENTO = 10      # x10
SL_USD = 3               # Stop Loss 3 USD
TP_USD = 5               # Take Profit 5 USD

exchange = ccxt.binance({
    'apiKey': BINANCE_API_KEY,
    'secret': BINANCE_API_SECRET,
    'options': {'defaultType': 'future'}
})

ultimas_senales = set()

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
    elif ema_fast < ema_slow and macd < macd_signal and rsi > 30:
        tipo = "SHORT"
    else:
        return None

    return {
        "symbol": symbol,
        "tf": tf,
        "tipo": tipo,
        "precio": round(precio_actual, 4)
    }

def abrir_posicion(signal):
    symbol = signal["symbol"]
    tipo = signal["tipo"]
    precio = signal["precio"]

    # Configurar apalancamiento
    market = symbol.replace("/", "")
    exchange.fapiPrivate_post_leverage({'symbol': market, 'leverage': APALANCAMIENTO})

    # Calcular cantidad
    cantidad = round(MONTO_USD / precio, 3)

    # Abrir orden de mercado
    side = 'buy' if tipo == 'LONG' else 'sell'
    order = exchange.create_market_order(symbol, side, cantidad)

    # Mensaje a Telegram
    mensaje = (
        f"📊 {symbol} | {tipo}\n"
        f"💰 Entrada: {precio} | Cantidad: {cantidad}\n"
        f"🔹 Posición abierta en Binance Futures x{APALANCAMIENTO}\n"
        f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    bot.send_message(chat_id=CHAT_ID, text=mensaje)
    print(mensaje)

    return order

# ==============================
# LOOP PRINCIPAL
# ==============================
bot.send_message(chat_id=CHAT_ID, text="✅ Bot de Trading iniciado. Esperando señales...")

while True:
    seleccion = random.sample(SYMBOLS, 30)
    print(f"🔹 Analizando {len(seleccion)} monedas: {seleccion}")

    todas_senales = []
    for symbol in seleccion:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe=random.choice(TIMEFRAMES), limit=150)
            if not ohlcv:
                continue

            df = pd.DataFrame(ohlcv, columns=['timestamp','open','high','low','close','volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df = calcular_indicadores(df)

            señal = generar_senal(df, symbol, 'mix')
            if señal and f"{señal['symbol']}_{señal['tipo']}" not in ultimas_senales:
                ultimas_senales.add(f"{señal['symbol']}_{señal['tipo']}")
                abrir_posicion(señal)

        except Exception as e:
            print(f"❌ Error en {symbol}: {e}")

    print(f"⏳ Esperando {INTERVALO_HORAS} horas para próximo análisis...")
    time.sleep(INTERVALO_HORAS * 3600)

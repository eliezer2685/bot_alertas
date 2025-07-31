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
# CONFIGURACIÓN
# ==============================
INTERVALO_HORAS = 1
TIMEFRAMES = ['1h', '4h']

SYMBOLS = [
    "BTC/USDT","ETH/USDT","BNB/USDT","XRP/USDT","ADA/USDT",
    "DOGE/USDT","SOL/USDT","MATIC/USDT","DOT/USDT","LTC/USDT",
    "TRX/USDT","AVAX/USDT","SHIB/USDT","UNI/USDT","ATOM/USDT",
    "LINK/USDT","XLM/USDT","ETC/USDT","XMR/USDT","NEAR/USDT",
    "APT/USDT","ARB/USDT","SUI/USDT","OP/USDT","AAVE/USDT",
    "FIL/USDT","EOS/USDT","THETA/USDT","FLOW/USDT","ALGO/USDT",
    "GALA/USDT","FTM/USDT","SAND/USDT","AXS/USDT","CHZ/USDT",
    "MANA/USDT","IMX/USDT","RNDR/USDT","INJ/USDT","LDO/USDT"
]

MONTO_USD = 20         # Monto por operación
APALANCAMIENTO = 10    # x10
STOP_LOSS_USD = 3      # SL en dólares
TAKE_PROFIT_USD = 5    # TP en dólares

exchange = ccxt.binance({
    'apiKey': BINANCE_API_KEY,
    'secret': BINANCE_API_SECRET,
    'options': {'defaultType': 'future'}
})

ultimas_senales = set()

# ==============================
# FUNCIONES
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

def generar_senal(df, symbol):
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
        "tipo": tipo,
        "precio": round(precio_actual, 4)
    }

def balance_suficiente(monto):
    try:
        balance = exchange.fetch_balance()
        usdt = balance['total'].get('USDT', 0)
        return usdt >= monto, usdt
    except Exception as e:
        print(f"❌ Error al consultar balance: {e}")
        return False, 0

def abrir_posicion(signal):
    symbol = signal["symbol"]
    tipo = signal["tipo"]
    precio = signal["precio"]
    market = symbol.replace("/", "")

    # Verificar balance
    ok, usdt = balance_suficiente(MONTO_USD)
    if not ok:
        bot.send_message(chat_id=CHAT_ID, text=f"⚠️ No hay fondos suficientes para abrir {symbol} ({usdt:.2f} USDT)")
        return None

    # Configurar apalancamiento
    try:
        exchange.fapiPrivate_post_leverage({'symbol': market, 'leverage': APALANCAMIENTO})
    except Exception as e:
        print(f"⚠️ Error al configurar apalancamiento en {symbol}: {e}")

    # Calcular cantidad
    cantidad = round(MONTO_USD / precio, 3)
    side = 'buy' if tipo == 'LONG' else 'sell'

    # Crear orden de mercado
    order = exchange.create_market_order(symbol, side, cantidad)

    # Calcular SL y TP
    if tipo == "LONG":
        sl_price = round(precio - STOP_LOSS_USD / cantidad, 2)
        tp_price = round(precio + TAKE_PROFIT_USD / cantidad, 2)
    else:
        sl_price = round(precio + STOP_LOSS_USD / cantidad, 2)
        tp_price = round(precio - TAKE_PROFIT_USD / cantidad, 2)

    # Crear orden STOP y TP
    try:
        params = {'stopPrice': sl_price}
        exchange.create_order(symbol, 'STOP_MARKET', 'sell' if tipo == 'LONG' else 'buy', cantidad, None, params)

        params_tp = {'reduceOnly': True}
        exchange.create_order(symbol, 'TAKE_PROFIT_MARKET', 'sell' if tipo == 'LONG' else 'buy', cantidad, tp_price, params_tp)
    except Exception as e:
        print(f"⚠️ Error creando SL/TP para {symbol}: {e}")

    # Enviar mensaje a Telegram
    mensaje = (
        f"📊 {symbol} | {tipo}\n"
        f"💰 Entrada: {precio} | Cantidad: {cantidad}\n"
        f"⛔ SL: {sl_price} | 🎯 TP: {tp_price}\n"
        f"🔹 Posición abierta x{APALANCAMIENTO}\n"
        f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    bot.send_message(chat_id=CHAT_ID, text=mensaje)

    return order

# ==============================
# LOOP PRINCIPAL
# ==============================
while True:
    seleccion = random.sample(SYMBOLS, 30)  # analiza 30 al azar de las 40
    for symbol in seleccion:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe=random.choice(TIMEFRAMES), limit=150)
            if not ohlcv:
                continue

            df = pd.DataFrame(ohlcv, columns=['timestamp','open','high','low','close','volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df = calcular_indicadores(df)

            señal = generar_senal(df, symbol)
            if señal and f"{señal['symbol']}_{señal['tipo']}" not in ultimas_senales:
                ultimas_senales.add(f"{señal['symbol']}_{señal['tipo']}")
                abrir_posicion(señal)

        except Exception as e:
            # Solo log interno
            print(f"❌ Error en {symbol}: {e}")

    time.sleep(INTERVALO_HORAS * 3600)

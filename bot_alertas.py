import ccxt
import pandas as pd
import ta
import os
import time
from datetime import datetime
from telegram import Bot

# ==============================
# CONFIGURACIÓN
# ==============================
API_KEY_TELEGRAM = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
BINANCE_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET = os.getenv("BINANCE_API_SECRET")

if not API_KEY_TELEGRAM or not CHAT_ID or not BINANCE_KEY or not BINANCE_SECRET:
    print("❌ ERROR: Variables de entorno no configuradas.")
    exit(1)

bot = Bot(token=API_KEY_TELEGRAM)

exchange = ccxt.binance({
    'apiKey': BINANCE_KEY,
    'secret': BINANCE_SECRET,
    'enableRateLimit': True,
    'options': {'defaultType': 'future'}  # FUTUROS
})

# Configuración de trading
USDT_AMOUNT = 20          # Tamaño de posición
STOP_LOSS_USD = 3
TAKE_PROFIT_USD = 5
LEVERAGE = 10
SYMBOLS = ["BTC/USDT","ETH/USDT","BNB/USDT","XRP/USDT"]
TIMEFRAMES = ['1h', '4h']

# Configura apalancamiento
for sym in SYMBOLS:
    try:
        market = sym.replace("/", "")
        exchange.fapiPrivate_post_leverage({'symbol': market, 'leverage': LEVERAGE})
    except Exception as e:
        print(f"⚠️ No se pudo setear leverage para {sym}: {e}")

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
        "precio": float(precio_actual)
    }

# ==============================
# FUNCIONES DE TRADING
# ==============================
def abrir_operacion(señal):
    symbol = señal['symbol']
    precio = señal['precio']
    tipo = señal['tipo']
    market = symbol.replace("/", "")

    # Verificar balance antes de operar
    balance = exchange.fetch_balance()
    usdt_disp = balance['total'].get('USDT', 0)

    # Margen necesario
    margen_requerido = USDT_AMOUNT / LEVERAGE

    # Cantidad de coin según USDT_AMOUNT
    qty = round(USDT_AMOUNT / precio, 3)

    # Definir SL y TP
    if tipo == "LONG":
        sl_price = round(precio - STOP_LOSS_USD / qty, 2)
        tp_price = round(precio + TAKE_PROFIT_USD / qty, 2)
        side = "buy"
        close_side = "sell"
    else:
        sl_price = round(precio + STOP_LOSS_USD / qty, 2)
        tp_price = round(precio - TAKE_PROFIT_USD / qty, 2)
        side = "sell"
        close_side = "buy"

    # Si no hay saldo suficiente, enviar alerta de señal potencial
    if usdt_disp < margen_requerido:
        mensaje = (f"⚠️ Señal detectada pero SIN saldo suficiente\n"
                   f"{tipo} en {symbol} ({señal['tf']})\n"
                   f"💰 Precio: {precio}\n"
                   f"⛔ SL: {sl_price} | 🎯 TP: {tp_price}\n"
                   f"💵 Balance disponible: {usdt_disp:.2f} USDT")
        print(mensaje)
        bot.send_message(chat_id=CHAT_ID, text=mensaje)
        return

    try:
        # Orden Market principal
        order = exchange.create_market_order(symbol, side, qty)

        # SL
        exchange.create_order(
            symbol, 'STOP_MARKET', 
            close_side, qty, None, {'stopPrice': sl_price}
        )

        # TP
        exchange.create_order(
            symbol, 'TAKE_PROFIT_MARKET', 
            close_side, qty, None, {'stopPrice': tp_price}
        )

        mensaje = (f"🚀 Operación {tipo} abierta en {symbol}\n"
                   f"💰 Entrada: {precio}\n"
                   f"⛔ SL: {sl_price} | 🎯 TP: {tp_price}\n"
                   f"📈 Cantidad: {qty} ({USDT_AMOUNT} USDT apalancado x{LEVERAGE})\n"
                   f"💵 Balance usado: {margen_requerido:.2f} USDT")
        print(mensaje)
        bot.send_message(chat_id=CHAT_ID, text=mensaje)

    except Exception as e:
        mensaje = f"❌ Error abriendo operación {symbol}: {e}"
        print(mensaje)
        bot.send_message(chat_id=CHAT_ID, text=mensaje)

# ==============================
# LOOP PRINCIPAL
# ==============================
if __name__ == "__main__":
    while True:
        print(f"🔹 Iniciando análisis {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        for symbol in SYMBOLS:
            try:
                for tf in TIMEFRAMES:
                    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=tf, limit=150)
                    df = pd.DataFrame(ohlcv, columns=['timestamp','open','high','low','close','volume'])
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                    df = calcular_indicadores(df)
                    señal = generar_senal(df, symbol, tf)
                    if señal:
                        abrir_operacion(señal)
            except Exception as e:
                print(f"❌ Error analizando {symbol}: {e}")

        print("⏳ Esperando 1 hora para el próximo análisis...")
        time.sleep(3600)

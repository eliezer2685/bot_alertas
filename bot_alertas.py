import os
import time
import requests
import pandas as pd
import numpy as np
import schedule
from datetime import datetime, timedelta
from binance.client import Client
from binance.exceptions import BinanceAPIException
from textblob import TextBlob
from telegram import Bot

# ======================
# CONFIGURACIÓN
# ======================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

bot = Bot(token=TELEGRAM_TOKEN)

COOLDOWN_ALERTA = 3  # horas sin repetir alerta por moneda
UMBRAL_ALERTA = 70  # probabilidad mínima
MAX_ALERTAS_HORA = 10

# ======================
# INICIALIZACIÓN BINANCE (SPOT)
# ======================
client = Client()  # sin API key para spot público

# Lista de monedas a analizar
MONEDAS = [
    'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 'ADAUSDT',
    'DOGEUSDT', 'MATICUSDT', 'DOTUSDT', 'LTCUSDT', 'TRXUSDT', 'LINKUSDT',
    'AVAXUSDT', 'ATOMUSDT', 'XMRUSDT', 'ALGOUSDT', 'ICPUSDT', 'FILUSDT',
    'SANDUSDT', 'AXSUSDT', 'THETAUSDT', 'EGLDUSDT', 'VETUSDT', 'FTMUSDT',
    'GALAUSDT', 'APEUSDT', 'NEARUSDT', 'FLOWUSDT', 'CHZUSDT', 'HBARUSDT',
    'QNTUSDT', 'CRVUSDT', 'RUNEUSDT', 'MANAUSDT', '1INCHUSDT', 'AAVEUSDT',
    'KAVAUSDT', 'GMXUSDT', 'RNDRUSDT', 'BLURUSDT', 'SUIUSDT', 'PYTHUSDT',
    'JTOUSDT', 'OCEANUSDT', 'ARUSDT', 'OPUSDT', 'LDOUSDT', 'INJUSDT',
    'DYDXUSDT', 'COMPUSDT', 'PEPEUSDT', 'BONKUSDT', 'SEIUSDT', 'TIAUSDT',
    'WIFUSDT', 'TURBOUSDT', 'FLOKIUSDT', 'SHIBUSDT', 'UNIUSDT', 'ENSUSDT'
]

# Almacena último timestamp de alerta para cooldown
ultimo_alerta = {m: datetime.min for m in MONEDAS}

# ======================
# FUNCIONES DE INDICADORES
# ======================
def obtener_velas(symbol, interval='15m', limit=200):
    klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    df = pd.DataFrame(klines, columns=[
        'timestamp','open','high','low','close','volume',
        'close_time','qav','trades','tbbav','tbqav','ignore'
    ])
    df['close'] = df['close'].astype(float)
    df['volume'] = df['volume'].astype(float)
    return df

def calcular_indicadores(df):
    df['ema9'] = df['close'].ewm(span=9).mean()
    df['ema21'] = df['close'].ewm(span=21).mean()
    df['ema50'] = df['close'].ewm(span=50).mean()

    df['rsi'] = calcular_rsi(df['close'], 14)
    df['macd'], df['macd_signal'] = calcular_macd(df['close'])
    return df

def calcular_rsi(series, period=14):
    delta = series.diff()
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = pd.Series(gain).rolling(period).mean()
    avg_loss = pd.Series(loss).rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calcular_macd(series, short=12, long=26, signal=9):
    ema_short = series.ewm(span=short).mean()
    ema_long = series.ewm(span=long).mean()
    macd = ema_short - ema_long
    signal_line = macd.ewm(span=signal).mean()
    return macd, signal_line

# ======================
# ESTRATEGIAS
# ======================
def estrategia_ema_macd_rsi(df):
    c = df.iloc[-1]
    if c['ema9'] > c['ema21'] > c['ema50'] and c['macd'] > c['macd_signal'] and c['rsi'] > 50:
        return 'LONG', 70
    elif c['ema9'] < c['ema21'] < c['ema50'] and c['macd'] < c['macd_signal'] and c['rsi'] < 50:
        return 'SHORT', 70
    return None, 0

def estrategia_volumen(df):
    c = df.iloc[-1]
    vol_medio = df['volume'].iloc[-20:].mean()
    if c['volume'] > vol_medio*2:
        return 'BREAKOUT', 60
    return None, 0

def estrategia_breakout(df):
    c = df.iloc[-1]
    if c['close'] > df['close'].max() * 0.995:
        return 'LONG', 65
    if c['close'] < df['close'].min() * 1.005:
        return 'SHORT', 65
    return None, 0

def estrategia_noticias(symbol):
    # Noticias mock (a integrar con API real tipo CryptoPanic o NewsAPI)
    try:
        url = f"https://cryptopanic.com/api/v1/posts/?auth_token={os.getenv('CRYPTO_TOKEN')}&currencies={symbol[:-4].lower()}"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            news = resp.json().get('results', [])
            score = 0
            for n in news[:5]:
                polarity = TextBlob(n['title']).sentiment.polarity
                score += polarity
            if score > 0.5: return 15
            if score < -0.5: return 15
    except:
        pass
    return 0

# ======================
# ENVÍO DE ALERTAS
# ======================
def enviar_alerta(symbol, direccion, prob, precio):
    tp = round(precio * 1.02, 4)
    sl = round(precio * 0.98, 4)
    msg = (f"🚨 Alerta {direccion} {symbol}\n"
           f"Probabilidad: {prob}%\n"
           f"Precio: {precio}\n"
           f"TP: {tp} | SL: {sl}\n"
           f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)

# ======================
# LOOP PRINCIPAL
# ======================
def analizar_moneda(symbol):
    global ultimo_alerta

    df = obtener_velas(symbol)
    df = calcular_indicadores(df)
    precio_actual = df['close'].iloc[-1]

    dir1, p1 = estrategia_ema_macd_rsi(df)
    dir2, p2 = estrategia_volumen(df)
    dir3, p3 = estrategia_breakout(df)
    p4 = estrategia_noticias(symbol)

    # Combinar probabilidades
    direcciones = [d for d in [dir1, dir2, dir3] if d]
    if not direcciones:
        return None

    probabilidad = p1 + p2 + p3 + p4
    probabilidad = min(probabilidad, 100)
    direccion_final = direcciones[0]  # prioridad a la primera que detecta tendencia

    # Filtro por probabilidad y cooldown
    if probabilidad >= UMBRAL_ALERTA:
        if datetime.now() - ultimo_alerta[symbol] > timedelta(hours=COOLDOWN_ALERTA):
            ultimo_alerta[symbol] = datetime.now()
            return (symbol, direccion_final, probabilidad, precio_actual)
    return None

def enviar_resumen():
    bot.send_message(chat_id=TELEGRAM_CHAT_ID,
                     text=f"✅ Bot activo {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.\nMonedas analizadas: {len(MONEDAS)}")

def ciclo_completo():
    alertas = []
    for symbol in MONEDAS:
        try:
            alerta = analizar_moneda(symbol)
            if alerta:
                alertas.append(alerta)
        except Exception as e:
            print(f"Error {symbol}: {e}")

    # Ordenar por mayor probabilidad y limitar
    alertas.sort(key=lambda x: x[2], reverse=True)
    alertas = alertas[:MAX_ALERTAS_HORA]

    for a in alertas:
        enviar_alerta(*a)

# ======================
# SCHEDULER
# ======================
schedule.every(30).minutes.do(ciclo_completo)
schedule.every().hour.do(enviar_resumen)

bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="🤖 Bot de alertas iniciado correctamente.")

while True:
    schedule.run_pending()
    time.sleep(1)

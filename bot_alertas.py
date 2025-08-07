import os, time, datetime, requests, json, feedparser, schedule, csv
import pandas as pd
import numpy as np
import ta
from textblob import TextBlob
from telegram import Bot
from binance.client import Client

# === Variables de entorno ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")

# Binance Client solo para Spot
client = Client()

bot = Bot(token=TELEGRAM_TOKEN)

# === Archivos ===
CSV_FILE = "historico_senales.csv"
COINS_FILE = "last_coins.json"

# Crear CSV si no existe
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Fecha", "Moneda", "Señal", "Precio Entrada", "TP", "SL", "Noticia", "Probabilidad"])

# === Configuración ===
ALL_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "SOLUSDT", "DOGEUSDT", "ADAUSDT", "TRXUSDT", "MATICUSDT", "LTCUSDT",
    "DOTUSDT", "SHIBUSDT", "AVAXUSDT", "UNIUSDT", "ATOMUSDT", "LINKUSDT", "XLMUSDT", "FILUSDT", "ICPUSDT", "APTUSDT",
    "ARBUSDT", "SANDUSDT", "MANAUSDT", "APEUSDT", "AXSUSDT", "NEARUSDT", "EOSUSDT", "FLOWUSDT", "XTZUSDT", "THETAUSDT",
    "AAVEUSDT", "GRTUSDT", "RUNEUSDT", "KAVAUSDT", "CRVUSDT", "FTMUSDT", "CHZUSDT", "SNXUSDT", "LDOUSDT", "OPUSDT",
    "COMPUSDT", "DYDXUSDT", "BLURUSDT", "RNDRUSDT", "GMTUSDT", "1INCHUSDT", "OCEANUSDT", "SUIUSDT", "PYTHUSDT", "JTOUSDT",
    "PEPEUSDT", "TIAUSDT", "BONKUSDT", "ORDIUSDT", "ENJUSDT", "STXUSDT", "SKLUSDT", "CFXUSDT", "GALUSDT", "AGIXUSDT"
]

ANALYSIS_INTERVAL = "15m"
ALERT_THRESHOLD = 70
MAX_ALERTS_PER_HOUR = 10
LAST_ALERTS = {}

# === RSS ===
news_feeds = [
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
    "https://news.bitcoin.com/feed/",
    "https://cryptoslate.com/feed/",
    "https://decrypt.co/feed",
    "https://bitcoinmagazine.com/feed",
    "https://u.today/rss",
    "https://ambcrypto.com/feed/",
    "https://cryptopotato.com/feed/",
    "https://beincrypto.com/feed/"
]

# === Función de Noticias ===
def check_news(symbol):
    keyword = symbol.replace("USDT", "")
    for feed in news_feeds:
        d = feedparser.parse(feed)
        for entry in d.entries[:5]:
            title = entry.title
            if keyword.lower() in title.lower():
                sentiment = TextBlob(title).sentiment.polarity
                if sentiment > 0.1:
                    return f"🟢 Noticia positiva: {title}"
                elif sentiment < -0.1:
                    return f"🔴 Noticia negativa: {title}"
    return None

# === Indicadores Técnicos ===
def get_indicators(symbol):
    try:
        klines = client.get_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_15MINUTE, limit=100)
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'number_of_trades',
            'taker_buy_base', 'taker_buy_quote', 'ignore'])

        df['close'] = pd.to_numeric(df['close'])
        df['volume'] = pd.to_numeric(df['volume'])

        df['rsi'] = ta.momentum.RSIIndicator(close=df['close'], window=14).rsi()
        ema_50 = ta.trend.EMAIndicator(close=df['close'], window=50).ema_indicator()
        ema_200 = ta.trend.EMAIndicator(close=df['close'], window=200).ema_indicator()
        macd = ta.trend.MACD(close=df['close'])
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()

        latest = df.iloc[-1]
        return {
            'price': latest['close'],
            'rsi': latest['rsi'],
            'ema50': ema_50.iloc[-1],
            'ema200': ema_200.iloc[-1],
            'macd': latest['macd'],
            'macd_signal': latest['macd_signal'],
            'volume': latest['volume']
        }
    except Exception as e:
        print(f"❌ Error al obtener velas para {symbol}: {e}")
        return None

# === Estrategias ===
def apply_strategies(symbol, indicators):
    strategies = []
    if indicators['rsi'] < 30 and indicators['macd'] > indicators['macd_signal'] and indicators['ema50'] > indicators['ema200']:
        strategies.append("Técnica (RSI+MACD+EMA)")
    if indicators['volume'] > 0:
        strategies.append("Volumen")
    news = check_news(symbol)
    if news:
        strategies.append("Noticia")
    if indicators['macd'] > 0 and indicators['ema50'] > indicators['ema200']:
        strategies.append("Momentum")

    prob = min(100, len(strategies) * 25)
    direction = "LONG" if indicators['macd'] > indicators['macd_signal'] else "SHORT"
    return prob, direction, strategies, news

# === Selección de Top10 ===
def select_top10():
    top = []
    for sym in ALL_SYMBOLS:
        indicators = get_indicators(sym)
        if not indicators:
            continue
        prob, direction, strategies, news = apply_strategies(sym, indicators)
        if prob >= ALERT_THRESHOLD:
            top.append((sym, prob))
    top.sort(key=lambda x: x[1], reverse=True)
    top10 = [x[0] for x in top[:10]]
    with open(COINS_FILE, 'w') as f:
        json.dump(top10, f)
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"✅ Top10 generado: {top10}")

# === Cargar monedas ===
def load_selected_coins():
    if not os.path.exists(COINS_FILE):
        return []
    with open(COINS_FILE) as f:
        return json.load(f)

# === Análisis de monedas ===
def analyze_intraday():
    global LAST_ALERTS
    coins = load_selected_coins()
    if not coins:
        print("⚠️ No hay monedas para analizar")
        return

    count = 0
    for symbol in coins:
        indicators = get_indicators(symbol)
        if not indicators:
            continue
        prob, direction, strategies, news = apply_strategies(symbol, indicators)
        if prob < ALERT_THRESHOLD:
            continue

        today = datetime.datetime.now().strftime('%Y-%m-%d')
        key = f"{symbol}-{today}"
        if key in LAST_ALERTS:
            continue

        tp = round(indicators['price'] * (1.02 if direction == "LONG" else 0.98), 6)
        sl = round(indicators['price'] * (0.98 if direction == "LONG" else 1.02), 6)

        msg = (
            f"📢 Señal Confirmada\n"
            f"Moneda: {symbol}\n"
            f"Dirección: {direction}\n"
            f"Precio entrada: {indicators['price']}\n"
            f"TP: {tp}\n"
            f"SL: {sl}\n"
            f"Probabilidad: {prob}%\n"
            f"Estrategias: {', '.join(strategies)}\n"
        )
        if news:
            msg += f"📰 {news}"

        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
        LAST_ALERTS[key] = True

        with open(CSV_FILE, mode='a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([datetime.datetime.now(), symbol, direction, indicators['price'], tp, sl, news if news else "", prob])

        count += 1
        if count >= MAX_ALERTS_PER_HOUR:
            break

# === Heartbeat ===
def hourly_summary():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = f"📊 Bot funcionando correctamente - Último resumen {now}"
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)

# === Lógica de fallback ===
def ensure_top10():
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    if not os.path.exists(COINS_FILE):
        print("📌 No existe top10. Generando...")
        select_top10()
        return
    with open(COINS_FILE) as f:
        try:
            coins = json.load(f)
            if not coins:
                print("📌 Top10 vacío. Regenerando...")
                select_top10()
        except:
            select_top10()

# === Scheduler ===
schedule.every().day.at("06:00").do(select_top10)
schedule.every().hour.do(ensure_top10)
schedule.every(15).minutes.do(analyze_intraday)
schedule.every().hour.at(":00").do(hourly_summary)

# === Inicio ===
bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="🚀 Bot iniciado y funcionando...")
print("✅ Bot activo. Esperando tareas...")

while True:
    schedule.run_pending()
    time.sleep(1)

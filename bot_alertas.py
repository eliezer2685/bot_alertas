import os, time, datetime, csv
import pandas as pd
import ta
import schedule
from binance.client import Client
from telegram import Bot

# 🔹 Variables de entorno para Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")

if not all([TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
    print("❌ ERROR: Variables de entorno no configuradas.")
    exit()

bot = Bot(token=TELEGRAM_TOKEN)

# 🔹 CSV para histórico
CSV_FILE = "historico_senales.csv"
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Fecha", "Moneda", "Señal", "Precio Entrada", "TP", "SL"])

# 🔹 Cliente Binance (solo SPOT, sin API key)
client = Client()  # para spot público no se necesita key

# 🔹 Lista de monedas a analizar (podés ampliarla)
symbols = [
    "BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","SOLUSDT","DOGEUSDT","ADAUSDT","TRXUSDT","MATICUSDT","LTCUSDT",
    "DOTUSDT","SHIBUSDT","AVAXUSDT","UNIUSDT","ATOMUSDT","LINKUSDT","XLMUSDT","FILUSDT","ICPUSDT","APTUSDT",
    "ARBUSDT","SANDUSDT","MANAUSDT","APEUSDT","AXSUSDT","NEARUSDT","EOSUSDT","FLOWUSDT","XTZUSDT","THETAUSDT",
    "AAVEUSDT","GRTUSDT","RUNEUSDT","KAVAUSDT","CRVUSDT","FTMUSDT","CHZUSDT","SNXUSDT","LDOUSDT","OPUSDT",
    "COMPUSDT","DYDXUSDT","BLURUSDT","RNDRUSDT","GMTUSDT","1INCHUSDT","OCEANUSDT","SUIUSDT","PYTHUSDT","JTOUSDT"
]

# 🔹 Estrategia técnica
def analyze_market():
    for symbol in symbols:
        try:
            klines = client.get_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_15MINUTE, limit=200)
            closes = [float(k[4]) for k in klines]
            df = pd.DataFrame(closes, columns=["close"])
            
            # RSI y EMAs
            df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
            df["ema50"] = ta.trend.EMAIndicator(df["close"], window=50).ema_indicator()
            df["ema200"] = ta.trend.EMAIndicator(df["close"], window=200).ema_indicator()
            
            # MACD
            macd_indicator = ta.trend.MACD(df["close"])
            df["macd"] = macd_indicator.macd()
            df["macd_signal"] = macd_indicator.macd_signal()

            last = df.iloc[-1]
            price = last["close"]
            rsi = last["rsi"]
            macd = last["macd"]
            macd_signal = last["macd_signal"]
            ema50 = last["ema50"]
            ema200 = last["ema200"]

            # Señal LONG o SHORT
            signal = None
            if rsi < 30 and macd > macd_signal and ema50 > ema200:
                signal = "LONG"
            elif rsi > 70 and macd < macd_signal and ema50 < ema200:
                signal = "SHORT"

            if signal:
                tp = round(price * (1.02 if signal == "LONG" else 0.98), 6)
                sl = round(price * (0.98 if signal == "LONG" else 1.02), 6)

                msg = (
                    f"🔔 Señal Detectada\n"
                    f"Moneda: {symbol}\n"
                    f"Tipo: {signal}\n"
                    f"Entrada: {price}\n"
                    f"TP: {tp}\n"
                    f"SL: {sl}\n"
                    f"Apalancamiento sugerido: x10\n"
                )
                bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
                print(f"📤 Señal enviada: {symbol} {signal}")

                with open(CSV_FILE, mode='a', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([datetime.datetime.now(), symbol, signal, price, tp, sl])

        except Exception as e:
            print(f"⚠️ Error analizando {symbol}: {e}")

# 🔹 Heartbeat cada 1 hora
def heartbeat():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"✅ Bot activo - {now}")

# 🔹 Scheduler
schedule.every(15).minutes.do(analyze_market)
schedule.every().hour.do(heartbeat)

# 🔹 Aviso inicial
bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="🚀 Bot de alertas Binance Spot iniciado correctamente...")

print("✅ Bot iniciado. Analiza cada 15 minutos y heartbeat cada 1 hora...")
while True:
    schedule.run_pending()
    time.sleep(1)

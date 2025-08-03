import os, time, datetime, feedparser, requests, ccxt, pandas as pd, ta, schedule
from textblob import TextBlob
import random

# ==== CONFIGURACIÓN ====
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")

if not all([API_KEY, API_SECRET, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
    print("❌ ERROR: Variables de entorno no configuradas.")
    exit()

# Inicializar Binance en modo lectura de futuros
binance = ccxt.binance({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'enableRateLimit': True,
    'options': {'defaultType': 'future'}
})

# Lista de 40 monedas para análisis
coins = [
    "BTC/USDT","ETH/USDT","BNB/USDT","SOL/USDT","XRP/USDT","DOGE/USDT","ADA/USDT","MATIC/USDT","DOT/USDT","LTC/USDT",
    "TRX/USDT","SHIB/USDT","AVAX/USDT","UNI/USDT","XMR/USDT","ATOM/USDT","ETC/USDT","ICP/USDT","FIL/USDT","HBAR/USDT",
    "APT/USDT","ARB/USDT","QNT/USDT","VET/USDT","ALGO/USDT","GRT/USDT","EOS/USDT","SAND/USDT","AAVE/USDT","MANA/USDT",
    "FLOW/USDT","XTZ/USDT","THETA/USDT","KAVA/USDT","ZEC/USDT","RUNE/USDT","STX/USDT","NEAR/USDT","CHZ/USDT","OP/USDT"
]

# ==== Funciones ====
def enviar_telegram(mensaje):
    """Envía mensajes a Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    params = {"chat_id": TELEGRAM_CHAT_ID, "text": mensaje}
    try:
        requests.get(url, params=params)
    except Exception as e:
        print(f"❌ Error enviando mensaje: {e}")

def alerta_prueba():
    """Envía una alerta de prueba cada 3 horas"""
    mensaje = "🚀 ALERTA DE PRUEBA: Sistema funcionando correctamente.\nPróxima señal real cuando se detecte una estrategia válida."
    enviar_telegram(mensaje)
    print("✅ Alerta de prueba enviada.")

def analizar_noticias():
    """Simulación de análisis de noticias para ejemplo."""
    periodicos = [
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://cointelegraph.com/rss",
        "https://www.newsbtc.com/feed/",
    ]
    for rss in periodicos:
        feed = feedparser.parse(rss)
        for entrada in feed.entries[:5]:
            sentimiento = TextBlob(entrada.title).sentiment.polarity
            if sentimiento > 0.2:
                enviar_telegram(f"🟢 Noticia positiva: {entrada.title}")
            elif sentimiento < -0.2:
                enviar_telegram(f"🔴 Noticia negativa: {entrada.title}")

# ==== Inicio del bot ====
if __name__ == "__main__":
    enviar_telegram("🤖 Bot de alertas iniciado correctamente. Enviará alertas de prueba cada 3 horas.")
    print("✅ Bot iniciado. Enviando alertas cada 3 horas...")

    # Programar tareas
    schedule.every(3).hours.do(alerta_prueba)
    schedule.every(6).hours.do(analizar_noticias)

    while True:
        schedule.run_pending()
        time.sleep(60)

import ccxt
import os
import requests

# ===== Variables de entorno =====
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")

def send_telegram(msg):
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})

# ===== Verificación de variables =====
if not all([API_KEY, API_SECRET, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
    print("❌ ERROR: Variables de entorno no configuradas.")
    send_telegram("❌ ERROR: Variables de entorno no configuradas.")
    exit()

# ===== Conexión a Binance Futuros =====
binance = ccxt.binance({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'enableRateLimit': True,
    'options': {'defaultType': 'future'}
})

try:
    balance = binance.fetch_balance()
    futures_balance = balance.get('total', {})
    print("✅ Conexión exitosa a Binance Futuros")
    print("💰 Balances:", futures_balance)
    send_telegram(f"✅ Bot conectado a Binance Futuros.\nBalance: {futures_balance}")
    
except ccxt.BaseError as e:
    print(f"❌ Error de conexión: {str(e)}")
    send_telegram(f"❌ Error de conexión a Binance Futuros:\n{str(e)}")

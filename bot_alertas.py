import os, time, datetime, feedparser, requests, ccxt, pandas as pd, ta
from textblob import TextBlob
import random

# === Configuración ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
if not all([TELEGRAM_TOKEN, CHAT_ID, API_KEY, API_SECRET]):
    print("❌ Variables de entorno faltantes")
    exit()

exchange = ccxt.binance({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'enableRateLimit': True,
    'options': {'defaultType': 'future'}
})

RSS_FEEDS = [
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
    "https://decrypt.co/feed",
    "https://www.theblock.co/feed",
    "https://cryptonews.com/news/feed",
    "https://bitcoinmagazine.com/.rss/full/",
    "https://coinjournal.net/feed/",
    "https://www.investing.com/rss/news_301.rss",
    "https://coingape.com/feed/",
    "https://u.today/rss"
]

SYMBOLS = [
    'BTC/USDT','ETH/USDT','BNB/USDT','SOL/USDT','XRP/USDT','DOGE/USDT','ADA/USDT',
    'MATIC/USDT','DOT/USDT','AVAX/USDT','LTC/USDT','LINK/USDT','ATOM/USDT','NEAR/USDT',
    'FTM/USDT','APT/USDT','AAVE/USDT','SAND/USDT','MANA/USDT','FIL/USDT','THETA/USDT',
    'FLOW/USDT','EGLD/USDT','GALA/USDT','CHZ/USDT','VET/USDT','XLM/USDT','TRX/USDT',
    'UNI/USDT','ETC/USDT','EOS/USDT','ALGO/USDT','ICP/USDT','CFX/USDT','LDO/USDT',
    'DYDX/USDT','GRT/USDT','OP/USDT','ARB/USDT','STX/USDT','IMX/USDT'
]

CSV_FILE = "historial_senales.csv"
if not os.path.exists(CSV_FILE):
    pd.DataFrame(columns=['fecha','symbol','operacion','precio','tp','sl','apalancamiento','sentimiento']).to_csv(CSV_FILE, index=False)

# === Funciones ===

def enviar_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg})

def fetch_news():
    news = []
    for feed in RSS_FEEDS:
        try:
            f = feedparser.parse(feed)
            for entry in f.entries[:5]:
                news.append({'title': entry.get('title',''), 'summary': entry.get('summary','')})
        except: pass
    return news

def get_sentiment(text):
    p = TextBlob(text).sentiment.polarity
    return 'positive' if p>0.1 else ('negative' if p< -0.1 else 'neutral')

def technical_signal(symbol):
    df = pd.DataFrame(exchange.fetch_ohlcv(symbol, '1h', limit=200),
                      columns=['t','o','h','l','c','v'])
    df['c']=df['c'].astype(float)
    df['EMA50']=ta.trend.ema_indicator(df['c'],50)
    df['EMA200']=ta.trend.ema_indicator(df['c'],200)
    df['RSI']=ta.momentum.rsi(df['c'],14)
    df['MACD']=ta.trend.macd_diff(df['c'])
    last = df.iloc[-1]
    if last['EMA50']>last['EMA200'] and last['MACD']>0 and last['RSI']<70:
        return 'LONG'
    if last['EMA50']<last['EMA200'] and last['MACD']<0 and last['RSI']>30:
        return 'SHORT'
    return None

def process_cycle():
    news = fetch_news()
    sent_sent = []
    alerts = 0
    for symbol in SYMBOLS:
        if alerts>=3: break
        txt = " ".join([n['title']+" "+n['summary'] for n in news])
        sentiment = 'neutral'
        if symbol.split('/')[0] in txt:
            sentiment = get_sentiment(txt)
        sig = technical_signal(symbol)
        if sig and ((sig=='LONG' and sentiment=='positive') or (sig=='SHORT' and sentiment=='negative')):
            send_alert(symbol, sig, strong=True)
            alerts+=1
        elif sig and sentiment=='neutral' and random.random()>0.7:
            send_alert(symbol, sig, strong=False)
            alerts+=1

def send_alert(symbol, operation, strong):
    price = exchange.fetch_ticker(symbol)['last']
    tp = round(price*(1.02 if operation=='LONG' else 0.98),4)
    sl = round(price*(0.98 if operation=='LONG' else 1.02),4)
    lev = 'x5-x10' if strong else 'x3-x5'
    fecha = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    row = {'fecha':fecha,'symbol':symbol,'operacion':operation,'precio':price,'tp':tp,'sl':sl,'apalancamiento':lev,'sentimiento':'strong' if strong else 'tecnico'}
    pd.DataFrame([row]).to_csv(CSV_FILE, mode='a', header=False, index=False)
    enviar_telegram(f"""📊 Señal {operation} {symbol}
Entrada: {price}
TP: {tp} | SL: {sl}
Apalancamiento: {lev}
Fuente: {'noticia+técnico' if strong else 'solo técnico'}
""")

# === Loop principal ===

while True:
    hr = datetime.datetime.now().hour
    if 6 <= hr <= 22 and hr%3==0:
        process_cycle()
        print("✅ ciclo enviado", datetime.datetime.now())
        time.sleep(3*3600)
    else:
        time.sleep(600)

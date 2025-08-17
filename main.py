#!/usr/bin/env python3
"""
Binance 15m ±6% move alert bot -> Telegram
- Checks ALL USDT‑M perpetual symbols on Binance every minute.
- If the current 15m candle's absolute move (|close-open|/open*100) >= THRESHOLD, it sends one alert per symbol per candle.
- Free to run locally or on any free-tier host.
"""
import os
import asyncio
import aiohttp
import time
import math
import sqlite3
from contextlib import asynccontextmanager
from dotenv import load_dotenv

BINANCE_FAPI = "https://fapi.binance.com"
INTERVAL = os.getenv("INTERVAL", "15m")
THRESHOLD = float(os.getenv("THRESHOLD", "6"))
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "60"))
QUOTE = os.getenv("QUOTE", "USDT")  # USDT‑M futures
EXCLUDED = set(os.getenv("EXCLUDED", "").upper().split(",")) if os.getenv("EXCLUDED") else set()

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise SystemExit("Please set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in your environment or .env file.")

DB_PATH = os.getenv("DB_PATH", "alerts.db")

def db_init():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS alerts (
        symbol TEXT NOT NULL,
        open_time INTEGER NOT NULL,
        PRIMARY KEY(symbol, open_time)
    )""")
    con.commit()
    con.close()

def already_alerted(symbol: str, open_time: int) -> bool:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT 1 FROM alerts WHERE symbol=? AND open_time=?", (symbol, open_time))
    row = cur.fetchone()
    con.close()
    return row is not None

def mark_alerted(symbol: str, open_time: int) -> None:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("INSERT OR IGNORE INTO alerts(symbol, open_time) VALUES (?,?)", (symbol, open_time))
    con.commit()
    con.close()

@asynccontextmanager
async def session_ctx():
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        yield s

async def get_symbols(session: aiohttp.ClientSession):
    # USDT‑M futures exchange info
    url = f"{BINANCE_FAPI}/fapi/v1/exchangeInfo"
    async with session.get(url) as r:
        r.raise_for_status()
        data = await r.json()
    symbols = []
    for s in data.get("symbols", []):
        # Keep trading perpetuals quoted in selected QUOTE (default USDT)
        if s.get("status") != "TRADING":
            continue
        if s.get("contractType") != "PERPETUAL":
            continue
        if s.get("quoteAsset") != QUOTE:
            continue
        sym = s.get("symbol")
        if not sym or sym in EXCLUDED:
            continue
        symbols.append(sym)
    return symbols

async def get_latest_15m_kline(session: aiohttp.ClientSession, symbol: str):
    params = {"symbol": symbol, "interval": INTERVAL, "limit": 1}
    url = f"{BINANCE_FAPI}/fapi/v1/klines"
    for attempt in range(3):
        try:
            async with session.get(url, params=params) as r:
                if r.status in (418, 429, 451):  # rate limited or blocked
                    await asyncio.sleep(1 + attempt * 2)
                    continue
                r.raise_for_status()
                arr = await r.json()
                if not arr:
                    return None
                # Kline format: [ openTime, open, high, low, close, volume, closeTime, ... ]
                k = arr[0]
                return {
                    "open_time": int(k[0]),
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "close_time": int(k[6]),
                }
        except aiohttp.ClientError:
            await asyncio.sleep(1 + attempt * 2)
    return None

async def send_telegram(text: str):
    api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    # simple retry
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
        for attempt in range(3):
            try:
                async with s.post(api, data=payload) as r:
                    if r.status in (429, 500, 502, 503, 504):
                        await asyncio.sleep(1 + attempt * 2)
                        continue
                    r.raise_for_status()
                    return True
            except aiohttp.ClientError:
                await asyncio.sleep(1 + attempt * 2)
    return False

def fmt_pct(p):
    return f"{p:.2f}%"

def make_alert_text(symbol, k, pct):
    direction = "▲ UP" if k["close"] >= k["open"] else "▼ DOWN"
    return (
        f"<b>{symbol}</b> {direction}\n"
        f"Interval: {INTERVAL} | Move: <b>{fmt_pct(abs(pct))}</b>\n"
        f"Open: {k['open']:.6f} | Close: {k['close']:.6f}\n"
        f"High: {k['high']:.6f} | Low: {k['low']:.6f}\n"
        f"Open Time: {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(k['open_time']/1000))} UTC"
    )

async def check_once():
    db_init()
    async with session_ctx() as s:
        symbols = await get_symbols(s)
        # Concurrency with a cap to be polite with API weight
        sem = asyncio.Semaphore(50)
        alerts = []

        async def worker(sym):
            async with sem:
                k = await get_latest_15m_kline(s, sym)
            if not k:
                return
            pct = (k["close"] - k["open"]) / k["open"] * 100.0
            if abs(pct) >= THRESHOLD and not already_alerted(sym, k["open_time"]):
                text = make_alert_text(sym, k, pct)
                ok = await send_telegram(text)
                if ok:
                    mark_alerted(sym, k["open_time"])
                    alerts.append((sym, pct))

        await asyncio.gather(*(worker(sym) for sym in symbols))
        return alerts

async def main_loop():
    print(f"Starting watcher: interval={INTERVAL}, threshold={THRESHOLD}%, poll={POLL_SECONDS}s, quote={QUOTE}")
    while True:
        start = time.time()
        try:
            alerts = await check_once()
            if alerts:
                print(f"Sent {len(alerts)} alerts: " + ", ".join(f"{s}:{abs(p):.2f}%" for s,p in alerts))
            else:
                print("No new alerts this cycle.")
        except Exception as e:
            print("Error in cycle:", e)
        # sleep remaining time
        elapsed = time.time() - start
        await asyncio.sleep(max(0, POLL_SECONDS - elapsed))

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        print("Bye")

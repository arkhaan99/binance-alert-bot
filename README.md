# Binance 15m Move → Telegram Alerts (Free)

**Kya karta hai:** Har 1 minute me Binance USDT‑M perpetual pairs check karta hai. Jis symbol ka current 15‑minute candle `±6%` se zyada move kare, uska Telegram pe alert bhejta hai. Har candle per symbol **sirf ek** alert (spam nahi).

## 1) Requirements
- Python 3.10+
- A free Telegram bot (BotFather se banaye)
- Aapka chat ID (numeric)

## 2) Setup
```bash
cd binance_15m_move_alert_bot
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.sample .env
# .env me TELEGRAM_BOT_TOKEN aur TELEGRAM_CHAT_ID fill karein
```

**Chat ID kaise nikalein (simple way):**
1. Telegram me apne bot ko `/start` bhejein.
2. Browser me yeh open karein (bot token se):  
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`  
   Response me `message.chat.id` milega. (Agar private chat hai to wahi aapka chat id hai.)

## 3) Run
```bash
python main.py
```
Console me "Starting watcher..." dikhega, aur jab bhi koi 15m candle ±6% move hogi to alert aayega.

## 4) Env Options
`.env`:
- `THRESHOLD` (default `6`) – Percent move trigger.
- `INTERVAL` (default `15m`) – Binance interval (e.g., `1m`, `5m`, `15m`, `1h`).
- `POLL_SECONDS` (default `60`) – Kitni der me check karna.
- `QUOTE` (default `USDT`) – USDT‑M futures. (USDT hi rakhein.)
- `EXCLUDED` – Comma‑separated symbols to skip (e.g. `BTCUSDT,ETHUSDT`).
- `DB_PATH` – SQLite file to remember which candles already alerted.

## 5) Notes
- Ye script Binance **USDT‑M (fapi)** perpetuals ko check karta hai.
- API limits ko respect karne ke liye concurrency cap set hai.
- Agar app restart ho to duplicate alerts avoid karne ke liye SQLite DB use hoti hai.

## 6) Run Free
- Aap isay apne laptop/PC par free chala sakte hain (sabse asaan).
- Lightweight hai; Raspberry Pi ya kisi bhi low‑spec machine par bhi chalega.
- Cloud free tiers kabhi kabhi sleep karte hain; locally chalana sabse reliable free option hai.

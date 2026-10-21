# Eden Trader

Nifty / Sensex CPR Breakout calls on your phone: an Android app with **notifications**, the **live chart**, today's
**buy / sell calls**, and the **history** of every call with its success.

- **Calls** (the rules of `trading-system/alerts/cprb_alerts.py`, the research of this repository): the daily plan
  (CPR Magnet at 9:16 or the 9:30 breakout) and the 3-day volume lines; Nifty with yesterday's volume POC, Sensex
  with the volume check.
- **Notifications**: every call (entry with the strike, stop, book half, exit), the plan at 8:45 and the day's
  result after 3:30, also when the app is closed.
- **Targets T1 / T2 / T3**: **T1 = where the call books half**, as always (a volume-line call has one target: T1 is
  that target). T2 / T3, for reference only (the exits don't use them): the next two price levels beyond T1 (CPR,
  pivots R1-R3 / S1-S3, yesterday's high / low, the 15-minute range, the volume lines, the POC). In every call, on the
  chart and in the history, with how far each call went its way and against it. The trades themselves (entries,
  stop, book half, trail) are exactly the strategy's.
- **Options** (from 21 October 2026): the current expiry's option chain for Nifty and Sensex, live (prices, change,
  open interest and its change; the at-the-money strike in blue, the index price as an orange line, in-the-money
  sides shaded), and a live chart of any call or put you tap (1 / 3 / 5 minutes) with that option's own CPR and
  yesterday's high / low. Prices from Groww's public data every few seconds; the 1-minute candles from Upstox, the
  minute still forming from the live prices. Also at /options on the server (with the key).
  Laid out like Groww: chart and chain side by side on a wide screen, a short chart above the chain on a phone; the
  PCR, the call OI wall (resistance) and the put OI wall (support) above the chain, OI bars per strike, an "OI
  table" mode; tap the index price for the index chart with the CPR, pivots (R1 / S1 / R2 / S2) and the OI walls.
- **Trend / no reversal**: on the Calls screen and at the top of the chart, a red bar on a FALLING day (price below
  both the day's open and the CPR), green on a RISING day: "no sign of a reversal ... don't BUY / SELL against it",
  with how often such moments reversed in 2023-2026 (about 1 in 3 before 10:30, 1 in 4 to 12:30, 1 in 5 after).
- **History**: a call is a **success** when the index went at least **50 points (Nifty) / 150 points (Sensex)** its
  way before the stop loss. With the largest stop Nifty 55 / Sensex 170 points (from 17 October 2026), the 2026 calls
  to 9 October: Nifty 62 of 97 (64%), Sensex 60 of 85 (71%); 70% / 78% of them made money. 2023-2026: T1 (book half)
  reached on 80% of the Nifty and 77% of the Sensex breakouts, 82-83% of the Magnet calls.
  **Extra calls** (CPR break, open high low, gap fill, second chance) have their own cards and filter: one is a success when it reached its
  target (60 Nifty / 200 Sensex points) before its stop (35 / 100); above about 41% / 37% they make money. 2026 to 9
  October: Nifty 38 of 81 (47%), +636 points; Sensex 37 of 90 (41%), +1,366.

## Install the app

1. On the phone open **https://trade.munimo.online/app.apk** (or, before the server runs,
   https://github.com/CURIOUSMIND123/Edensniper/raw/claude/trading-cafe-strategy-analysis-jnh595/eden-trader/dist/eden-trader.apk).
2. Open the download and allow installing from this source (Android asks once).
3. Open Eden Trader > Settings: server `https://trade.munimo.online`, and the key you were given. Save.
4. Allow notifications, and allow it to run in the background when Android asks (or Settings > Apps > Eden Trader
   > Battery > **Unrestricted**). That's what keeps the notifications coming with the app closed.

## On a computer (web)

Open **https://trade.munimo.online/web/?key=YOUR-KEY** in any browser (Chrome, Edge, Safari). The same Chart, Calls
and History as the app; the browser remembers the key, so next time **https://trade.munimo.online/web/** is enough.
Notifications come only in the phone app. The chart alone: **https://trade.munimo.online/?key=YOUR-KEY**.

## How it runs

- **Server** (the Oracle server, next to Munimo, which it doesn't touch): `deploy/update.sh` runs every 2 minutes,
  from the Munimo updater (`erp-link/companions.sh` added to ne-construction-erp) or from `eden-trader-update.timer`
  (`deploy/bootstrap.sh`, one paste on the server). It pulls this branch to `/opt/eden-trader` and runs
  `deploy/install.sh` when something changed: the service `eden-trader` (user `eden`, data in `/var/lib/eden-trader`,
  settings in `/etc/eden-trader.env`) and the address `https://trade.munimo.online` in Caddy. During market hours a
  restart for new code waits for a safe moment (`deploy/tick.sh`): no trade open, not 9:10-10:05, 1-2 minutes after
  a 5-minute candle; the program goes through the day again within seconds and doesn't repeat an alert it sent.
- **App** (`app/`): Capacitor, like the Adidev app. Chart, Calls and History read the server's API (`/api/state`,
  `/api/events`, `/api/history`, `/data`; every request needs the key). A native foreground service
  (`app/native/java/.../TraderService.java`) checks `/api/events` every 10 seconds on weekdays 8:40-15:45 IST (every 5
  minutes otherwise) and shows each new alert as a notification. The built APK is `dist/eden-trader.apk`, which the
  server offers at `/app.apk`.
- **Live price**: the chart's last candle and price line move every second in market hours (Groww's public data), the
  price in Calls every 3 seconds, until the 1-minute candle arrives; the calls use the 1-minute candles only. Each
  trade is drawn like TradingView's long / short position tool (green to T1 / T3, red to the stop loss).
- **Over-the-air updates** (from 1.0.5, like the Adidev app): `app/www/boot.js` loads the screens (`app.js`,
  `style.css`, `index.html`) from the copy the server sends at `/app/ota.json` (this branch's `app/www`), or from the
  APK. The app checks when it opens and when it comes back to the front, and takes a new version at once; a version
  that fails to start is dropped and the built-in one used. A change to `app/www` needs only a push. The native
  service and `boot.js` need a new APK: build it with `BUILD_NUMBER` one higher, set the same number in `boot.js` and
  `dist/eden-trader.json`, run `node app/native/ota-ver.js`; the app then shows "A new version is ready".
- **Key**: only its SHA-256 is in this repository (`deploy/app-key.sha256`). To change the key, put the SHA-256 of a
  new one there and push.

## On the server (if ever needed)

| What | Command |
|---|---|
| Running? | `systemctl status eden-trader` |
| What it prints | `sudo journalctl -u eden-trader -f` |
| Updates | `sudo tail /var/log/munimo-companions.log` (Munimo link) or `sudo journalctl -u eden-trader-update` |
| Telegram as well (optional) | put `CPRB_TELEGRAM_TOKEN` / `CPRB_TELEGRAM_CHAT_ID` in `/etc/eden-trader.env`, `sudo systemctl restart eden-trader` |

Calls are the output of a backtested rule set chosen on 2026 data; they are not financial advice.

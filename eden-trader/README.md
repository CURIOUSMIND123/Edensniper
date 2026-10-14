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
- **History**: a call is a **success** when the index went at least **50 points (Nifty) / 150 points (Sensex)** its
  way before the stop loss. 2026 to 13 October: Nifty 68 of 95 calls (72%), Sensex 66 of 86 (77%). On average the
  Nifty calls went 112 points their way and 32 against; Sensex 395 and 96. 80% of the Nifty calls and 85% of the
  Sensex calls made money. T1 (book half) was reached on 91% of the Nifty and 98% of the Sensex breakout / Magnet
  calls; with the volume-line calls (T1 = their one target), T1 / T2 / T3 were reached on 60 / 39 / 23% of all Nifty
  calls and 72 / 45 / 28% of all Sensex calls.

## Install the app

1. On the phone open **https://trade.munimo.online/app.apk** (or, before the server runs,
   https://github.com/CURIOUSMIND123/Edensniper/raw/claude/trading-cafe-strategy-analysis-jnh595/eden-trader/dist/eden-trader.apk).
2. Open the download and allow installing from this source (Android asks once).
3. Open Eden Trader > Settings: server `https://trade.munimo.online`, and the key you were given. Save.
4. Allow notifications, and allow it to run in the background when Android asks (or Settings > Apps > Eden Trader
   > Battery > **Unrestricted**). That's what keeps the notifications coming with the app closed.

## How it runs

- **Server** (the Oracle server, next to Munimo, which it doesn't touch): `deploy/update.sh` runs every 2 minutes,
  from the Munimo updater (`erp-link/companions.sh` added to ne-construction-erp) or from `eden-trader-update.timer`
  (`deploy/bootstrap.sh`, one paste on the server). It pulls this branch to `/opt/eden-trader` and runs
  `deploy/install.sh` when something changed: the service `eden-trader` (user `eden`, data in `/var/lib/eden-trader`,
  settings in `/etc/eden-trader.env`) and the address `https://trade.munimo.online` in Caddy. During market hours a
  restart waits until 15:36 IST.
- **App** (`app/`): Capacitor, like the Adidev app. Chart, Calls and History read the server's API (`/api/state`,
  `/api/events`, `/api/history`, `/data`; every request needs the key). A native foreground service
  (`app/native/java/.../TraderService.java`) checks `/api/events` every 10 seconds on weekdays 8:40-15:45 IST (every 5
  minutes otherwise) and shows each new alert as a notification. The built APK is `dist/eden-trader.apk`, which the
  server offers at `/app.apk`.
- **Live price**: the chart's last candle and the price in Calls move every 2 seconds in market hours (Groww's public
  data), until the 1-minute candle arrives; the calls use the 1-minute candles only.
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

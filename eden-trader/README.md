# Eden Trader

Nifty / Sensex CPR Breakout calls on your phone: an Android app with **notifications**, the **live chart**, today's
**buy / sell calls**, and the **history** of every call with its success.

- **Calls** (the rules of `trading-system/alerts/cprb_alerts.py`, the research of this repository): the daily plan
  (CPR Magnet at 9:16 or the 9:30 breakout) and the 3-day volume lines; Nifty with yesterday's volume POC, Sensex
  with the volume check.
- **Notifications**: every call (entry with the strike, stop, book half, exit), the plan at 8:45 and the day's
  result after 3:30, also when the app is closed.
- **Targets T1 / T2 / T3** (for reference; the exits don't use them): the next three price levels ahead of the entry
  (CPR, pivots R1-R3 / S1-S3, yesterday's high / low, the 15-minute range, the volume lines, the POC), in every call,
  on the chart and in the history, with how far each call went its way and against it.
- **History**: a call is a **success** when the index went at least **50 points (Nifty) / 150 points (Sensex)** its
  way before the stop loss. 2026 to 13 October: Nifty 68 of 95 calls (72%), Sensex 66 of 86 (77%). On average the
  Nifty calls went 112 points their way and 32 against; Sensex 395 and 96. T1 / T2 / T3 were reached on 73 / 40 / 23%
  of the Nifty calls and 76 / 49 / 26% of the Sensex calls.

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

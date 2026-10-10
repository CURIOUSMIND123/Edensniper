# CPR Breakout alerts: live, free, without TradingView

Free TradingView accounts now show Nifty and Sensex 15 minutes late, and the live-data add-on costs over Rs 1,000 a
month. Brokers' charts (Groww, Dhan, Zerodha) show live prices for free but can't run our own indicator.

[`cprb_alerts.py`](cprb_alerts.py) follows the same rules as the indicator (`tradingview/cpr_breakout.pine`, its
default settings) on live 1-minute candles from Upstox's free public candle data. It doesn't need an Upstox account
or a login. It tells you:

- **before 9:15:** the plan for the day: CPR, narrow or not, the 30-day POC, the 3-day volume lines, the CPR Magnet
  trigger prices;
- **9:16:** CPR Magnet BUY / SELL, or "no magnet today";
- **9:30:** the 15-minute range and the one breakout trade that is still allowed: "SELL when price touches X". Set
  a price alert in Groww at X, so you aren't late;
- **every trade:** BUY = buy the ATM call, SELL = buy the ATM put, with the stop, when to book half, when to move
  the stop, and the exit with points and rupees.

Alerts appear on the screen (with a beep) and, if you set it up, on your phone through Telegram (free).

## Set up once

1. **Python.** On a laptop: install Python 3 from [python.org](https://www.python.org/downloads/). On Windows,
   tick "Add Python to PATH". On an Android phone: install **Pydroid 3** from the Play Store.
2. **The file.** Save `cprb_alerts.py` in a folder, for example `Documents\cprb`.
3. **Telegram (optional, for alerts on your phone):**
   1. In Telegram, open **@BotFather**, send `/newbot`, and pick a name. It replies with a token like
      `123456789:AAH...`.
   2. Open your new bot and send it any message, for example "hi".
   3. At the top of `cprb_alerts.py`, put the token between the quotes: `TELEGRAM_TOKEN = '123456789:AAH...'`.
   4. Run `python cprb_alerts.py --telegram-chat-id` (on a phone: just press Run). It prints your chat id, a
      number. Put it in `TELEGRAM_CHAT_ID = '...'`.
   5. Run `python cprb_alerts.py --telegram-test`. A test message should arrive on your phone. (On a phone, the
      "alerts started" message when you run it is the test.)
4. **Your lots.** Change `LOTS = 5` at the top if needed. It's used only for the rupee estimates (option moves are
   estimated at half the index move). `LADDER = True` switches on the volume-line ladder.

## Every trading day

Open a terminal in the folder (on Windows: in the folder's address bar type `cmd` and press Enter). Then run:

    python cprb_alerts.py

On a phone: open the file in Pydroid 3 and press the yellow Run button.

Start it any time before 9:15 and leave it running until 3:30. On a laptop, plug it in and stop it from sleeping.
On a phone, keep Pydroid open and the screen on. If you start late, it shows what already happened as
"[earlier today]" and alerts only new things.

To see how it works without waiting for the market, replay any past day in a few seconds:

    python cprb_alerts.py --replay 2026-10-08

On a phone, put the date in `REPLAY_DAY = '2026-10-08'` at the top and press Run (empty it again for live).
`python cprb_alerts.py --plan` prints only the next session's plan. `python cprb_alerts.py nifty` runs one index.

## Checked

`research/quant/alerts_check.py` runs it on every 2026 session, minute by minute as it runs live. It took exactly the
backtest's trades (Nifty 99 trades, net +2,454 points; Sensex 116 trades, net +7,894; with the ladder +2,373 /
+8,612). Nothing it had already said changed later in the day.

## Limits

- An alert comes when the 1-minute candle in which something happened has closed, plus a few seconds for the data.
  CPR Magnet (9:16) and volume-line trades (at a 5-minute close) are fine with that. For a breakout, use the 9:30
  message to set a price alert in Groww.
- The data is Upstox's public candle feed. It worked without a login when this was written. If Upstox changes it,
  the script will say "data error".
- It only sends alerts. You place the orders yourself in Groww.
- The rules were adjusted on 2026 itself, so live results will very likely be lower than the backtest.

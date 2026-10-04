# Fair Price playbook for Nifty and Sensex

This is JJ Simon's "fair pricing theory" from his Chart Fanatics interview
([video](https://youtu.be/KHEQ5g55dQ4)), turned into exact rules for the Nifty 50 and Sensex 1-minute chart.
He trades US Nasdaq futures on prop-firm accounts. The rules below keep his method and change only what has to
change for India: the session times and the point sizes.

What you get:

| Piece | What it does | Where |
|---|---|---|
| **Fair Price indicator** | Draws the fair price, prints BUY / SELL with stop and target lines, shows a plan table, sends alerts | [`tradingview/fair_price.pine`](tradingview/fair_price.pine) |
| **Fair Price Desk** (app) | Upload a chart screenshot. It reads the numbers and gives the trade, stop, target, strike, lots and rupee risk for your capital. It also keeps today's trade log. | [`app/fair-price-desk.html`](app/fair-price-desk.html) (also published as an artifact) |
| **Rules engine** | The same rules in Python, used for the test below | [`tci/fairprice.py`](tci/fairprice.py), tests in [`tests/test_fairprice.py`](tests/test_fairprice.py) |
| **Test trades** | Every trade from the test, with times and results | [`research/fair_price_backtest_1m.csv`](research/fair_price_backtest_1m.csv) |

![Fair Price on a real day](tradingview/fair-price-preview.png)

## Read this first

- **Nothing makes money every day.** In the test below, 6 of 19 days lost money on Nifty, and the first two days
  were both losing days. "Profitable from tomorrow" and "up every day" can't be promised by any method.
- **His profits come from prop firms.** He pays about $100 per evaluation and loses only that when an account
  fails (he says about 91% of evaluations end with nothing). He trades about 45 accounts at once. He says the
  fixed targets are tuned for prop-firm rules, and that a live account needs a more discretionary version. With
  ₹30k of your own money, every loss is real.
- **The test is short.** 19 days of 1-minute data is all that's available. The same rules on 5-minute candles over
  59 days lost money. Treat the 1-minute result as encouraging, not proven.
- SEBI's studies found that about 9 in 10 individual F&O traders lose money. **Paper-trade for 2 to 4 weeks**
  (mark trades in the app without placing them), then trade one lot.

## The rules

Everything is on the **1-minute chart**. Every signal waits for the candle to **close**.

1. **Fair price** = the 9:15 opening price. The rush of orders at the open pushes price away from it ("an unfair
   move"), and price tends to come back within the first 90 minutes.
2. **Bias** = the opposite of the last session. If today opened **above** yesterday's 9:15 open, the bias is
   **shorts**. If it opened **below**, the bias is **longs**. (He inverts "the previous 6 to 12 hours".)
3. **Trade 1, the opening candle.** When the 9:15 candle closes, trade in its colour (green = buy, red = sell),
   only if that matches the bias. If the candle is bigger than the stop, double the stop and target and halve
   the size. On Nifty the first minute was bigger than 20 points on every test day, so this trade is normally
   **40 / 60 points** (Sensex 120 / 180).
4. **After that, only trade back toward the fair price.** Wait until price is at least 80% of the target away from
   it (24 Nifty points, 72 Sensex points). Then enter on a **break of structure** toward the fair price:
   - buy when a candle closes above the latest swing high (a candle whose high is above the candle on each side);
   - sell when a candle closes below the latest swing low.

   He calls this "the stronger entry". It's the only one he uses on his own live account.
5. **Displacement entries are off.** A displacement candle has a bigger body than the previous candle, closes
   beyond the previous candle's wick, and the previous candle was the opposite colour. He uses these to fill
   many evaluation accounts. They lost money in the test, so they're off in the indicator; you can switch them on.
6. **Fixed stop and target, 1 : 1.5.** **Nifty 20 / 30 points, Sensex 60 / 90.** He doesn't move the stop and
   doesn't exit early.
7. **New trades only 9:15 to 10:45** (his "first 90 minutes"). A trade still open keeps its stop and target. Close
   anything still open at 3:15.
8. **Stop for the day after 2 losses in a row.** His rule is 3. With ₹30k, use 2: it changed nothing in the test
   and it caps a bad day.
9. **One trade at a time.**

### How his numbers became Nifty and Sensex numbers

His points are Nasdaq futures points. Over the same 59 days, the median range of the first 90 minutes was
233.5 points on Nasdaq, 97 on Nifty and 302 on Sensex. So 1 Nasdaq point ≈ 0.42 Nifty points ≈ 1.3 Sensex points.

| His rule (Nasdaq) | Nifty | Sensex | Used |
|---|---|---|---|
| Stop 25 / target 38 | 10 / 16 | 32 / 49 | No: charges eat it (lost money in the test) |
| Stop 50 / target 76 | 21 / 32 | 65 / 98 | **Yes: 20 / 30 and 60 / 90** |
| Stop never under 25 | never under 10 | never under 32 | |
| 9:30 New York open, first 90 minutes | 9:15 to 10:45 | 9:15 to 10:45 | |
| 2 pm New York session | (13:30 to 15:00 tested) | | No: it lost money |
| Expected news at 8:30 (CPI, PPI) | RBI policy at 10:00, Budget | same | Manual fair price on those days |

## Morning routine

| Time | What to do |
|---|---|
| Before 9:15 | Open TradingView, NIFTY (or SENSEX), **1 minute**, Fair Price indicator on. Check for news: an RBI policy day, the Budget, a big overnight US move. Open the Fair Price Desk. |
| 9:15 | The blue line is the fair price. The table shows today's bias. |
| 9:16 | The 9:15 candle has closed. If the indicator prints BUY or SELL "CONT", screenshot it, upload to the app, check the plan, and buy the at-the-money call (BUY) or put (SELL). |
| 9:16 to 10:45 | Wait for price to move away from the blue line, past the dotted line. When a BUY / SELL "BOS" label prints, screenshot, check the app, enter. |
| In a trade | Do nothing until the stop or target. Then mark it in the app's **Today** tab. |
| 2 losses in a row | Stop. The app and the indicator both say so. |
| 10:45 | No new trades. Anything open runs to its stop or target, or 3:15. |

**News days.** On an RBI policy day, type the 9:59 price into "Manual fair price" for trades after 10:00 (he
trades expected news back to the pre-news price). After surprise news (a sudden spike with no scheduled event),
he treats the place where price goes sideways after the spike as the new fair price. That's a judgement call, so
the safest choice is to stop for the day.

## Money: ₹30k, one lot

You trade **options**, not futures: one Nifty futures lot needs well over ₹1 lakh of margin. You buy one lot of the
at-the-money option (Nifty lot 65, Sensex lot 20; weekly expiry Tuesday for Nifty, Thursday for Sensex).

| | Nifty | Sensex |
|---|---|---|
| One lot of an ATM option | about ₹6,000 to ₹10,000 | about ₹4,000 to ₹8,000 |
| Break-of-structure trade: stop / target on the index | 20 / 30 points | 60 / 90 points |
| ...option loss if stopped (delta 0.5, with charges) | about ₹780 (up to ₹1,200 in fast markets) | about ₹730 |
| ...option profit at target | about ₹845 | about ₹770 |
| Opening trade: stop / target on the index | 40 / 60 points | 120 / 180 points |
| ...option loss if stopped | about ₹1,430 | about ₹1,330 |
| A bad day: opening trade lost, then one more loss | about ₹2,200 (7% of ₹30k) | about ₹2,050 |

The indicator and the app size trades at **5% of capital per trade** by default (₹1,500). That allows one lot of
each trade above and blocks anything bigger. Placing the stop: either watch the index level the indicator draws
and exit the option when it's hit, or put a stop-loss order on the option at the premium the app shows (premium
minus delta times the stop points). Option premiums don't move exactly with delta, so the index level is the
real stop.

## What the test showed

His rules on the last 19 trading days of 1-minute data (4 Sep to 1 Oct 2026), one lot per trade, stopping after 2
losses in a row. Option profit is estimated at delta 0.5 after ₹130 per lot for charges and slippage.
"Random" is the share of 500 runs where coin-flip directions (same entry times, stops and targets) did as well or
better. Lower is better: it means the direction calls mattered.

| Version | Trades | Won | 1 lot, 19 days | Random |
|---|---|---|---|---|
| **Nifty**: opening candle (40 / 60) + break of structure (20 / 30) | 39 | 54% | **+₹7,280** | 11% |
| **Sensex**: opening candle (120 / 180) + break of structure (60 / 90) | 33 | 58% | **+₹9,735** | 6% |
| Nifty, break of structure only (skip the opening trade) | 32 | 56% | +₹4,290 | 10% |
| Nifty, with displacement entries added | 47 | 45% | +₹1,040 | 44% |
| Nifty 10 / 15 (his exact points, scaled) | 58 | 50% | −₹228 | 5% |
| Nifty, adding an afternoon session (13:30 to 15:00) | 83 | 47% | +₹561 | 21% |
| Same rules on 5-minute candles, Nifty, 59 days | 43 | 40% | −₹7,756 | 44% |
| Same rules on 5-minute candles, Sensex, 59 days | 47 | 28% | −₹18,435 | 91% |

- **Nifty days:** 11 up, 6 down, 2 flat. Worst day −₹1,560, best +₹4,355.
- **Sensex days:** 11 up, 5 down, 3 flat. Worst day −₹1,410, best +₹4,080.
- The opening trade made most of the profit: Nifty 12 trades (7 won), Sensex 10 (7 won). That's very few trades.
- A cross-check with an option-price model fitted to NSE bhavcopy gave a larger Nifty figure (+₹10,790), with
  bigger average losses (₹1,208) and wins (₹1,550) than the delta-0.5 estimate.
- 19 days is short, and I picked the 20 / 30 stop after seeing results for 10 / 15 to 25 / 50 (all of 15 / 22 and
  up were positive on Nifty). The 5-minute result is a warning that the edge may not hold.

## What's left out of his method, and why

- **Many accounts and layering.** He sends the same idea into dozens of prop accounts and adds more as price moves.
  With one account you take each signal once.
- **Targets set by the account.** He picks 25, 38, 50, 75 or 100 points depending on each prop firm's rules. That
  doesn't apply to your own money, so the target is fixed at 1.5 times the stop.
- **The 2 pm session** lost money in the Indian version, so it's off (in Python, `pm_start` / `pm_end` turn it on).
- **News drift trades** (follow a surprise spike with a wide stop and no target): too discretionary to test.

## Files

- `tci/fairprice.py`: `FPParams` holds every setting (stop, target, room, window, losses, entries).
  `run_day(prev_day_bars, today_bars, params)` returns the day with its trades.
- `tests/test_fairprice.py`: 11 tests (bias, opening trade, big opening candle, break of structure, room check,
  fair-price target, displacement, window, afternoon session, the loss stop).
- `tradingview/fair_price.pine`: the indicator. Settings: Index (NIFTY / SENSEX), entries, stop / target, window,
  losses, manual fair price, capital and risk.
- `app/fair-price-desk.html`: the app. Opened as a plain file it works with typed numbers. Screenshot reading
  needs the published artifact, because it asks Claude to read the image.

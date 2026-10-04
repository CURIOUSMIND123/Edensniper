# Fair Price Reversal: Nifty 1-minute indicator

One TradingView indicator that tells you, on the live chart, **when to buy, when to sell, where the stop is and
where the target is**. You trade the options yourself.

- Indicator code: [`tradingview/fair_price.pine`](tradingview/fair_price.pine). There is also a copy page with
  setup steps (a claude.ai artifact).
- Rules in Python, used for every test below: [`tci/fairprice.py`](tci/fairprice.py) (`tested_params`), with
  tests in [`tests/test_fairprice.py`](tests/test_fairprice.py).
- Every test trade: [`research/fair_price_reversal_2023_2026.csv`](research/fair_price_reversal_2023_2026.csv).
- Re-run the test yourself: `python research/fair_price_backtest.py` (it downloads the 1-minute candles).

![Fair Price Reversal on a real day](tradingview/fair-price-preview.png)

## What you see on the chart

| On the chart | Meaning |
|---|---|
| Blue line **FAIR** | Today's 9:15 open. |
| Red dotted **SELL ZONE** line | Above it, price is far enough above the open to look for a sell. |
| Green dotted **BUY ZONE** line | Below it, price is far enough below the open to look for a buy. |
| Green **BUY** / red **SELL** label | The signal, at the close of the candle. It shows the entry, **STOP** and **TARGET**. |
| Red / green lines | The stop and the target, drawn until the trade ends. |
| **TARGET HIT / STOP HIT / 3:15 EXIT** | How the trade ended, with the points. |
| Box at the top right | What to do right now. For example: "WAIT: price +35 from fair", "BUY ZONE: BUY if a candle closes above 22,606", "IN BUY from 22,606 STOP 22,568 TARGET 22,718", "DONE FOR TODAY". |

Alerts: create one alert with condition **Fair Price Reversal → Any alert() function call**. It fires on every
signal (with stop and target), every exit, and when price first enters a zone.

## The rules

1. **Fair price** = the 9:15 open.
2. **Usual opening range** = the median high-to-low of 9:15 to 10:45 over the last 20 days. It sets every
   distance, so the indicator adjusts by itself as the market gets calmer or wilder. Nifty in October 2026:
   about 98 points.
3. **Stop** = 0.4 × usual range (about 39 Nifty points). **Target** = 3 × stop (about 118 points).
4. **Zones**: trade only after price has moved at least 0.8 × target away from the open (about 94 Nifty
   points). Small moves away from the open are not traded. This filter is the biggest difference from his
   rules as given.
5. **Signal**: inside a zone, the first 1-minute candle that **closes** beyond the latest swing, back toward the
   open. A swing high is a candle whose high is above the 2 candles before it and the 2 after it. Below the open,
   a close above the last swing high is a BUY. Above the open, a close below the last swing low is a SELL.
6. New signals only **9:15 to 10:45**. One trade at a time. After **2 losses in a row**, no more trades that day.
   Anything still open is closed at 3:15.

Typical trade: a signal between 9:30 and 10:45 (mostly after 10:00), held about 1½ hours. There's **no signal on most days** (about 1 day in 8).

## What the test says (915 days, January 2023 to October 2026)

Real 1-minute Nifty and Sensex candles from Upstox. One R is the stop distance. Every trade pays 4 Nifty points
(12 Sensex points) for charges and the bid-ask spread, the cost of an option round trip at delta 0.5. I tuned
the settings on January 2023 to June 2025 and kept July 2025 to October 2026 aside to check them.

| Nifty | Trades | Result |
|---|---|---|
| 2023 | 36 | +25.2R |
| 2024 | 28 | +6.0R |
| 2025 | 33 | +10.1R |
| 2026 (to 1 Oct) | 28 | +2.0R |
| **All** | **125** (about 4 in 10 won) | **+43.3R**, average +0.35R per trade |
| Tuning period / check period | 86 / 39 | +41.3R / **+2.0R** |
| June to September 2026 | 16 (2 hit target) | **−5.3R** |

- Coin-flip directions with the same entries, stops and targets did as well in only 1% of 300 runs. On Nifty the
  direction calls matter.
- **Sensex is weaker**: 145 trades, +25.7R, but −7.3R in 2026 and −6.7R in the check period, and random
  directions did as well 17% of the time. Use it on Nifty.
- **Be careful with these numbers.** I picked these settings out of about 2,300 combinations. On the months I
  kept aside, Nifty only broke even (+2R in 39 trades), and the last four months lost. Expect much less than the
  full-period average.

### What it means for your money (Nifty, compounding every trade)

| Risk per trade (one stop) | ₹30,000 became | Worst fall from a peak | Longest losing run |
|---|---|---|---|
| 2% | ₹65,760 | −15% | 6 losses |
| 5% | ₹1,60,198 | −35% | 6 losses |
| 10% | ₹3,54,775 | −62% | 6 losses |

These are over 3¾ years, with the in-sample average. At 10% per trade, six losses in a row (which happened)
cut the account almost in half, and you would have watched it fall 62% from a high.

### "20% profit, 10% loss, every day"

That isn't possible with this indicator or anything else I tested. On 805 of the 915 days there was no signal at
all. Risking 10% per trade, only 34 days ended up 20% or more, and 56 days lost 10% or more. Compounding 20% a day
for one year would turn ₹30,000 into more money than exists. Treat any method that promises it as broken.

## What I tested and dropped

| Tried | Result over 915 days |
|---|---|
| His rules as given (opening-candle trade + break of structure, 20 / 30) | **Nifty −357.7R** over 1,828 trades, **Sensex −312.5R**. Lost every year. The good 19-day result was luck. |
| 480 stop / target / entry combinations of his method | 37 positive while tuning, 6 positive in both periods, all small |
| 1,320 further combinations (swing size, zone distance, time window, break-even, loss limit) | The wide-stop, big-move version above was the most consistent |
| Opening-range breakout (432 variants) | Best: +29R on Nifty, but losing in 2026 |
| Supertrend (24 variants) | About break-even after costs (+10R Nifty over 1,034 trades) |
| EMA crossover (32 variants) | About break-even after costs |
| His displacement entries, his afternoon session, the opening-candle trade | Lost money or broke even, so they're left out |
| TCI + JJ combined (liquidity sweep back toward the open), 144 variants | Didn't hold up after the tuning period |
| Machine learning on 26 TCI / JJ / momentum measurements, about 10 trades a day | Right 51-52% of the time; −25,200 Nifty points after costs over 680 days |
| FII vs retail positioning (NSE participant open interest) | No help during the day; it made the model worse |

Plain-language summary of all of this: [`research/WHAT_THE_TESTS_SHOW.md`](research/WHAT_THE_TESTS_SHOW.md).

## Trading it with options

The indicator gives index levels. An at-the-money option moves about half as much as the index, so a 39-point
stop is about 19–20 points of premium, and a 118-point target about 55–60. Option premiums don't follow the index
exactly, so treat the **index level as the real stop**: exit the option when the index touches the STOP line.

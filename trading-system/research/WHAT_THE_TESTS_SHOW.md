# What the tests show, in plain words

![Edge versus cost](edge-vs-cost.png)

## What a backtest is

A backtest replays the past one minute at a time. At each minute the rules see only what had happened up to
then, decide whether to buy or sell, and the trade is closed at its stop, its target or 3:15, exactly as if it
were live. Every trade pays its costs. Add up all the trades and you see what the rules would have made.

The data: every 1-minute Nifty and Sensex candle from January 2023 to October 2026 (915 trading days, Upstox's
public candle API), plus NSE's daily positions of FIIs, DIIs, proprietary desks and retail clients ("participant
wise open interest") for the same days.

## The one number that decides everything: cost per trade

Buying and selling one option lot costs brokerage, STT, exchange fees, GST and the bid-ask spread. Together
that's about ₹130 per lot, which equals about **4 Nifty points** of index movement (an at-the-money option moves
about half as much as the index). A typical 30-minute Nifty move is 17 points, so every trade starts about a
quarter of a typical move behind.

To make money, a strategy's average trade has to beat 4 points before costs. The chart above shows that nothing
that trades often comes close.

## What was tested

| Approach | What it is | Result after costs |
|---|---|---|
| JJ Simon's rules as given | Opening-candle trade, then trades back to the 9:15 open | Nifty −358R over 1,828 trades, lost every year |
| 1,800 variations of JJ's rules | Stops, targets, zone distance, swing size, window, break-even, loss limits | Almost all lose. Best: Fair Price Reversal (below) |
| TCI + JJ combined | A liquidity sweep of a TCI level (yesterday's high / low, opening range) that pulls price back toward JJ's fair price; 144 variations | 40 looked good on 2023 to mid-2025, 11 stayed positive afterwards, all small. The best one in the tuning years lost −57R afterwards |
| Opening-range breakout, Supertrend, EMA crossovers | 488 variations of common indicator strategies | About break-even at best |
| Machine learning | A model reads 26 measurements every 5 minutes (TCI levels, sweeps, JJ's distance from the open, momentum, time of day, gap) and predicts the next 15 / 30 / 60 minutes. Each month it learns only from earlier months | Right 51 to 52% of the time (a coin flip is 50%). About 10 trades a day: −25,200 Nifty points over 680 days |
| Retail vs smart money | FII, retail (Client) and Pro positions in index futures and options, published by NSE every evening | Lines up slightly with the next morning's gap, which you can't trade because the data comes out after the close. Says nothing useful about 9:15 to 3:30. Added to the model, results got worse |

R means one stop-loss amount. −358R means the rules lost 358 times what one stop costs.

## Why the 19-day test looked good

Over 19 days, a strategy with no real edge can easily look profitable, the same way a coin can land heads 12
times in 19. The longer test (915 days) is what tells the truth.

## What did hold up

**Fair Price Reversal** on Nifty: trade only after price has moved far from the 9:15 open (about 94 points), on a
1-minute close back toward it, with a wide stop (about 39 points) and a 1 : 3 target (about 118 points). Its
average trade earns about 19 points before costs, so it clears the 4-point cost. It's positive in every year
from 2023 to 2026. But:

- It trades about once a week, not 10 times a day. That's why it works: it waits for the rare big move, where
  the edge is bigger than the cost.
- In the 15 months it wasn't tuned on, it earned less (about 9 points per trade before costs, +2R in total),
  and June to September 2026 lost money.

## "80% win rate" setups on the 5-minute chart

![Win rate trap](win-rate-trap.png)

I searched 1,820 five-minute setups (TCI liquidity traps at yesterday's high / low, the opening range, swings
and the day's high / low; JJ's fair-price reversal; trend pullbacks) with small targets and wide stops, which is
how you get a high win rate.

- **523 of them won 80% or more in the last 90 days** (3 July to 1 October 2026). A high win rate is easy:
  take profit after a few points and give the stop lots of room.
- Only 16 of those 523 made money in those 90 days. Wins were small and losses big: a typical one won
  +12 points and lost −55.
- Only 1 also made money in the 90 days before that, and none did over the full 3¾ years.
- The busiest one won 87.5% of 64 trades in the last 90 days (+223 points). Over 3¾ years it won 77.5% and
  lost −4,895 points. That's the orange line above.

One setup held up on Nifty: **Liquidity Trap**, a stop hunt at yesterday's high or low. A 5-minute candle trades
about 8 points beyond the level and closes back inside; target about 25 points, stop about 59. Results:

- Nifty: 105 trades in 3¾ years (about one every 9 days), 78% won, +520 points after costs. It lost a little in
  2023 and made money in 2024, 2025 and 2026.
- Last 90 days: 10 trades, 80% won, +20 points.
- Sensex: the same rules lost −2,017 points. Treat the Nifty result as thin.

It's in `tradingview/liquidity_trap.pine` as a TradingView strategy, so TradingView's Strategy Tester shows the
same numbers on your own chart.

## How to re-check all of this

- `python research/fair_price_backtest.py` downloads the candles and re-runs the Fair Price test.
- `research/quant/`: the machine-learning, combination and sentiment tests (see the README there).

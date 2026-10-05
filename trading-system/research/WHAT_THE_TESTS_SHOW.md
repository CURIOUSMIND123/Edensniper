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

## Breakout, pullback, ride: trades every day

I tested 960 versions of: a breakout through a level (yesterday's high / low, the opening range, today's
swings), with or without a "real breakout" filter (a strong or expanding candle); a pullback to the level; a
reversal candle (close past the previous candle, engulfing, or pin bar); then a fixed target, a trailing stop or
holding to 3:15.

- 448 of them traded at least 0.8 times a day in the last 90 days. 43 made money there, 7 also in the 90 days
  before, 5 also over all 3¾ years, and 3 also on Sensex.
- **Win rates were 20-40%, never 70-80%.** Riding a move means many small losses (stopped or scratched at
  entry) and a few big wins. 11 versions won 70%+ in the last 90 days; none of them made money.
- The best all-round version, **Breakout Retest**: real breakout (candle range at least 1.5× the last six),
  pullback within about 12 points of the level, entry on a close past the previous candle, stop about 29
  points, stop to entry after +15, then a trail about 59 points behind the best close.
  - Nifty: 1,482 trades (1.6 a day), 25% won, average win +77 and loss −24, +1,621 points after costs.
    Last 90 days +163, the 90 days before +975, but 2025 lost −1,546. About 2 days in 3 lost money.
  - Sensex: +3,334 Sensex points over all years, but −154 in the last 90 days and −5,224 in 2025.
  - **Random buy / sell directions with the same entries and exits did as well in about 1 run in 5.** The
    profit comes mostly from cutting losers fast and riding the occasional trend, not from calling direction.

It's in `tradingview/breakout_retest.pine` as a TradingView strategy.

## 15-day levels, volume profile and consolidations

Levels rebuilt every morning from the last 15 days: every daily high and low, profile peaks (prices where the
most trading happened), and consolidations (an hour or more inside a narrow band). Lines within about 10 Nifty
points are merged into one. The Nifty index has no volume, so this test uses time spent at each price (the
classic market profile); the TradingView indicator can use Nifty futures volume instead.

I tested 1,296 versions: rejection candles at the levels (pin bar or engulfing, then trade back), or strong
breakout candles through them; which levels to use; how close counts as a touch; stop size; target at the next
level or a fixed multiple.

- 774 versions traded at least 0.8 times a day in the last 90 days. 24 made money there; none of those also made
  money in the 90 days before.
- **Rejection candles at the levels lost money**: −3,161 Nifty points and −27,882 Sensex points over 3¾ years
  using all the lines.
- **Adding profile peaks and consolidations to the trade levels made results worse** (Nifty −1,964 with them,
  +1,863 without).
- What held up: a **strong breakout candle through a "double" daily level**, where two or more of the last 15
  daily highs / lows sit within about 10 points. Stop about 12 points back across the level, target the next
  such level at least 2× the stop away.
  - Nifty: 719 trades (0.8 a day), 36% won, average win +72 and loss −36, +1,863 points after costs, positive
    in each of 2023, 2024, 2025 and 2026. Last 90 days −132, the 90 days before +138.
  - Random buy / sell directions with the same entries, stops and targets did as well in only 2% of runs.
  - Sensex: +3,304 Sensex points, but it lost in 2023 and 2026.

It's in `tradingview/levels_15d.pine`. It draws all the lines (15-day highs / lows, VOL, CONS, merged) and
trades only the tested breakouts unless you switch that off.

## How to re-check all of this

- `python research/fair_price_backtest.py` downloads the candles and re-runs the Fair Price test.
- `research/quant/`: the machine-learning, combination and sentiment tests (see the README there).

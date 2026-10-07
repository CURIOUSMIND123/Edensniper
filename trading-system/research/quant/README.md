# Quant tests behind WHAT_THE_TESTS_SHOW.md

Run from this folder. Data lives in `../.cache/` (not committed):

1. `python ../fair_price_backtest.py` downloads `nifty_1m.json` and `sensex_1m.json` (Upstox public candles).
2. `python fetch_poi.py` downloads NSE participant-wise open interest for every trading day into `poi.json`.

| Script | Test |
|---|---|
| `build.py nifty` (and `sensex`) | One row per 5-minute decision point, 9:30 to 14:55: TCI levels, sweeps, distance from the 9:15 open, momentum, time of day, gap, and the next 15 / 30 / 60 minutes |
| `wf.py nifty` | Walk-forward machine learning (gradient boosting and logistic regression, retrained monthly on earlier months only), traded at three confidence levels |
| `sentiment.py ml` | FII / Client / Pro positioning against the next day's gap and open-to-close move, day trades that follow FII or fade retail, and the model with positioning added |
| `combo.py` | TCI liquidity sweeps combined with JJ's fair price, 144 variations, tuned on Jan 2023 to Jun 2025 and checked afterwards |
| `alt.py` | Opening-range breakout, Supertrend and EMA crossovers |

Costs: 4 Nifty points or 12 Sensex points per trade. `pip install pandas scikit-learn` first.
| `liquidity_trap_test.py` | Reference for `tradingview/liquidity_trap.pine` (5-minute, TradingView fill rules); prints its results by period |
| `high_win_search.py` | 1,820 five-minute setups: which win 80%+ in the last 90 days, and how they did before that |
| `breakout_retest_test.py` | Reference for `tradingview/breakout_retest.pine`; prints its results by period and a random-direction check |
| `breakout_search.py` | 960 breakout / pullback / reversal-candle / ride versions on Nifty and Sensex, last 90 days vs before |
| `levels15_build.py` | Rolling 15-day levels for every day: daily highs / lows, time-at-price profile peaks, consolidation boxes, merged |
| `levels15_test.py` | Reference for `tradingview/levels_15d.pine` (`--default`) and the 1,296-version search of rejection and breakout signals at those levels |
| `combine_test.py` | All four strategies together on Nifty, their correlation, and trading only without (or with) a second strategy's agreement |
| `combo4_mirror.py` | Line-by-line Python copy of `tradingview/combo4.pine`; reproduces `combine_test.py` (+7,403 points) |
| `breakout_probability_test.py` | Rebuild of "Breakout Probability (Expo)" on any candle size (e.g. `nifty 65 3`); scores its strong calls over the last 30 days |
| `breakout_probability_scalp.py` | Trades the same calls as 1:2 scalps (stop X, target 2X, whichever comes first) on any candle size (e.g. `nifty 3`); last 30 days and the 12 months before |

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
| `breakout_probability_peak.py` | Its highest readings on every candle since 2023 (e.g. `nifty 5`): did it ever show 90%, and did its top readings pay? Also a 50-candle-memory version that does reach 90% |
| `cpr_study.py` | CPR width and where the day opens vs the CPR: what the day did next (e.g. `nifty`); last 60 sessions, the 30 before, all since 2023 |
| `cpr_backtest.py` | 576 CPR + pivot rule versions (fade to the CPR, opening-range breakout, CPR break, R1 / S1 rejection, all-day bias), picked on the last 60 sessions |
| `cpr_walkforward.py` | Picks the best versions on Feb 2023 - Jun 2025 only and shows what they did afterwards (run `cpr_backtest.py` for both indices first) |
| `cpr_magnet_check.py` | The CPR Magnet rule in detail: narrow vs other days, random-direction baseline, drawdown, every trade in the last 90 sessions |
| `cpr_magnet_lastn.py` | CPR Magnet day by day over the last N sessions (e.g. `nifty 30`): why each day did or didn't trade, how each trade ended, points won and lost |
| `cpr_orb.py` | Open vs the CPR, the first 15-minute candle's high / low break, the 15-day point of control and value area, EMA 50: how often each idea held, then 3,888 combined breakout versions at 1:3, ride or trail (e.g. `nifty`) |
| `cpr_orb_pick.py` | Which `cpr_orb.py` versions made money on both indices, every year, and in a walk-forward split (run `cpr_orb.py` for both first) |
| `cpr_orb_lastn.py` | The chosen CPR Breakout version trade by trade over the last N sessions (e.g. `nifty 90`) |
| `cpr_orb_winrate.py` | How high the CPR Breakout's win rate can go while it still makes money: targets 0.1R-3R, trail, half booked early, seven trend filters |
| `cpr_winrate_pick.py` | Reads the `cpr_orb_winrate.py` results for both indices: versions with 70 / 80 / 90%+ wins, and which of them made money |
| `cpr_scalp_lastn.py` | The highest-win-rate version that made money on both indices, trade by trade over the last N sessions |
| `cpr_scalp.py` | Pure scalps at the CPR, pivot and 15-minute levels: 10-30 point targets, 10-40 point stops, time limits, up to 5 trades a day |
| `pa_ml.py` | Price action + levels + machine learning: about 55 candle-shape, momentum, level, CPR and volatility measurements at every 5-minute close; learns which led to +25 before -15 (or ATR-sized); scored on 2026 only (e.g. `nifty`) |
| `pa_ml_importance.py` | Which measurement groups the `pa_ml.py` model relied on in 2026 |
| `y2026.py` | 2026 only: CPR Magnet and CPR Breakout trade by trade, what the losing trades had in common (real-volume zones from NIFTYBEES, 30-day Fibonacci, trend, volatility, time), and which adjustments helped in both halves of 2026; `breakout_live()` is the adjusted indicator rule |
| `y2026_levels.py` | 2026 only: scalps taken at the volume zones and Fibonacci levels themselves |
| `y2026_daily.py` | 2026 only: the daily plan (CPR Breakout on narrow days; CPR Magnet or the breakout on other days), with and without half booking, by half-year and month |
| `y2026_losses.py` | 2026 only: every losing trade of the daily plan, and which CPR Magnet changes (stop size, time stop, gap size, open inside yesterday's range, confirmation, POC side, volatility) cut losses |
| `y2026_rupees.py` | 2026 only: the daily plan in rupees for Rs 30,000 with 2 at-the-money option lots (delta 0.5, lots 65 / 20), by month, with drawdowns |
| `btc_load.py` | Turns Binance's public 1-minute BTCUSDT futures archives (data.binance.vision) into `../.cache/btc_1m.json` (run with `python -I`) |
| `btc_2026.py` | 2026 only: the daily-plan indicator on Bitcoin (UTC day as the session, Bitcoin's own volume), and Rs 30,000 at 1x to 150x leverage |
| `btc_all.py` | 2026 only: every strategy built so far run on Bitcoin (as `btcist`: its candles in IST market hours, Binance costs), and Rs 30,000 at 1x-150x leverage |
| `btc_h1_load.py` | Binance public archives -> hourly BTCUSDT candles and funding rates, Jan 2023 - Oct 2026 (run with `python -I`) |
| `btc_trend.py` | Bitcoin strategies built for Bitcoin (Donchian breakout, EMA trend, daily volatility breakout, dip buying; 60 versions), designed on 2023-2025 and tested on 2026, with fees, funding and leverage |
| `btc_trend_basket.py` | The 4-hour trend-following versions from `btc_trend.py` traded together, 2026 and 2023-2025, 1x-150x |
| `btc_vol_lines.py` | Bitcoin volume lines (3 / 7 / 15-day POC and high-volume peaks): break a line, target the next one; designed on 2023-2025, tested on 2026 |
| `y2026_vol_lines.py` | 2026 only: the same volume-line breakouts on Nifty / Sensex with NIFTYBEES volume (e.g. `nifty`) |
| `y2026_combo.py` | 2026 only: the CPR daily plan plus 3-day volume-line trades, side by side or one trade at a time, with rupees at 2 lots (e.g. `nifty`) |
| `y2026_trades.py` | 2026 only: every trade of the indicator one by one: calls vs puts, how far winners kept going after we booked, whether losers were in profit first |
| `y2026_improve.py` | 2026 only: exit changes from that review (magnet rest to the far edge / trail / hold, breakout trail 1.5R / 2R / hold, volume-line breakeven stop and line-to-line ladder), alone and in all 64 combinations |
| `alerts_check.py` | Checks that `alerts/cprb_alerts.py` (live alerts) takes exactly the backtest's 2026 trades, also minute by minute as it runs live |

"""Rs 5,000 -> Rs 50,000 in a week on Bitcoin at 50x (asked on 15 October 2026): how often does it happen?

    python btc_10x_week.py

Binance BTCUSDT futures 1-minute candles (October 2025 - 9 October 2026). Every week from Monday 00:00 UTC: the whole
balance as margin at 50x, one trade after another, compounding, until the balance reaches Rs 50,000 (done), drops
below Rs 500 (gone) or the week ends. Each trade: take profit and stop loss the same distance from the entry
(0.5% / 1% / 1.5% of price; 50x is liquidated at about 1.6%), direction by a coin flip (200 runs a week), with the
last hour's move (trend) or against it (fade). Costs 0.11% of the position a trade (taker fee both sides plus
slippage) = 5.5% of the margin at 50x. A candle reaching both the target and the stop counts as the stop.
For comparison: in a fair game with no costs, the chance of turning 5,000 into 50,000 before losing it is 10%.
"""
import collections, json, random
import numpy as np

raw = json.load(open('../.cache/btc_1m.json'))
keys = sorted(raw)
O = np.array([raw[k][0] for k in keys]); H = np.array([raw[k][1] for k in keys])
L = np.array([raw[k][2] for k in keys]); C = np.array([raw[k][3] for k in keys])
import datetime as dt
T = [dt.datetime.strptime(k, '%Y-%m-%d %H:%M') for k in keys]
starts = [i for i, t in enumerate(T) if t.weekday() == 0 and t.hour == 0 and t.minute == 0]
LEV, COST, START, GOAL, GONE = 50, 0.0011, 5000.0, 50000.0, 500.0

def trade(i, side, x):
    """Enter at the open of minute i; out at +x / -x. Returns (return on the margin, next minute)."""
    e = O[i]; tp = e * (1 + side * x); sl = e * (1 - side * x)
    j = i
    n = len(O)
    while j < n:
        if (L[j] <= sl) if side > 0 else (H[j] >= sl):
            return -LEV * x - LEV * COST, j + 1
        if (H[j] >= tp) if side > 0 else (L[j] <= tp):
            return LEV * x - LEV * COST, j + 1
        j += 1
    return LEV * side * (C[-1] - e) / e - LEV * COST, n

def week(s, x, how, rng):
    end = s + 7 * 1440
    bal, i, n = START, s + 60, 0
    while i < end and i < len(O) - 1:
        if how == 'coin':
            side = 1 if rng.random() < 0.5 else -1
        else:
            mv = C[i - 1] - O[i - 60]
            side = (1 if mv >= 0 else -1) * (1 if how == 'trend' else -1)
        r, i = trade(i, side, x)
        bal *= max(0.0, 1 + r); n += 1
        if bal >= GOAL:
            return 'done', bal, n
        if bal < GONE:
            return 'gone', bal, n
    return 'end', bal, n

if __name__ == '__main__':
    print(f"Bitcoin, {len(starts)} weeks ({keys[starts[0]][:10]} - {keys[starts[-1]][:10]}), Rs 5,000 at 50x, all in, compounding")
    rng = random.Random(7)
    for x in (0.005, 0.01, 0.015):
        for how in ('coin', 'trend', 'fade'):
            runs = 200 if how == 'coin' else 1
            res = collections.Counter(); ends = []; trades = []
            for s in starts:
                for _ in range(runs):
                    out, bal, n = week(s, x, how, rng)
                    res[out] += 1; ends.append(bal); trades.append(n)
            tot = sum(res.values())
            print(f"  target / stop {x * 100:.1f}%, direction {how:5}: reached Rs 50,000 in {100 * res['done'] / tot:4.1f}% of the weeks, "
                  f"lost it all in {100 * res['gone'] / tot:4.1f}%, neither {100 * res['end'] / tot:4.1f}% | median end Rs {np.median(ends):,.0f}, "
                  f"median {np.median(trades):.0f} trades")

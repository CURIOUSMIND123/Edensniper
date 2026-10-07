"""Breakout Probability (Expo) replica on 15-minute candles, then a check of its strong calls over the last 30 days.

    python breakout_probability_test.py nifty 65      (index, probability threshold in %)

The indicator shows, for each line, how often the next candle reached it in the chart's history, split by the
colour of the current candle. Line 0 is the candle's own high / low; lines step 0.1% of price beyond it.
"""
import json, collections, statistics as st, sys
name = sys.argv[1] if len(sys.argv) > 1 else 'nifty'
COST = {'nifty': 4.0, 'sensex': 12.0}[name]
THR = float(sys.argv[2]) if len(sys.argv) > 2 else 70.0
STEP_PCT, NLINES, HISTORY = 0.1, 5, 5000          # indicator defaults; ~5,000 bars of chart history
raw = json.load(open(f'../.cache/{name}_1m.json'))
by = collections.defaultdict(list)
for k in sorted(raw):
    hm = int(k[11:13]) * 60 + int(k[14:16])
    if 555 <= hm < 930: by[k[:10]].append((hm, *raw[k]))
bars = []                                          # (day, minute, o, h, l, c)
for d in sorted(by):
    if len(by[d]) < 300: continue
    g = collections.OrderedDict()
    for m, o, h, l, c in by[d]: g.setdefault((m - 555) // 15, []).append((m, o, h, l, c))
    for k, ch in g.items():
        bars.append((d, 555 + 15 * k, ch[0][1], max(x[2] for x in ch), min(x[3] for x in ch), ch[-1][4]))
bars = bars[-(HISTORY + 600):]                     # chart history before and through the test window
START, END = '2026-09-07', '2026-10-07'            # last 30 days
tot = {1: 0, -1: 0}; up = {1: [0] * NLINES, -1: [0] * NLINES}; dn = {1: [0] * NLINES, -1: [0] * NLINES}
calls = []
for t in range(1, len(bars) - 2):
    d, m, o, h, l, c = bars[t]
    # 1. learn from the finished pair (t-1 -> t)
    pd_, pm, po, ph, pl, pc = bars[t - 1]
    col = 1 if pc > po else -1 if pc < po else 0
    if col:
        stp = pc * STEP_PCT / 100
        tot[col] += 1
        for i in range(NLINES):
            if h >= ph + stp * i: up[col][i] += 1
            if l <= pl - stp * i: dn[col][i] += 1
    # 2. what the indicator shows now, at the close of bar t, for the next bar
    col = 1 if c > o else -1 if c < o else 0
    if not col or tot[col] < 50 or not (START <= d <= END): continue
    stp = c * STEP_PCT / 100
    nd, nm, no, nh, nl, nc = bars[t + 1]
    d2, m2, _, h2, l2, c2 = bars[t + 2]
    same_day = nd == d and d2 == d
    for i in range(NLINES):
        for side, hits, lvl in ((1, up[col][i], h + stp * i), (-1, dn[col][i], l - stp * i)):
            p = 100 * hits / tot[col]
            if p < THR: continue
            right = (nh >= lvl) if side > 0 else (nl <= lvl)
            move30 = side * (c2 - c)                                  # from the signal close to 30 minutes later
            best = side * ((max(nh, h2) if side > 0 else min(nl, l2)) - c)  # best point within those 30 minutes
            # entry with a stop order at the level (only if the next candle breaks it), exit 30 minutes after the signal
            fill = (max(no, lvl) if side > 0 else min(no, lvl)) if right else None
            stopTrade = side * (c2 - fill) if right else None
            calls.append(dict(d=d, m=m, line=i, side=side, p=p, right=right, move30=move30, best=best, stopTrade=stopTrade, same=same_day))
def show(cs, label):
    if not cs: print(f'  {label}: none'); return
    r = [x for x in cs if x['right']]; w = [x for x in cs if not x['right']]
    mean = lambda xs: st.mean(xs) if xs else 0
    print(f"  {label}: {len(cs)} calls, correct {len(r)} ({100*len(r)/len(cs):.0f}%), average shown probability {mean([x['p'] for x in cs]):.1f}%")
    print(f"     30 min later, in the called direction: when RIGHT avg {mean([x['move30'] for x in r]):+.1f} pts (best point avg {mean([x['best'] for x in r]):+.1f}), when WRONG avg {mean([x['move30'] for x in w]):+.1f} pts")
    a = [x['move30'] - COST for x in cs]
    b = [x['stopTrade'] - COST for x in r]
    print(f"     trade A, enter at the signal close, exit 30 min later: {len(a)} trades, won {100*sum(v > 0 for v in a)/len(a):.0f}%, total {sum(a):+,.0f} pts after {COST:g} pts cost each")
    print(f"     trade B, buy/sell only when the level breaks, exit 30 min after the signal: {len(b)} trades, won {100*sum(v > 0 for v in b)/max(1,len(b)):.0f}%, total {sum(b):+,.0f} pts after costs")
print(f"{name.upper()} 15-minute, {START} to {END}; step {STEP_PCT}% (about {bars[-1][5]*STEP_PCT/100:.0f} pts), probabilities learned from {HISTORY:,} bars of history")
allc = [x for x in calls if x['same']]
print(f"lines at or above the threshold: by line {collections.Counter(x['line'] for x in calls)}; dropped {len(calls)-len(allc)} late-day calls whose 30 minutes run past the close")
show(allc, f"ALL {THR:g}%+ calls")
show([x for x in allc if x['side'] > 0], 'calls for a NEW HIGH (bullish)')
show([x for x in allc if x['side'] < 0], 'calls for a NEW LOW (bearish)')


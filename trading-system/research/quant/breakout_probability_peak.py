"""Did Breakout Probability (Expo) ever show 90%+ on 3- or 5-minute candles, and did its highest readings pay?

    python breakout_probability_peak.py nifty 3        (index, candle minutes)

Replays every candle from 2023 to 7 October 2026. On each candle the indicator's numbers are worked out the way a
live chart would show them: from the last 5,000 candles loaded on the chart. Its highest calls are then traded as
1:2 scalps (stop X, target 2X, whichever comes first on 1-minute candles) and as a 30-minute hold.
A second pass shortens its memory to the last 50 candles, which makes 90% readings possible, to see whether
those would have paid. Costs: 4 Nifty / 12 Sensex points.
"""
import json, collections, statistics as st, sys
name = sys.argv[1] if len(sys.argv) > 1 else 'nifty'
TF = int(sys.argv[2]) if len(sys.argv) > 2 else 3
COST = {'nifty': 4.0, 'sensex': 12.0}[name]
STEP_PCT, NLINES = 0.1, 5
raw = json.load(open(f'../.cache/{name}_1m.json'))
by = collections.defaultdict(list)
for k in sorted(raw):
    hm = int(k[11:13]) * 60 + int(k[14:16])
    if 555 <= hm < 930: by[k[:10]].append((hm, *raw[k]))
days = [d for d in sorted(by) if len(by[d]) >= 300 and d <= '2026-10-07']
one = {d: by[d] for d in days}
bars = []                                                          # (day, start minute, o, h, l, c)
for d in days:
    g = collections.OrderedDict()
    for m, o, h, l, c in one[d]: g.setdefault((m - 555) // TF, []).append((m, o, h, l, c))
    for k, ch in g.items(): bars.append((d, 555 + TF * k, ch[0][1], max(x[2] for x in ch), min(x[3] for x in ch), ch[-1][4]))

def readings(window, warmup):
    """Every candle's numbers: (bar index, colour, [up % per line], [down % per line]) from the last `window` candles."""
    ev = collections.deque(); tot = {1: 0, -1: 0}
    up = {1: [0] * NLINES, -1: [0] * NLINES}; dn = {1: [0] * NLINES, -1: [0] * NLINES}; out = []
    for t in range(1, len(bars) - 1):
        po, ph, pl, pc = bars[t - 1][2:]; h, l = bars[t][3], bars[t][4]
        col = 1 if pc > po else -1 if pc < po else 0
        if col:
            s = pc * STEP_PCT / 100
            u = [h >= ph + s * i for i in range(NLINES)]; w = [l <= pl - s * i for i in range(NLINES)]
            ev.append((t, col, u, w)); tot[col] += 1
            for i in range(NLINES): up[col][i] += u[i]; dn[col][i] += w[i]
        while ev and ev[0][0] <= t - window:
            _, c0, u, w = ev.popleft(); tot[c0] -= 1
            for i in range(NLINES): up[c0][i] -= u[i]; dn[c0][i] -= w[i]
        o, c = bars[t][2], bars[t][5]
        col = 1 if c > o else -1 if c < o else 0
        if not col or t < warmup or tot[col] == 0 or bars[t + 1][0] != bars[t][0]: continue
        out.append((t, col, [100 * x / tot[col] for x in up[col]], [100 * x / tot[col] for x in dn[col]]))
    return out

def path(o, h, l, c): return (o, l, h, c) if c >= o else (o, h, l, c)

def scalp(calls, stop_k, entry):
    """1:2 scalp; stop_k in Nifty-equivalent points scaled to the index price. One trade at a time."""
    res = []; busy = (None, -1)
    for d, m, side, lvl, c in calls:
        sig_end = m + TF
        if busy[0] == d and sig_end <= busy[1]: continue
        ms = [x for x in one[d] if x[0] >= sig_end]
        if not ms: continue
        if entry == 'close': e, k0 = c, 0
        else:
            k0 = next((k for k, x in enumerate(ms) if x[0] < sig_end + TF and (x[2] >= lvl if side > 0 else x[3] <= lvl)), None)
            if k0 is None: continue
            x = ms[k0]; e = max(x[1], lvl) if side > 0 else min(x[1], lvl); k0 += 1
        risk = stop_k * e / 22500.0; stp, tgt = e - side * risk, e + side * 2 * risk; out = None
        for k in range(k0, len(ms)):
            x = ms[k]
            for px in path(*x[1:]):
                if side * (px - stp) <= 0: out = (stp, x[0]); break
                if side * (px - tgt) >= 0: out = (tgt, x[0]); break
            if out: break
            if x[0] >= 925: out = (x[4], x[0]); break
        if not out: out = (ms[-1][4], ms[-1][0])
        res.append((d, side * (out[0] - e) - COST)); busy = (d, out[1])
    return res

def hold30(calls):
    res = []
    for d, m, side, lvl, c in calls:
        x = [y for y in one[d] if y[0] < m + TF + 30]
        if x[-1][0] < m + TF + 29: continue                          # not 30 minutes left in the day
        res.append((d, side * (x[-1][4] - c) - COST))
    return res

def line(res, label):
    if not res: print(f'      {label}: no trades'); return
    p = [r[1] for r in res]; byd = collections.defaultdict(float)
    for d, v in res: byd[d] += v
    yrs = collections.defaultdict(float)
    for d, v in res: yrs[d[:4]] += v
    print(f"      {label}: {len(p)} trades, won {100*sum(v > 0 for v in p)/len(p):.0f}%, total {sum(p):+,.0f} pts, "
          f"green days {sum(v > 0 for v in byd.values())}/{len(byd)}; by year " + ', '.join(f'{y} {v:+,.0f}' for y, v in sorted(yrs.items())))

def trade_all(calls):
    line(scalp(calls, 10, 'close'), 'scalp, enter at close, stop 10 / target 20')
    line(scalp(calls, 20, 'break'), 'scalp, enter on the break, stop 20 / target 40')
    line(hold30(calls), 'hold 30 minutes from the close')

def to_calls(rs, thr, lines):
    cs = []
    for t, col, u, w in rs:
        d, m, o, h, l, c = bars[t]; s = c * STEP_PCT / 100
        for i in lines:
            if u[i] >= thr: cs.append((d, m, 1, h + s * i, c))
            if w[i] >= thr: cs.append((d, m, -1, l - s * i, c))
    return cs

print(f"{name.upper()} {TF}-minute, {bars[0][0]} to {bars[-1][0]}, {len(bars):,} candles")
rs = readings(5000, 5000)
print(f"  As the chart shows it (last 5,000 candles), {len(rs):,} candles from {bars[rs[0][0]][0]}:")
for i in range(NLINES):
    a = [max(u[i], w[i]) for _, _, u, w in rs]
    print(f"    line {i}: lowest {min(a):.1f}%, median {st.median(a):.1f}%, highest {max(a):.1f}%")
top = max(max(u[0], w[0]) for _, _, u, w in rs)
for thr in (70, 75, 80, 90):
    print(f"    candles showing {thr}%+ on any line: {sum(max(max(u), max(w)) >= thr for _, _, u, w in rs):,}")
a0 = sorted(max(u[0], w[0]) for _, _, u, w in rs); cut = a0[int(len(a0) * 0.99)]
print(f"  Its highest 1% of readings ({cut:.1f}% to {top:.1f}%), traded:")
trade_all(to_calls(rs, cut, [0]))
print(f"  Shorter memory (last 50 candles), calls at 90%+ on any line:")
rs50 = readings(50, 5000)
cs = to_calls(rs50, 90, range(NLINES))
print(f"    {len(cs):,} calls on {len({c[0] for c in cs})} days")
trade_all(cs)

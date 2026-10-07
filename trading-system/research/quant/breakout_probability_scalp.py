"""Scalp the Breakout Probability (Expo) calls at 1:2: stop X, target 2X, exit at whichever is hit first.

    python breakout_probability_scalp.py nifty 3        (index, candle minutes)

Calls are the indicator's strong line-0 calls (65%+): after a green candle, a new high next candle; after a
red candle, a new low. Two entries are tested: at the call candle's close, or only when the next candle breaks
the call level (a stop order at that candle's high / low). Exits are checked on 1-minute candles from the
minute after entry, one trade at a time, closed by 15:25 at the latest. Costs: 4 Nifty / 12 Sensex points.
"""
import json, collections, statistics as st, sys
name = sys.argv[1] if len(sys.argv) > 1 else 'nifty'
TF = int(sys.argv[2]) if len(sys.argv) > 2 else 3
COST = {'nifty': 4.0, 'sensex': 12.0}[name]
THR, STEP_PCT, HISTORY = 65.0, 0.1, 5000
raw = json.load(open(f'../.cache/{name}_1m.json'))
by = collections.defaultdict(list)
for k in sorted(raw):
    hm = int(k[11:13]) * 60 + int(k[14:16])
    if 555 <= hm < 930: by[k[:10]].append((hm, *raw[k]))
days = [d for d in sorted(by) if len(by[d]) >= 300]
one = {d: by[d] for d in days}                                     # 1-minute candles per day
bars = []                                                          # (day, start minute, o, h, l, c)
for d in days:
    g = collections.OrderedDict()
    for m, o, h, l, c in one[d]: g.setdefault((m - 555) // TF, []).append((m, o, h, l, c))
    for k, ch in g.items(): bars.append((d, 555 + TF * k, ch[0][1], max(x[2] for x in ch), min(x[3] for x in ch), ch[-1][4]))

def calls_in(start, end):
    """The indicator's 65%+ line-0 calls between start and end (probabilities from 5,000 earlier candles)."""
    i0 = next(i for i, b in enumerate(bars) if b[0] >= start)
    seg = bars[max(0, i0 - HISTORY):]
    tot = {1: 0, -1: 0}; up = {1: 0, -1: 0}; dn = {1: 0, -1: 0}; out = []
    for t in range(1, len(seg) - 1):
        d, m, o, h, l, c = seg[t]
        if d > end: break
        po, ph, pl, pc = seg[t - 1][2:]
        col = 1 if pc > po else -1 if pc < po else 0
        if col:
            tot[col] += 1; up[col] += h >= ph; dn[col] += l <= pl
        col = 1 if c > o else -1 if c < o else 0
        if not col or tot[col] < 50 or d < start or seg[t + 1][0] != d: continue
        for side, hits, lvl in ((1, up[col], h), (-1, dn[col], l)):
            if 100 * hits / tot[col] >= THR:
                out.append((d, m, side, lvl, c))
    return out

def path(o, h, l, c): return (o, l, h, c) if c >= o else (o, h, l, c)

def scalp(calls, stop_k, entry):
    """stop_k: stop in Nifty-equivalent points (scaled to the index price); target = 2 x stop."""
    res = []; busy_until = (None, -1)
    for d, m, side, lvl, c in calls:
        sig_end = m + TF                                            # the call candle has closed
        if busy_until[0] == d and sig_end <= busy_until[1]: continue
        ms = [x for x in one[d] if x[0] >= sig_end]
        if not ms: continue
        if entry == 'close':
            e, k0 = c, 0
        else:                                                      # stop order at the level, next candle only
            k0 = next((k for k, x in enumerate(ms) if x[0] < sig_end + TF and (x[2] >= lvl if side > 0 else x[3] <= lvl)), None)
            if k0 is None: continue
            x = ms[k0]; e = max(x[1], lvl) if side > 0 else min(x[1], lvl); k0 += 1
        risk = stop_k * e / 22500.0
        stp, tgt = e - side * risk, e + side * 2 * risk
        out = None
        for k in range(k0, len(ms)):
            x = ms[k]
            for px in path(*x[1:]):
                if side * (px - stp) <= 0: out = (stp, 'SL', x[0]); break
                if side * (px - tgt) >= 0: out = (tgt, 'TP', x[0]); break
            if out: break
            if x[0] >= 925: out = (x[4], 'time', x[0]); break
        if not out: out = (ms[-1][4], 'end', ms[-1][0])
        res.append((d, side * (out[0] - e) - COST, out[1], out[2] - sig_end, risk))
        busy_until = (d, out[2])
    return res

def report(res, ndays, label):
    if not res: print(f'   {label}: no trades'); return
    p = [r[1] for r in res]; w = [x for x in p if x > 0]; lo = [x for x in p if x <= 0]
    byd = collections.defaultdict(float)
    for r in res: byd[r[0]] += r[1]
    tp = sum(r[2] == 'TP' for r in res)
    print(f"   {label}: {len(p)} trades ({len(p)/ndays:.0f}/day), target hit {100*tp/len(p):.0f}%, won after costs {100*len(w)/len(p):.0f}%, "
          f"avg win {st.mean(w) if w else 0:+.1f} / loss {st.mean(lo) if lo else 0:+.1f}, total {sum(p):+,.0f} pts, green days {sum(v > 0 for v in byd.values())}/{ndays}, median hold {st.median(r[3] for r in res):.0f} min")

for label, (a, b) in (('LAST 30 DAYS', ('2026-09-07', '2026-10-07')), ('THE 12 MONTHS BEFORE', ('2025-09-01', '2026-09-04'))):
    cs = calls_in(a, b); nd = len({x[0] for x in cs})
    print(f"{name.upper()} {TF}-minute, {label} ({a} to {b}): {len(cs)} calls")
    for entry in ('close', 'break'):
        for k in (5, 10, 15, 20):
            report(scalp(cs, k, entry), nd, f"enter at {'call close' if entry == 'close' else 'the break'}, stop {k} / target {2*k}")

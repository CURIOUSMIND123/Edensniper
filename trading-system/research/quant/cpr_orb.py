"""CPR bias + 15-minute range breakout + 15-day profile (highest-activity price), at 1:3 or riding the trend.

    python cpr_orb.py nifty        (or sensex)

1. How often the two ideas held in the last 90 sessions (and since 2023):
   A. the day opens above the CPR (and so above the pivot P) -> it keeps going up; below -> down
   B. price breaks the first 15-minute candle's high / low -> it keeps going that way
2. 3,888 versions of a breakout trade with those filters, entries and exits on 1-minute candles, after costs:
   cpr   none / agree (open above the CPR -> buys only, below -> sells only, inside -> no trade) / notagainst
   poc   none / poc (buy only above the 15-day point of control, sell only below) / va (above the value area
         high / below its low)
   ema   none / agree (5-minute EMA 50 on the right side)
   rel   none / notagainst (today's CPR vs yesterday's: higher value -> no sells, lower -> no buys)
   width any / narrow / notnarrow
   entry close5 (a 5-minute close beyond the 15-minute range) / touch (stop order at the range high / low)
   stop  range (other side of the 15-minute range) / mid (its middle) / 0.2% of price
   exit  3R (target 3 x risk) / ride (stop to entry at +1R, out at 15:15) / trail (stop 1R behind the best price
         once +1R)
   rev   no / yes (after a loss, take the break of the other side too, without the direction filters)
The 15-day profile is time at price from 1-minute candles (the index has no volume): point of control (POC) is the
price traded most, the value area the 70% around it. Entries 9:30 to 13:00, out by 15:15.
"""
import json, collections, itertools, statistics as st, sys
import numpy as np
import cpr_backtest as B

one, five, LV, TEST, COST, path = B.one, B.five, B.LV, B.TEST, B.COST, B.path
BIN = {'nifty': 5.0, 'sensex': 16.0, 'btcist': 25.0}[B.name]
CUT, T_OUT = 780, 915

# ---------------- 15-day time-at-price profile ----------------
lo_all = min(x[3] for d in B.days for x in one[d]); hi_all = max(x[2] for d in B.days for x in one[d])
base = int(lo_all // BIN) - 2; nb = int(hi_all // BIN) - base + 3
hist = {}
for d in B.days:
    diff = np.zeros(nb + 1)
    for m, o, h, l, c in one[d]:
        diff[int(l // BIN) - base] += 1; diff[int(h // BIN) - base + 1] -= 1
    hist[d] = np.cumsum(diff)[:nb]
PROF = {}
for i, d in enumerate(B.days):
    if i < 15 or d not in LV: continue
    p = sum(hist[x] for x in B.days[i - 15:i]); k = int(np.argmax(p)); tot = p.sum(); a = b = k; s = p[k]
    while s < 0.7 * tot:
        up = p[b + 1] if b + 1 < nb else -1; dn = p[a - 1] if a > 0 else -1
        if up >= dn: b += 1; s += up
        else: a -= 1; s += dn
    PROF[d] = ((base + k + 0.5) * BIN, (base + b + 1) * BIN, (base + a) * BIN)    # POC, VAH, VAL

# ---------------- 5-minute EMA 50, carried across days ----------------
EMA, ema, k = {}, None, 2 / 51
for d in B.days:
    vals = []
    for x in five[d]:
        ema = x[4] if ema is None else ema + k * (x[4] - ema); vals.append(ema)
    EMA[d] = vals
def ema_at(d, m):
    """EMA after the last 5-minute candle that closed at or before minute m."""
    j = (m - 555) // 5 - 1
    if j >= 0: return EMA[d][j]
    i = B.days.index(d); return EMA[B.days[i - 1]][-1]

def rel_bias(d):
    i = B.days.index(d)
    if B.days[i - 1] not in LV: return 0
    t, y = LV[d], LV[B.days[i - 1]]
    return 1 if t['bot'] > y['top'] else -1 if t['top'] < y['bot'] else 0

REL = {d: rel_bias(d) for d in TEST}

def sim(d, side, start, e, stp, tgt, mode, R):
    best = e
    for m, o, h, l, c in one[d]:
        if m < start: continue
        for px in path(o, h, l, c):
            if side * (px - stp) <= 0: return side * (stp - e) - COST, m
            if tgt is not None and side * (px - tgt) >= 0: return side * (tgt - e) - COST, m
        best = max(best, h) if side > 0 else min(best, l)
        if mode == 'ride' and side * (best - e) >= R: stp = e if side * (e - stp) > 0 else stp
        if mode == 'trail' and side * (best - e) >= R:
            ns = best - side * R
            if side * (ns - stp) > 0: stp = ns
        if m >= T_OUT: return side * (c - e) - COST, m
    return side * (one[d][-1][4] - e) - COST, one[d][-1][0]

def candidates(d, entry, orh, orl, after):
    """Breakouts of the 15-minute range in time order: (side, entry price, first exit-check minute, minute)."""
    if entry == 'close5':
        for x in five[d]:
            if x[0] < max(570, after) or x[0] + 5 > CUT: continue
            if x[4] > orh: yield 1, x[4], x[0] + 5, x[0] + 5
            elif x[4] < orl: yield -1, x[4], x[0] + 5, x[0] + 5
    else:
        for m, o, h, l, c in one[d]:
            if m < max(570, after) or m >= CUT: continue
            if h >= orh: yield 1, max(o, orh), m + 1, m
            elif l <= orl: yield -1, min(o, orl), m + 1, m

def day(d, P):
    cpr, poc, emaf, rel, wf, entry, stop, exitm, rev = P
    lv = LV[d]
    if not B.wid_ok(lv, wf): return []
    first = [x for x in one[d] if x[0] < 570]
    orh, orl = max(x[2] for x in first), min(x[3] for x in first)
    o = one[d][0][1]; cb = 1 if o > lv['top'] else -1 if o < lv['bot'] else 0
    for side, e, start, m in candidates(d, entry, orh, orl, 570):
        if cpr == 'agree' and side != cb: continue
        if cpr == 'notagainst' and side == -cb: continue
        if rel == 'notagainst' and side == -REL[d]: continue
        if emaf == 'agree' and side * (e - ema_at(d, m)) <= 0: continue
        if poc != 'none':
            pc, vah, val = PROF[d]
            ref = pc if poc == 'poc' else (vah if side > 0 else val)
            if side * (e - ref) <= 0: continue
        stp = (orl if side > 0 else orh) if stop == 'range' else (orh + orl) / 2 if stop == 'mid' else e - side * 0.002 * e
        R = side * (e - stp)
        if R <= 0: continue
        pnl, mx = sim(d, side, start, e, stp, e + side * 3 * R if exitm == '3R' else None, exitm, R)
        out = [(d, pnl, side, R)]
        if rev == 'yes' and pnl <= 0:                  # the break failed: take the other side's break after it
            out += day_after(d, P, -side, mx + 1, orh, orl)
        return out
    return []

def day_after(d, P, side_need, after, orh, orl):
    _, _, _, _, _, entry, stop, exitm, _ = P
    for side, e, start, m in candidates(d, entry, orh, orl, after):
        if side != side_need: continue
        stp = (orl if side > 0 else orh) if stop == 'range' else (orh + orl) / 2 if stop == 'mid' else e - side * 0.002 * e
        R = side * (e - stp)
        if R <= 0: continue
        pnl, mx = sim(d, side, start, e, stp, e + side * 3 * R if exitm == '3R' else None, exitm, R)
        return [(d, pnl, side, R)]
    return []

def study(ds, label):
    print(f"\n=== {label}: {len(ds)} sessions, {ds[0]} to {ds[-1]} ===")
    pc = lambda xs: f"{100 * sum(xs) / len(xs):.0f}%" if xs else '-'
    for s, nm in ((1, 'ABOVE'), (-1, 'BELOW')):
        a = [d for d in ds if s * (one[d][0][1] - (LV[d]['top'] if s > 0 else LV[d]['bot'])) > 0]
        cl = [s * (one[d][-1][4] - one[d][0][1]) > 0 for d in a]
        keep = [s * (one[d][-1][4] - (LV[d]['top'] if s > 0 else LV[d]['bot'])) > 0 for d in a]
        never = [(min(x[3] for x in one[d]) > LV[d]['p']) if s > 0 else (max(x[2] for x in one[d]) < LV[d]['p']) for d in a]
        print(f" A. opened {nm} the CPR: {len(a)} days. Closed {'higher' if s > 0 else 'lower'} than the open: {pc(cl)}. "
              f"Closed still {nm.lower()} the CPR: {pc(keep)}. Never touched the pivot P all day: {pc(never)}")
    res = collections.defaultdict(list)
    for d in ds:
        first = [x for x in one[d] if x[0] < 570]; orh, orl = max(x[2] for x in first), min(x[3] for x in first)
        o = one[d][0][1]; cb = 1 if o > LV[d]['top'] else -1 if o < LV[d]['bot'] else 0
        for side, e, start, m in candidates(d, 'close5', orh, orl, 570):
            R = side * (e - (orl if side > 0 else orh))
            later = [x for x in one[d] if x[0] >= start]
            end = side * (later[-1][4] - e) > 0 if later else False
            hits = {}
            for k in (1, 3):
                hits[k] = None
                for x in later:
                    lo_, hi_ = (x[3], x[2]) if side > 0 else (-x[2], -x[3])
                    ee = side * e
                    if lo_ <= ee - R: hits[k] = False; break
                    if hi_ >= ee + k * R: hits[k] = True; break
            for key in ('all', 'with CPR' if side == cb else 'against CPR' if side == -cb else 'open inside CPR'):
                res[key].append((end, bool(hits[1]), bool(hits[3])))
            break
    for key in ('all', 'with CPR', 'against CPR', 'open inside CPR'):
        r = res[key]
        if r: print(f" B. first 5-min close beyond the 15-min range, {key:15}: {len(r):3} days. Still that way at 3:30: {pc([x[0] for x in r])}. "
                    f"Reached 1R before the stop (other side of the range): {pc([x[1] for x in r])}. Reached 3R first: {pc([x[2] for x in r])}")

GRID = list(itertools.product(('none', 'agree', 'notagainst'), ('none', 'poc', 'va'), ('none', 'agree'), ('none', 'notagainst'),
                              ('any', 'narrow', 'notnarrow'), ('close5', 'touch'), ('range', 'mid', 0.2), ('3R', 'ride', 'trail'), ('no', 'yes')))

def evaluate(P):
    ts = [t for d in TEST for t in day(d, P)]
    daily = collections.defaultdict(float)
    for t in ts: daily[t[0]] += t[1]
    s90 = set(TEST[-90:])
    p90 = [t[1] for t in ts if t[0] in s90]; pall = [t[1] for t in ts]
    return dict(P=P, n90=len(p90), w90=sum(v > 0 for v in p90), net90=sum(p90), n=len(pall), w=sum(v > 0 for v in pall), net=sum(pall),
                win_pts=sum(v for v in p90 if v > 0), loss_pts=sum(v for v in p90 if v <= 0), daily=daily)

if __name__ == '__main__':
    L90 = TEST[-90:]
    study(L90, f'{B.name.upper()} LAST 90 SESSIONS')
    study(TEST, f'{B.name.upper()} EVERY SESSION SINCE 2023')
    import multiprocessing as mp
    with mp.Pool() as pool: res = pool.map(evaluate, GRID, chunksize=20)
    json.dump(res, open(f'../.cache/cpr_orb_{B.name}.json', 'w'))
    print(f"\n{len(GRID)} versions. Made money in the last 90 sessions: {sum(r['net90'] > 0 for r in res)}; also since 2023: "
          f"{sum(r['net90'] > 0 and r['net'] > 0 for r in res)}. Won 80%+ in the last 90 (10+ trades): {sum(r['n90'] >= 10 and r['w90'] >= 0.8 * r['n90'] for r in res)}")
    f = lambda r: f"last90 {r['n90']:3}tr {100*r['w90']/max(1,r['n90']):3.0f}% won {r['net90']:+7,.0f} | since 2023 {r['n']:4}tr {100*r['w']/max(1,r['n']):3.0f}% {r['net']:+8,.0f}"
    print("BEST 12 IN THE LAST 90 SESSIONS (15+ trades):")
    for r in sorted([r for r in res if r['n90'] >= 15], key=lambda r: -r['net90'])[:12]: print(f"  {str(r['P']):75} {f(r)}")
    print("HIGHEST WIN RATE IN THE LAST 90 (15+ trades):")
    for r in sorted([r for r in res if r['n90'] >= 15], key=lambda r: (-r['w90'] / r['n90'], -r['net90']))[:6]: print(f"  {str(r['P']):75} {f(r)}")

"""2026 only: the daily-plan indicator on Bitcoin (BTCUSDT futures, Binance), and what leverage does to Rs 30,000.

    python btc_2026.py

Bitcoin trades 24 hours, so a "session" here is a UTC day (Binance's daily candle, 5:30 am IST). Same rules as
tradingview/cpr_breakout.pine, translated:
  CPR from the previous UTC day; narrow = narrowest third of the last 20 days; today's CPR vs yesterday's.
  30-day volume POC from Bitcoin's own 1-minute volume (Bitcoin has real volume).
  Opening range = 00:00-00:15 UTC. No gap filter (Bitcoin has no overnight gap).
  Narrow day -> breakout scalp (touch of the range high / low, POC side, stop at the other side, book half at
  0.25R, stop to entry, trail the rest 1R behind the best price). Other day -> magnet at 00:01 if the first minute
  closes far enough beyond the CPR (POC side, book half at 0.25R, rest to the CPR edge), else the breakout.
Variants: entry window 45 minutes (like 9:30-10:00) or 2 hours; magnet sizes as on Nifty (0.2% beyond, 0.3% stop)
or 3x (Bitcoin moves about 3x as much as Nifty in a day); out after 6 hours (like 9:15-3:15) or at 23:45 UTC.
Costs: 0.05% a side taker fee + 0.01% slippage = 0.11% of the position per trade. Funding ignored (exits by
06:00 UTC avoid the 08:00 funding; the 23:45 version would pay about 0.01% at 08:00 and 16:00).
Leverage: liquidation when the price moves 1/leverage - 0.4% (maintenance margin) against the position.
"""
import collections, itertools, json, statistics as st
import numpy as np

COST = 0.0011
raw = json.load(open('../.cache/btc_1m.json'))
by = collections.defaultdict(list)
for k in sorted(raw):
    by[k[:10]].append((int(k[11:13]) * 60 + int(k[14:16]), *raw[k]))
days = [d for d in sorted(by) if len(by[d]) >= 1400]
IDX = {d: i for i, d in enumerate(days)}
DAY = {d: (by[d][0][1], max(x[2] for x in by[d]), min(x[3] for x in by[d]), by[d][-1][4]) for d in days}
D26 = [d for d in days if d >= '2026-01-01']
H1 = {d for d in D26 if d < '2026-07-01'}

def cpr(d):
    h, l, c = DAY[d][1:]
    p = (h + l + c) / 3; bc = (h + l) / 2; tc = 2 * p - bc
    return dict(p=p, top=max(tc, bc), bot=min(tc, bc), w=abs(tc - bc) / p)
LV = {}
for d in D26:
    i = IDX[d]; lv = cpr(days[i - 1]); y = cpr(days[i - 2])
    lv['narrow'] = sum(cpr(days[j - 1])['w'] < lv['w'] for j in range(i - 20, i)) * 3 < 20
    lv['rel'] = 1 if lv['bot'] > y['top'] else -1 if lv['top'] < y['bot'] else 0
    LV[d] = lv

BIN = 25.0
VH = {}
for d in days:
    lo = min(x[3] for x in by[d]); base = int(lo // BIN); h = np.zeros(int(max(x[2] for x in by[d]) // BIN) - base + 1)
    for m, o, hh, l, c, v in by[d]:
        a, b = int(l // BIN) - base, int(hh // BIN) - base; h[a:b + 1] += v / (b - a + 1)
    VH[d] = (base, h)
POC = {}
for d in D26:
    ds = days[IDX[d] - 30:IDX[d]]; base = min(VH[x][0] for x in ds); top = max(VH[x][0] + len(VH[x][1]) for x in ds)
    p = np.zeros(top - base)
    for x in ds: b0, h = VH[x]; p[b0 - base:b0 - base + len(h)] += h
    POC[d] = (base + int(np.argmax(p)) + 0.5) * BIN

def path(o, h, l, c): return (o, l, h, c) if c >= o else (o, h, l, c)

def run(d, side, start, e, stp, half_at, final, trail, tout):
    """Book half at half_at, stop to entry, then final target (magnet) or 1R trail (breakout). Returns pnl %, MAE %."""
    R = abs(e - stp); half = None; best = e; mae = 0.0
    for m, o, h, l, c, v in by[d]:
        if m < start: continue
        mae = max(mae, side * (e - (l if side > 0 else h)) / e)
        for px in path(o, h, l, c):
            if side * (px - stp) <= 0:
                rest = side * (stp - e) / e
                return (rest if half is None else (half + rest) / 2) - COST, mae, m
            if half is None and side * (px - half_at) >= 0:
                half = side * (half_at - e) / e
                if side * (e - stp) > 0: stp = e
            if half is not None and final is not None and side * (px - final) >= 0:
                return (half + side * (final - e) / e) / 2 - COST, mae, m
        if trail:
            best = max(best, h) if side > 0 else min(best, l)
            if side * (best - e) >= R:
                ns = best - side * R
                if side * (ns - stp) > 0: stp = ns
        if m >= tout:
            rest = side * (c - e) / e
            return (rest if half is None else (half + rest) / 2) - COST, mae, m
    c = by[d][-1][4]; rest = side * (c - e) / e
    return (rest if half is None else (half + rest) / 2) - COST, mae, by[d][-1][0]

def breakout(d, win, tout):
    bars = by[d]; first = [x for x in bars if x[0] < 15]; orh, orl = max(x[2] for x in first), min(x[3] for x in first)
    lv = LV[d]; poc = POC[d]; out = []; need = 0; after = 15
    for m, o, h, l, c, v in bars:
        if m < after or m >= 15 + win: continue
        side = 1 if h >= orh else -1 if l <= orl else 0
        if not side or (need and side != need): continue
        e = max(o, orh) if side > 0 else min(o, orl)
        if not need and side == -lv['rel']: continue
        if side * (e - poc) <= 0: continue
        stp = orl if side > 0 else orh; R = side * (e - stp)
        if R <= 0: continue
        pnl, mae, mx = run(d, side, m + 1, e, stp, e + side * 0.25 * R, None, True, tout)
        out.append((d, pnl, mae, abs(e - stp) / e))
        if need or pnl > 0: break
        need = -side; after = mx + 1
    return out

def magnet(d, k, tout):
    lv = LV[d]
    if lv['narrow']: return []
    m0, o, h, l, c, v = by[d][0]
    side = -1 if o > lv['top'] else 1 if o < lv['bot'] else 0
    if not side: return []
    edge = lv['top'] if side < 0 else lv['bot']
    if side * (edge - c) < 0.002 * k * c or side * (c - POC[d]) <= 0: return []
    R = 0.003 * k * c
    pnl, mae, _ = run(d, side, 1, c, c - side * R, c + side * 0.25 * R, edge, False, tout)
    return [(d, pnl, mae, 0.003 * k)]

def plan(d, win, k, tout):
    if LV[d]['narrow']: return breakout(d, win, tout)
    return magnet(d, k, tout) or breakout(d, win, tout)

def grow(ts, lev=None, risk=None):
    """Rs 30,000. lev: whole balance at that leverage. risk: risk this share of the balance per trade (stop-based)."""
    eq = 30000.0
    for d, pnl, mae, stop in ts:
        L = lev if lev else min(125.0, risk / stop)
        liq = 1 / L - 0.004
        if mae >= liq: return 0.0, d                      # liquidated: the margin is gone
        eq *= 1 + L * pnl
        if eq < 100: return eq, d
    return eq, None

if __name__ == '__main__':
    print(f"BTCUSDT 2026 ({D26[0]} to {D26[-1]}, {len(D26)} days; narrow-CPR days {sum(LV[d]['narrow'] for d in D26)})")
    best = None
    for win, k, tout in itertools.product((45, 120), (1, 3), (360, 1425)):
        ts = [t for d in D26 for t in plan(d, win, k, tout)]
        p = [t[1] for t in ts]; a = sum(t[1] for t in ts if t[0] in H1); b = sum(p) - a
        w = sum(v > 0 for v in p)
        print(f"  entries {win:3} min, magnet x{k}, out {'06:00' if tout == 360 else '23:45'}: {len(p):3} trades ({len(p)/9.3:.0f} a month), "
              f"{w} won / {len(p)-w} lost, total {100*sum(p):+.1f}% of price (Jan-Jun {100*a:+.1f}%, Jul-Oct {100*b:+.1f}%), "
              f"average {100*st.mean(p):+.3f}% a trade")
        if win == 45 and k == 1 and tout == 360: best = ts
    print("\n  Rs 30,000, entries 45 min, magnet x1, out 06:00 (the Nifty settings), trades compounded:")
    for lev in (1, 2, 3, 5, 10, 20, 50, 100, 125, 150):
        eq, bust = grow(best, lev=lev)
        print(f"    whole balance at {lev:3}x: Rs {eq:,.0f}" + (f"  (liquidated on {bust})" if bust else ''))
    for risk in (0.01, 0.02, 0.05):
        eq, bust = grow(best, risk=risk)
        Ls = [min(125, risk / t[3]) for t in best]
        print(f"    risk {int(risk*100)}% of the balance per trade (leverage {min(Ls):.1f}x-{max(Ls):.1f}x, set by the stop): Rs {eq:,.0f}"
              + (f"  (liquidated on {bust})" if bust else ''))

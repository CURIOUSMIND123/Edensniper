"""Bitcoin: why the calls hit the stop, what price does after it, and what to do about it (asked on 31 October 2026).
BTCUSDT perpetual, January 2024 - October 2026 (btc_data.py); target 450 / stop 150 points at $70,000 (0.64% / 0.21% of
the price), out after 24 hours, costs 0.06% a trade (42 points). Rules are judged on 2024-2025 and checked on 2026.

    python -I btc_stop_autopsy.py

The calls (the same rules as btc_scalp.py, UTC times; a 5-minute close is the signal, the entry is that close):
  ORB LDN    the London opening range 08:00-08:15; the first 5-minute close beyond it before 12:00 -> that way
             (the app's paper BTC calls)
  ORB NY     the same at 13:30-13:45, before 17:30
  PDH / PDL  yesterday's high / low swept and a 5-minute close back inside within an hour -> the other way
  ASIA       the 00:00-08:00 range swept between 08:00 and 20:00 and back inside within an hour -> the other way
  RANDOM     for comparison: one 5-minute close a day picked at random, BUY or SELL at random (the same each run)

1. AFTER THE STOP: of the calls that lost the stop, the share that came back to the entry within 24 hours of the call,
   and then went on to the target (a stop hunt); the share that never came back; how far beyond the stop price went
   first.
2. A WIDER STOP (target as now). 3. AVERAGING: half at the call, half when price is half way to the stop. 4. A PULLBACK
   ENTRY: a limit order 75 points better than the call for an hour, the stop and target prices as the call's. 5. AFTER A
   STOP: the opposite trade at the stop (stop and reverse), or the same trade again when price is back at the entry
   within 4 hours. 6. SIGNS AT THE ENTRY: the share of winners by what was known at the call.
"""
import collections, os, statistics as st, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import btc_data as B

D, REF, COST = B.D, B.REF, B.COST
TP, SL = 450, 150
M, O, H, L, C, V, TB, OI, FUND, TOP = (D[k] for k in ('m', 'o', 'h', 'l', 'c', 'v', 'tb', 'oi', 'fund', 'top'))
PER = (('2024', lambda y: y == 2024), ('2025', lambda y: y == 2025), ('2026', lambda y: y == 2026))

# ---------------- 5-minute candles ----------------
g = M // 5
st5 = np.flatnonzero(np.r_[True, g[1:] != g[:-1]])
en5 = np.r_[st5[1:], len(g)] - 1
full = (en5 - st5) == 4
B5 = dict(s=(g[st5] * 5)[full], o=O[st5][full], h=np.maximum.reduceat(H, st5)[full], l=np.minimum.reduceat(L, st5)[full],
          c=C[en5][full], v=np.add.reduceat(V, st5)[full], tb=np.add.reduceat(TB, st5)[full], last=en5[full])
N5 = len(B5['s'])
DAY = B5['s'] // 1440
TOD = B5['s'] % 1440

# yesterday's high / low and the Asia range for each UTC day
dg = M // 1440
dst = np.flatnonzero(np.r_[True, dg[1:] != dg[:-1]])
DHI = dict(zip(dg[dst], np.maximum.reduceat(H, dst)))
DLO = dict(zip(dg[dst], np.minimum.reduceat(L, dst)))
asia = (M % 1440) < 480
ag = dg[asia]
ast = np.flatnonzero(np.r_[True, ag[1:] != ag[:-1]])
AHI = dict(zip(ag[ast], np.maximum.reduceat(H[asia], ast)))
ALO = dict(zip(ag[ast], np.minimum.reduceat(L[asia], ast)))

# typical size of a 5-minute candle's volume at each time of day over the 20 days before (for the signs)
VOLMED = {}
by = collections.defaultdict(list)
for j in range(N5):
    by[TOD[j]].append((DAY[j], B5['v'][j]))
for tod, xs in by.items():
    for k, (d, v) in enumerate(xs):
        prev = [x[1] for x in xs[max(0, k - 20):k]]
        if len(prev) >= 10:
            VOLMED[(d, tod)] = st.median(prev)

def orb(m0, until, name):
    out, rng, done = [], {}, set()
    for j in range(N5):
        d, t = DAY[j], TOD[j]
        if m0 <= t < m0 + 15:
            r = rng.get(d)
            rng[d] = (max(r[0], B5['h'][j]), min(r[1], B5['l'][j])) if r else (B5['h'][j], B5['l'][j])
        elif m0 + 15 <= t < until and d in rng and d not in done:
            hi, lo = rng[d]
            c = B5['c'][j]
            if c > hi or c < lo:
                out.append(dict(j=j, side=1 if c > hi else -1, src=name, width=(hi - lo) / c * REF))
                done.add(d)
    return out

def sweeps(levels, name, h0=0, h1=24):
    out, armed = [], {}
    for j in range(N5):
        t = TOD[j]
        if not (h0 * 60 <= t < h1 * 60):
            armed.clear()
            continue
        s, h, l, c = B5['s'][j], B5['h'][j], B5['l'][j], B5['c'][j]
        for p, side in levels(DAY[j]):
            key = (round(p, 1), side)
            if key not in armed and ((side < 0 and h > p) or (side > 0 and l < p)):
                armed[key] = s
            if key in armed and armed[key] != -1 and s - armed[key] <= 60 and ((side < 0 and c < p) or (side > 0 and c > p)):
                out.append(dict(j=j, side=side, src=name))
                armed[key] = -1
    return out

def pdh(d):
    return [(DHI[d - 1], -1), (DLO[d - 1], 1)] if d - 1 in DHI else []

def asia_lv(d):
    return [(AHI[d], -1), (ALO[d], 1)] if d in AHI else []

def pts(i, side, x):
    """The move from the close of 1-minute candle i to price x, in points at $70,000, the trade's way."""
    return side * (x - C[i]) / C[i] * REF

def trade_from(i, e, side, tgt_px, stp_px, n=1440):
    """Entry price e after candle i; out at the target / stop prices or after n minutes -> (kind, exit index, points)."""
    h, l = H[i + 1:i + 1 + n], L[i + 1:i + 1 + n]
    if not len(h):
        return 'time', i, 0.0
    win = (h >= tgt_px) if side > 0 else (l <= tgt_px)
    los = (l <= stp_px) if side > 0 else (h >= stp_px)
    jw = int(np.argmax(win)) if win.any() else 10 ** 9
    jl = int(np.argmax(los)) if los.any() else 10 ** 9
    k = REF / e
    if jl <= jw and jl < 10 ** 9:
        return 'loss', i + 1 + jl, side * (stp_px - e) * k - COST
    if jw < 10 ** 9:
        return 'win', i + 1 + jw, side * (tgt_px - e) * k - COST
    return 'time', i + len(h), side * (C[i + len(h)] - e) * k - COST

def study(calls):
    rows = []
    for x in calls:
        j, side = x['j'], x['side']
        i = B5['last'][j]
        e = C[i]
        if i + 1440 >= len(C):
            continue
        u = e / REF
        tgt, stp = e + side * TP * u, e - side * SL * u
        r = dict(x, i=i, e=e, year=B.when(M[i]).year)
        r['kind'], ex, r['pnl'] = trade_from(i, e, side, tgt, stp)
        r['win'] = r['kind'] == 'win'
        # 1. after the stop
        if r['kind'] == 'loss':
            end = i + 1440
            seg_h, seg_l = H[ex + 1:end], L[ex + 1:end]
            back = np.flatnonzero((seg_h >= e) if side > 0 else (seg_l <= e))
            r['back'] = len(back) > 0
            upto = ex + 1 + (back[0] if r['back'] else len(seg_h))
            worst = (L[ex:upto].min() if side > 0 else H[ex:upto].max())
            r['beyond'] = side * (stp - worst) / e * REF
            r['hunt'] = bool(r['back'] and ((H[upto:end] >= tgt).any() if side > 0 else (L[upto:end] <= tgt).any()))
            # 5. stop and reverse: the other way from the stop price
            k2, _, p2 = trade_from(ex, stp, -side, stp - side * TP * u, stp + side * SL * u)
            r['reverse'] = p2
            # 5. the same trade again when price is back at the entry within 4 hours of the stop
            b4 = np.flatnonzero((H[ex + 1:ex + 241] >= e) if side > 0 else (L[ex + 1:ex + 241] <= e))
            r['again'] = trade_from(ex + 1 + b4[0], e, side, tgt, stp)[2] if len(b4) else 0.0
        # 2. a wider stop
        r['wide'] = {w: trade_from(i, e, side, tgt, e - side * (SL + w) * u)[2] for w in (0, 50, 100, 150, 300)}
        # 3. averaging: the second half at half way to the stop
        half = e - side * 0.5 * SL * u
        k, ex1, p = trade_from(i, e, side, tgt, half)
        if k == 'loss':
            k2, ex2, p2 = trade_from(ex1, half, side, tgt, stp, 1440 - (ex1 - i))
            p1 = side * ((tgt if k2 == 'win' else stp if k2 == 'loss' else C[ex2]) - e) / e * REF - COST
            r['avg'] = 0.5 * p1 + 0.5 * p2
        else:
            r['avg'] = 0.5 * p
        # 4. a pullback entry 75 points better, for an hour
        lim = e - side * 75 * u
        f = np.flatnonzero((L[i + 1:i + 61] <= lim) if side > 0 else (H[i + 1:i + 61] >= lim))
        hit_t = np.flatnonzero((H[i + 1:i + 61] >= tgt) if side > 0 else (L[i + 1:i + 61] <= tgt))
        if len(f) and not (len(hit_t) and hit_t[0] < f[0]):
            r['pull_fill'] = True
            r['pull'] = trade_from(i + 1 + f[0], lim, side, tgt, stp, 1440 - f[0] - 1)[2]
        else:
            r['pull_fill'], r['pull'] = False, 0.0
        # 6. signs at the entry
        s, tod = B5['s'][j], TOD[j]
        r['hour'] = f"{tod // 60:02d}:00 UTC"
        r['dow'] = 'weekend' if B.when(s).weekday() >= 5 else 'weekday'
        vm = VOLMED.get((DAY[j], tod))
        r['vol'] = ('signal candle volume n/a' if not vm else 'volume 2x+ usual' if B5['v'][j] >= 2 * vm else
                    'volume 1-2x usual' if B5['v'][j] >= vm else 'volume under usual')
        tbs = B5['tb'][j] / B5['v'][j] if B5['v'][j] else 0.5
        tbs = tbs if side > 0 else 1 - tbs
        r['flow'] = 'aggressive orders 60%+ its way' if tbs >= 0.6 else 'aggressive orders 50-60% its way' if tbs >= 0.5 else 'aggressive orders against'
        r24 = pts(i - 1440, side, e) if i >= 1440 else 0
        r['trend'] = 'last 24h moved 1%+ its way' if r24 >= 700 else 'last 24h moved 1%+ against' if r24 <= -700 else 'last 24h flat (under 1%)'
        oi4 = (OI[i] / OI[i - 240] - 1) * 100 if i >= 240 and OI[i - 240] > 0 else np.nan
        r['oi'] = ('open interest n/a' if np.isnan(oi4) else 'open interest up 1%+ in 4h' if oi4 >= 1 else
                   'open interest down 1%+ in 4h' if oi4 <= -1 else 'open interest flat 4h')
        fr = FUND[i] * 100
        r['fund'] = ('funding n/a' if np.isnan(fr) else 'funding high (crowded longs)' if fr >= 0.02 else
                     'funding negative (crowded shorts)' if fr < 0 else 'funding normal')
        r['fund_side'] = r['fund'] if 'normal' in r['fund'] or 'n/a' in r['fund'] else (
            r['fund'] + (' - call against the crowd' if (fr > 0) != (side > 0) else ' - call with the crowd'))
        tp4 = TOP[i] - TOP[i - 240] if i >= 240 else np.nan
        r['top'] = ('top traders n/a' if np.isnan(tp4) else 'top traders turned more long' if tp4 >= 0.05 else
                    'top traders turned more short' if tp4 <= -0.05 else 'top traders unchanged')
        r['top_side'] = r['top'] if 'n/a' in r['top'] or 'unchanged' in r['top'] else r['top'] + (
            ' (with the call)' if (tp4 > 0) == (side > 0) else ' (against the call)')
        if 'width' in x:
            r['width'] = 'opening range under 150' if x['width'] < 150 else 'opening range 150-300' if x['width'] < 300 else 'opening range 300+'
        r['side_name'] = 'BUY' if side > 0 else 'SELL'
        rows.append(r)
    return rows

def pct(n, d):
    return f"{round(100 * n / d):3}%" if d else '  - '

def report(name, rows):
    print(f"\n=== {name}: {len(rows)} calls ===")
    for per, f in PER:
        cs = [r for r in rows if f(r['year'])]
        if not cs:
            continue
        ls = [r for r in cs if r['kind'] == 'loss']
        print(f"  {per}: {len(cs)} calls, won {pct(sum(r['win'] for r in cs), len(cs))}, {sum(r['pnl'] for r in cs):+8,.0f} points; "
              f"{len(ls)} stops")
        if ls:
            b = sorted(r['beyond'] for r in ls)
            print(f"    1. after the stop: back to the entry {pct(sum(r['back'] for r in ls), len(ls))}, then the target "
                  f"{pct(sum(r['hunt'] for r in ls), len(ls))} (stop hunts), never back {pct(sum(not r['back'] for r in ls), len(ls))}; "
                  f"beyond the stop first: median {st.median(b):.0f}, 75% under {b[3 * len(b) // 4]:.0f} points")
        print("    2. stop wider by:  " + "  ".join(f"+{w}: {pct(sum(r['wide'][w] > 0 for r in cs), len(cs))} {sum(r['wide'][w] for r in cs):+7,.0f}"
                                            for w in (0, 50, 100, 150, 300)))
        win, los = [r for r in cs if r['win']], [r for r in cs if not r['win']]
        print(f"    3. averaging {sum(r['avg'] for r in cs):+7,.0f} against {sum(r['pnl'] for r in cs):+7,.0f};  "
              f"4. pullback entry (75 better): fills {pct(sum(r['pull_fill'] for r in win), len(win))} of winners, "
              f"{pct(sum(r['pull_fill'] for r in los), len(los))} of the others, {sum(r['pull'] for r in cs):+7,.0f}")
        if ls:
            print(f"    5. after a stop: stop and reverse {sum(r['reverse'] for r in ls):+7,.0f} "
                  f"(won {pct(sum(r['reverse'] > 0 for r in ls), len(ls))}); the same trade again at the entry "
                  f"{sum(r['again'] for r in ls):+7,.0f} ({sum(r['again'] != 0 for r in ls)} trades)")

def signs(rows):
    print("\n  6. SIGNS AT THE ENTRY (won % = the target before the stop; 2024-2025 | 2026; groups of 10+ calls)")
    for key in ('side_name', 'hour', 'dow', 'width', 'vol', 'flow', 'trend', 'oi', 'fund_side', 'top_side'):
        keys = sorted({r.get(key) for r in rows if r.get(key)})
        for k in keys:
            a = [r for r in rows if r.get(key) == k and r['year'] < 2026]
            b = [r for r in rows if r.get(key) == k and r['year'] == 2026]
            if len(a) + len(b) < 10:
                continue
            print(f"     {k:44} {pct(sum(r['win'] for r in a), len(a))} ({len(a):3}) {sum(r['pnl'] for r in a):+7,.0f} | "
                  f"{pct(sum(r['win'] for r in b), len(b))} ({len(b):3}) {sum(r['pnl'] for r in b):+7,.0f}")

def random_calls():
    rs = np.random.default_rng(7)
    out = []
    for d in np.unique(DAY):
        js = np.flatnonzero(DAY == d)
        out.append(dict(j=int(rs.choice(js)), side=int(rs.choice((1, -1))), src='RANDOM'))
    return out

CALLS = {'ORB LDN': orb(480, 720, 'ORB LDN'), 'ORB NY': orb(810, 1050, 'ORB NY'),
         'PDH / PDL': sweeps(pdh, 'PDH / PDL'), 'ASIA': sweeps(asia_lv, 'ASIA', 8, 20), 'RANDOM': random_calls()}
ROWS = {k: study(v) for k, v in CALLS.items()}

if __name__ == '__main__':
    print(f"BTCUSDT perpetual {B.when(M[0]):%Y-%m-%d} - {B.when(M[-1]):%Y-%m-%d}; target {TP} / stop {SL} points at $70,000; "
          f"points after costs")
    for k, rows in ROWS.items():
        report(k, rows)
    allr = [r for k, rows in ROWS.items() if k != 'RANDOM' for r in rows]
    report('ALL FOUR TOGETHER', allr)
    print("\n--- ORB LDN (the app's calls) ---")
    signs(ROWS['ORB LDN'])
    print("\n--- ALL FOUR TOGETHER ---")
    signs(allr)

"""Why calls hit the stop, and what happens after (asked on 31 October 2026). All the alert program's calls (default
settings and the extra calls), 2023-2026, 1-minute candles; costs 4 / 12 points.

    python stop_autopsy.py nifty        (or sensex)

1. AFTER THE STOP: each call that lost its full stop - did price come back to the entry later that day and reach the
   call's T1 (a stop hunt), come back without reaching T1, or never come back (a real reversal)? How far beyond the stop
   did it go first?
2. A WIDER STOP: the same calls, all out at T1 or the stop (no booking half), with the stop as now and X points wider.
3. AVERAGING: half at the call, the other half when price has gone half way to the stop (stop and T1 as now), against
   the whole position at the call.
4. SIGNS AT THE ENTRY: the share of calls that reached the success move (50 Nifty / 150 Sensex points before the stop,
   as the app's history counts it) by time of day, the day's trend, CPR width, the opening gap, how far the day had
   already moved, RSI 14 (5-minute) and the kind of call; 2023-2025 and 2026 apart. Added after the Bitcoin test
   (btc_signs.py: the size of the next move can be foreseen there, its direction not): the day's range so far against
   its usual size by that minute (the median of the 20 days before) and yesterday's range against usual.
"""
import collections, statistics as st, sys
import levels_style as LS
import weekly_cpr as WK

A = LS.A
NM, COST = LS.NM, LS.COST
NEED = {'nifty': 50, 'sensex': 150}[NM]
WIDER = {'nifty': (10, 20, 30, 50), 'sensex': (30, 60, 100, 150)}[NM]
LS.extras(True)

def rsi14(closes):
    if len(closes) < 15:
        return None
    g = [max(b - a, 0) for a, b in zip(closes, closes[1:])][-14:]
    l = [max(a - b, 0) for a, b in zip(closes, closes[1:])][-14:]
    return 100 if sum(l) == 0 else 100 - 100 / (1 + sum(g) / sum(l))

def first(c1, start, side, e, up, down, last=A.OUT):
    """Which comes first from minute start: +up the call's way ('win'), -down against ('loss'), or neither by `last`."""
    for m, o, h, l, c in c1:
        if m < start:
            continue
        if side * ((l if side > 0 else h) - e) <= -down:
            return 'loss', m
        if side * ((h if side > 0 else l) - e) >= up:
            return 'win', m
        if m >= last:
            return 'time', m
    return 'time', c1[-1][0]

def close_at(c1, m):
    return next((x[4] for x in c1 if x[0] >= m), c1[-1][4])

DRANGE = {d: max(x[2] for x in LS.sess[d]) - min(x[3] for x in LS.sess[d]) for d in LS.DAYS}

def range_by(d, m):
    xs = [x for x in LS.sess[d] if x[0] < m]
    return (max(x[2] for x in xs) - min(x[3] for x in xs)) if xs else None

CALLS = []
for n_d, d in enumerate(LS.DAYS):
    cx, c1 = LS.CX[d], LS.sess[d]
    for t in A.day_trades(cx, c1, 929, True, False, 'classic'):
        if not (t['taken'] and t['exit']):
            continue
        sd, e, stp = t['side'], t['e'], t['stp0']
        risk = sd * (e - stp)
        t1 = A.half_price(t) or e + sd * NEED          # SECOND CHANCE has no target: the success move
        if risk <= 0 or sd * (t1 - e) <= 0:
            continue
        r = dict(d=d, t=t, side=sd, e=e, risk=risk, t1=t1, src=t['src'], m=t['m'], known=t['known'])
        r['success'] = first(c1, t['known'], sd, e, NEED, risk, 929)[0] == 'win'
        r['full_stop'] = t['exit']['why'] == 'stop' and t['exit']['pnl'] < -COST - 0.5 * risk
        if r['full_stop']:
            ms = t['exit']['m']
            after = [x for x in c1 if x[0] > ms]
            back = next((x[0] for x in after if sd * ((x[2] if sd > 0 else x[3]) - e) >= 0), None)
            seg = [x for x in after if back is None or x[0] <= back]
            r['beyond'] = max([sd * (stp - (x[3] if sd > 0 else x[2])) for x in seg] or [0])
            r['back'] = back is not None
            r['t1_after'] = back is not None and any(sd * ((x[2] if sd > 0 else x[3]) - t1) >= 0 for x in after if x[0] >= back)
        # 2. all out at T1 or the stop, as now and wider
        r['fixed'] = {}
        for w in (0,) + WIDER:
            k, mx = first(c1, t['known'], sd, e, sd * (t1 - e), risk + w)
            r['fixed'][w] = (sd * (t1 - e) if k == 'win' else -(risk + w) if k == 'loss' else sd * (close_at(c1, mx) - e)) - COST
        # 3. averaging: half now, half at half way to the stop
        k, mx = first(c1, t['known'], sd, e, sd * (t1 - e), 0.5 * risk)
        if k == 'loss':                              # the second half filled at e - 0.5 risk
            e2 = e - sd * 0.5 * risk
            k2, mx2 = first(c1, mx + 1, sd, e2, sd * (t1 - e2), 0.5 * risk)
            p2 = sd * (t1 - e2) if k2 == 'win' else -0.5 * risk if k2 == 'loss' else sd * (close_at(c1, mx2) - e2)
            p1 = sd * (t1 - e) if k2 == 'win' else -risk if k2 == 'loss' else sd * (close_at(c1, mx2) - e)
            r['avg'] = 0.5 * p1 + 0.5 * p2 - COST
        else:                                        # only the first half
            r['avg'] = 0.5 * ((sd * (t1 - e)) if k == 'win' else sd * (close_at(c1, mx) - e)) - COST / 2
        # 4. signs at the entry
        am = [x for x in c1 if x[0] < t['known']]
        o0 = c1[0][1]
        r['hour'] = f"{t['m'] // 60:02d}:{'00' if t['m'] % 60 < 30 else '30'}"
        tn = A.trend_now(cx, am, t['known'] - 1) if am else None
        r['trend'] = 'no trend' if not tn or not tn['dir'] else 'with the trend' if tn['dir'] == sd else 'against the trend'
        r['cpr'] = 'narrow' if cx['narrow'] else 'wide' if cx['rank'] >= 2 / 3 else 'normal'
        g = (o0 - cx['yc']) / cx['yc'] * 100
        r['gap'] = 'gap with the call' if g * sd > 0.25 else 'gap against the call' if g * sd < -0.25 else 'small gap'
        moved = sd * (am[-1][4] - o0) / o0 * 100 if am else 0
        r['moved'] = ('already moved 0.5%+ its way' if moved >= 0.5 else 'moved 0.2-0.5% its way' if moved >= 0.2 else
                      'moved under 0.2% either way' if moved > -0.2 else 'moved 0.2%+ the other way')
        cl5 = [b[4] for b in WK.blocks5(am)] if am else []
        rs = rsi14(cx.get('c5h', [])[-30:] + cl5)
        r['rsi'] = 'RSI n/a' if rs is None else ('RSI stretched its way (70+/30-)' if (rs >= 70 if sd > 0 else rs <= 30) else
                                               'RSI against (under 50 for a BUY)' if (rs < 50 if sd > 0 else rs > 50) else 'RSI 50-70 its way')
        prev = LS.DAYS[max(0, n_d - 20):n_d]
        so_far = range_by(d, t['known'])
        usual = st.median([v for v in (range_by(p, t['known']) for p in prev) if v]) if len(prev) >= 10 else None
        r['range_now'] = ('range so far n/a' if not (so_far and usual) else 'range so far 1.5x+ usual' if so_far >= 1.5 * usual else
                          'range so far under 0.7x usual' if so_far < 0.7 * usual else 'range so far usual')
        yu = st.median(DRANGE[p] for p in prev[:-1]) if len(prev) >= 10 else None
        yd = DRANGE[prev[-1]] if prev else None
        r['range_y'] = ('yesterday n/a' if not (yu and yd) else 'yesterday 1.5x+ usual range' if yd >= 1.5 * yu else
                        'yesterday under 0.7x usual range' if yd < 0.7 * yu else 'yesterday usual range')
        CALLS.append(r)

def pct(n, d):
    return f"{round(100 * n / d):3}%" if d else '  - '

if __name__ == '__main__':
    for per, f in (('2023-2025', lambda d: d < '2026'), ('2026', lambda d: d >= '2026')):
        cs = [r for r in CALLS if f(r['d'])]
        fs = [r for r in cs if r['full_stop']]
        print(f"\n{NM.upper()} {per}: {len(cs)} calls, {sum(r['success'] for r in cs)} reached {NEED} points before the stop "
              f"({pct(sum(r['success'] for r in cs), len(cs))}); {len(fs)} lost the full stop")
        print("  1. AFTER THE STOP (the calls that lost the full stop):")
        if fs:
            print(f"     came back to the entry later that day: {pct(sum(r['back'] for r in fs), len(fs))}; and went on to T1: "
                  f"{pct(sum(r['t1_after'] for r in fs), len(fs))} (the stop hunts); never came back: {pct(sum(not r['back'] for r in fs), len(fs))}")
            b = sorted(r['beyond'] for r in fs)
            print(f"     how far beyond the stop before turning (or the close): median {st.median(b):.0f}, 25% under "
                  f"{b[len(b) // 4]:.0f}, 75% under {b[3 * len(b) // 4]:.0f} points; average stop {st.mean(r['risk'] for r in fs):.0f}")
            for k, g in sorted(collections.Counter(r['src'] for r in fs).items()):
                sub = [r for r in fs if r['src'] == k]
                print(f"       {k:14} {g:3} stops: back to the entry {pct(sum(r['back'] for r in sub), g)}, then T1 {pct(sum(r['t1_after'] for r in sub), g)}")
        print("  2. ALL OUT AT T1 OR THE STOP: the stop as now and wider (won %, net points)")
        for w in (0,) + WIDER:
            p = [r['fixed'][w] for r in cs]
            print(f"     stop {'as now' if not w else '+' + str(w) + ' points':12} {pct(sum(x > 0 for x in p), len(p))} {sum(p):+8,.0f}")
        p0, pa = [r['fixed'][0] for r in cs], [r['avg'] for r in cs]
        print(f"  3. AVERAGING (half now, half half way to the stop; T1 / stop as now): {pct(sum(x > 0 for x in pa), len(pa))} won "
              f"{sum(pa):+,.0f} points (in whole-position units) against the whole position at the call {sum(p0):+,.0f}")
        print(f"  4. SIGNS AT THE ENTRY (share reaching {NEED} points before the stop; calls):")
        for key in ('src', 'hour', 'trend', 'cpr', 'gap', 'moved', 'rsi', 'range_now', 'range_y'):
            groups = collections.defaultdict(list)
            for r in cs:
                groups[r[key]].append(r['success'])
            print('     ' + ' | '.join(f"{k} {pct(sum(v), len(v))} ({len(v)})" for k, v in sorted(groups.items()) if len(v) >= 5))

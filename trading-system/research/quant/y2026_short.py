"""2026 only: the indicator with small stops, short holding times and plain targets (no trailing).

    python y2026_short.py nifty        (or sensex)

Same signals as the indicator (daily plan: CPR Magnet / CPR Breakout; plus 3-day volume lines; one trade at a time),
with different risk rules:
  cap      the most a stop may be from entry: Sensex 100 / 150 points, Nifty 30 / 45 (about the same % of price);
           none = the indicator's own stops (0.3% for Magnet, the other side of the 15-minute range for Breakout,
           the previous volume line)
  mode     tighten (move a wider stop in to the cap) / skip (don't take trades whose stop is wider than the cap)
  hold     out after 15 / 30 / 60 minutes at the latest, or only at 3:15
  exit     half+target (book half at 0.25R, stop to entry, rest at the target) / target (all at the target) /
           1R / 1.5R / 2R (all at that multiple of the stop distance). Target = the CPR edge (Magnet), the next
           volume line (volume lines), 1R (Breakout, which has no level target). No trailing stop anywhere.
  again    Breakout: after a trade closes, take the next touch of the 15-minute high / low that passes the same
           filters, until 10:00 (as well as the one reversal after a loss)
Volume-line trades need the next line at least 1.5x the (capped) stop away. Costs 4 Nifty / 12 Sensex points.
January-June and July-9 October 2026 shown separately.
"""
import collections, itertools, json, sys
import y2026 as Y, y2026_combo as K, y2026_vol_lines as V, cpr_orb as C, cpr_orb_winrate as W, y2026_improve as I

one, five, LV, COST, D26, H1, NM = Y.one, Y.five, Y.LV, Y.COST, Y.D26, Y.H1, Y.B.name
CAPS = {'nifty': (30, 45), 'sensex': (100, 150)}[NM]
path = I.path

def walk(d, side, e, start, stp, tgt, half_at, last_m):
    """Exits on 1-minute candles: stop, book half (stop to entry), target, time limit (close of minute last_m), 3:15."""
    half = None
    for m, o, h, l, c in one[d]:
        if m < start: continue
        for px in path(o, h, l, c):
            if side * (px - stp) <= 0:
                rest = side * (stp - e)
                return (rest if half is None else (half + rest) / 2) - COST, m, 'stop' if half is None else 'stop at entry'
            if half_at is not None and half is None and side * (px - half_at) >= 0:
                half = side * (half_at - e); stp = e
            if (half_at is None or half is not None) and side * (px - tgt) >= 0:
                return (side * (tgt - e) if half is None else (half + side * (tgt - e)) / 2) - COST, m, 'target'
        if m >= min(last_m, 915):
            rest = side * (c - e)
            return (rest if half is None else (half + rest) / 2) - COST, m, 'time' if m < 915 else '3:15'
    rest = side * (one[d][-1][4] - e)
    return (rest if half is None else (half + rest) / 2) - COST, one[d][-1][0], '3:15'

def levels(side, e, stp0, tgt_main, P):
    """Stop, target and book-half level under rules P, or None if the trade is skipped."""
    cap, mode, hold, ex, again = P
    if side * (e - stp0) <= 0: return None
    stp = stp0
    if cap and side * (e - stp0) > cap:
        if mode == 'skip': return None
        stp = e - side * cap
    R = side * (e - stp)
    if tgt_main is None: tgt_main = e + side * R
    if ex in ('half+target', 'target'):
        tgt, half = tgt_main, (e + side * 0.25 * R if ex == 'half+target' else None)
    else:
        tgt, half = e + side * float(ex[:-1]) * R, None
    if side * (tgt - e) <= 0: return None
    return stp, tgt, half

def trade(d, src, side, e, start, m, stp0, tgt_main, P):
    L = levels(side, e, stp0, tgt_main, P)
    if L is None: return None
    stp, tgt, half = L
    last_m = start - 1 + P[2] if P[2] else 915
    pnl, mx, why = walk(d, side, e, start, stp, tgt, half, last_m)
    return dict(d=d, src=src, side=side, m=m, mx=mx, pnl=pnl, why=why, risk=side * (e - stp))

def magnet(d, P):
    lv = LV[d]
    if lv['rank'] < 1 / 3: return None
    o, e = one[d][0][1], one[d][0][4]
    side = -1 if o > lv['top'] else 1 if o < lv['bot'] else 0
    if not side: return None
    edge = lv['top'] if side < 0 else lv['bot']
    if side * (edge - e) < 0.002 * e or side * (e - Y.PROF30[d]['poc']) <= 0: return None
    t = trade(d, 'MAG', side, e, 556, 556, e - side * 0.003 * e, edge, P)
    return [t] if t else None

def breakout(d, P):
    first = [x for x in one[d] if x[0] < 570]; orh, orl = max(x[2] for x in first), min(x[3] for x in first)
    gap, poc, rel = W.FEAT[d]['gap'], Y.PROF30[d]['poc'], C.REL[d]
    out, after, last = [], 570, None
    while True:
        got = None
        for side, e, start, m in C.candidates(d, 'touch', orh, orl, after):
            if m >= 600: break
            normal = side != -rel and gap == side and side * (e - poc) > 0
            reverse = last is not None and last['pnl'] <= 0 and len(out) == 1 and side == -last['side'] and side * (e - poc) > 0
            if not (reverse or (normal and (not out or P[4]))): continue
            got = trade(d, 'BO', side, e, start, m, orl if side > 0 else orh, None, P)
            if got: break
        if not got: break
        out.append(got); last = got; after = got['mx'] + 1
        if not P[4] and (len(out) >= 2 or got['pnl'] > 0): break
    return out

def plan(d, P):
    if LV[d]['rank'] < 1 / 3: return breakout(d, P)
    return magnet(d, P) or breakout(d, P)

def vol(d, P):
    lv = V.LINES[(d, 3)]; b5 = five[d]; out = []; free = 0
    for j in range(1, len(b5)):
        m0, o, h, l, c = b5[j]; pc = b5[j - 1][4]
        if m0 < 570 or m0 + 5 > 870 or m0 < free: continue
        for x in lv:
            side = 1 if pc < x <= c else -1 if pc > x >= c else 0
            if not side: continue
            nxt = sorted((y for y in lv if side * (y - x) > 0), key=lambda y: abs(y - x))
            prv = [y for y in lv if side * (x - y) > 0]
            if not nxt or not prv: break
            stp0 = max(prv) if side > 0 else min(prv); e = c
            risk = side * (e - stp0)
            if P[0] and risk > P[0]:
                if P[1] == 'skip': break
                risk = P[0]
            if risk <= 0 or side * (nxt[0] - e) < 1.5 * risk: break
            t = trade(d, 'VOL', side, e, m0 + 5, m0 + 5, stp0, nxt[0], P)
            if t: out.append(t); free = t['mx'] + 1
            break
    return out

def one_book(ts):
    out = []; free = collections.defaultdict(int)
    for t in sorted(ts, key=lambda t: (t['d'], t['m'], t['src'] == 'VOL')):
        if t['m'] >= free[t['d']]: out.append(t); free[t['d']] = t['mx'] + 1
    return out

GRID = [P for P in itertools.product((0,) + CAPS, ('tighten', 'skip'), (0, 15, 30, 60), ('half+target', 'target', '1R', '1.5R', '2R'), (False, True))
        if not (P[0] == 0 and P[1] == 'skip')]

def run(P):
    ts = one_book([t for d in D26 for t in plan(d, P)] + [t for d in D26 for t in vol(d, P)])
    p = [t['pnl'] for t in ts]; a = sum(t['pnl'] for t in ts if t['d'] in H1)
    eq = pk = dd = 0
    for v in p: eq += v; pk = max(pk, eq); dd = min(dd, eq - pk)
    w = [v for v in p if v > 0]; l = [v for v in p if v <= 0]
    return dict(P=list(P), n=len(p), w=len(w), won=sum(w), lost=sum(l), net=sum(p), a=a, b=sum(p) - a, dd=dd,
                worst=min(p) if p else 0, avg_w=sum(w) / max(1, len(w)), avg_l=sum(l) / max(1, len(l)),
                hold=sum(t['mx'] - t['m'] for t in ts) / max(1, len(ts)),
                risk=sum(t['risk'] for t in ts) / max(1, len(ts)), why=dict(collections.Counter(t['why'] for t in ts)))

def show(r, label=None):
    print(f"  {label or str(r['P']):46} {r['n']:4} tr ({r['n'] / 9.3:4.1f}/mo) {100 * r['w'] / max(1, r['n']):3.0f}% won | avg win {r['avg_w']:+5.0f} "
          f"avg loss {r['avg_l']:+5.0f} worst {r['worst']:+5.0f} | stop {r['risk']:4.0f} hold {r['hold']:3.0f}m | net {r['net']:+7,.0f} "
          f"(Jan-Jun {r['a']:+6,.0f}, Jul-Oct {r['b']:+6,.0f}) fall {r['dd']:6,.0f}")

if __name__ == '__main__':
    now = K.one_book(K.plan_trades() + K.vol_trades(1.5))
    p = [t[1] for t in now]; a = sum(t[1] for t in now if t[0] in H1)
    print(f"{NM.upper()} 2026. Indicator now: {len(p)} trades, {100 * sum(v > 0 for v in p) / len(p):.0f}% won, net {sum(p):+,.0f} "
          f"(Jan-Jun {a:+,.0f}, Jul-Oct {sum(p) - a:+,.0f}), worst trade {min(p):+.0f}, average hold {sum(t[3] - t[2] for t in now) / len(now):.0f} min")
    import multiprocessing as mp
    with mp.Pool() as pool: res = pool.map(run, GRID, chunksize=4)
    json.dump(res, open(f'../.cache/short_{NM}.json', 'w'))
    print(f" {len(res)} versions; made money in both halves: {sum(r['a'] > 0 and r['b'] > 0 for r in res)}")
    print(" your rules (stop at most the cap, out within 30 minutes), every exit:")
    for r in res:
        if r['P'][0] in CAPS and r['P'][2] == 30: show(r)
    print(" best 10 with a cap and at most 30 minutes, by net (both halves positive):")
    for r in sorted([r for r in res if r['P'][0] and r['P'][2] and r['P'][2] <= 30 and r['a'] > 0 and r['b'] > 0], key=lambda r: -r['net'])[:10]: show(r)
    print(" best 5 overall (both halves positive):")
    for r in sorted([r for r in res if r['a'] > 0 and r['b'] > 0], key=lambda r: -r['net'])[:5]: show(r)

"""2026 only: reversals at key levels, and buying / selling the pullback after the 9:30 breakout.

    python y2026_reversal.py nifty        (or sensex)

LEVELS (rebuilt every morning from earlier sessions only):
  oc7   the open and close of each of the last 7 sessions
  hl7   the high and low of each of the last 7 sessions
  vp7   the 7-day volume profile: point of control, value-area high / low, and the high-volume lines
  piv   today's CPR (TC, P, BC) and R1 / S1 / R2 / S2
  all   all of them
  Levels within 0.05% of price are merged.

A. REVERSAL AT A LEVEL, on 5-minute candles 9:30-2:30:
  reject   the candle pokes through the level and closes back (opened and closed on the near side)
  touch    the candle's high (low) comes within 0.05% of the level and it closes at least 0.05% away from it
  -> SELL at the close (BUY for a support level). Stop just beyond the candle's high (low).
  filter   none (both ways) / trend: only in the day's direction (above the CPR: only BUY at support = buying the
           pullback; below the CPR: only SELL at resistance)
B. PULLBACK AFTER THE BREAKOUT: the indicator's 9:30 breakout signal (same filters), but instead of entering at the
  break, wait (until 12:00) for price to come back to the broken 15-minute high / low after it has gone at least
  0.1% beyond it, and enter there (limit order) / on a 5-minute close back on the breakout side.
RISK (both): stop at most 100 / 150 Sensex or 30 / 45 Nifty points (a wider stop is pulled in to the cap, or the
  trade is skipped); target the next level (at least 1x the stop away) or 1 / 1.5 / 2 x the stop; out after 30 or 60
  minutes at the latest; no trailing. One trade at a time, at most 5 a day. Costs 4 Nifty / 12 Sensex points.
"""
import collections, itertools, json, sys
import y2026 as Y, y2026_vol_lines as V, cpr_orb as C, cpr_orb_winrate as W, y2026_short as S

one, five, LV, DAY, COST, D26, H1, NM = Y.one, Y.five, Y.LV, Y.DAY, Y.COST, Y.D26, Y.H1, Y.B.name
CAPS = S.CAPS
walk = S.walk

def merge(xs, d):
    out = []
    for x in sorted(xs):
        if out and x - out[-1] <= 0.0005 * x: out[-1] = (out[-1] + x) / 2
        else: out.append(x)
    return out

def build(d):
    i = Y.IDX[d]; prev7 = Y.days[i - 7:i]; lv = LV[d]; pr = Y.profile(d, 7)
    sets = dict(oc7=[DAY[x][0] for x in prev7] + [DAY[x][3] for x in prev7],
                hl7=[DAY[x][1] for x in prev7] + [DAY[x][2] for x in prev7],
                vp7=[pr['poc'], pr['vah'], pr['val']] + V.lines(d, 7),
                piv=[lv['top'], lv['p'], lv['bot'], lv['r1'], lv['s1'], lv['r2'], lv['s2']])
    sets['all'] = sum(sets.values(), [])
    return {k: merge(v, d) for k, v in sets.items()}
LEVELS = {d: build(d) for d in D26}

def exits(d, side, e, start, stp0, tgt_kind, lv, P):
    """Stop (capped), target, time limit -> trade dict or None."""
    cap_i, mode, hold = P['cap'], P['mode'], P['hold']
    risk = side * (e - stp0)
    if risk <= 0: return None
    stp = stp0
    if risk > cap_i:
        if mode == 'skip': return None
        stp, risk = e - side * cap_i, cap_i
    if tgt_kind == 'next':
        beyond = [x for x in lv if side * (x - e) >= risk]
        if not beyond: return None
        tgt = min(beyond, key=lambda x: abs(x - e))
    else:
        tgt = e + side * float(tgt_kind[:-1]) * risk
    pnl, mx, why = walk(d, side, e, start, stp, tgt, None, start - 1 + hold)
    return dict(d=d, side=side, m=start, mx=mx, pnl=pnl, why=why, risk=risk)

def reversal(d, P):
    lv = LEVELS[d][P['levels']]; b5 = five[d]; L = LV[d]; out = []; free = 0
    for j in range(1, len(b5)):
        m0, o, h, l, c = b5[j]
        if m0 < 570 or m0 + 5 > 870 or m0 < free or len(out) >= 5: continue
        tol = 0.0005 * c
        sig = None
        for x in lv:
            if P['trigger'] == 'reject':
                if h > x and o < x and c < x: sig = (-1, x, h)
                elif l < x and o > x and c > x: sig = (1, x, l)
            else:
                if abs(h - x) <= tol and o < x and c < x - tol: sig = (-1, x, h)
                elif abs(l - x) <= tol and o > x and c > x + tol: sig = (1, x, l)
            if sig: break
        if not sig: continue
        side, x, ext = sig
        if P['filter'] == 'trend' and not (side > 0 and c > L['top'] or side < 0 and c < L['bot']): continue
        t = exits(d, side, c, m0 + 5, ext - side * 0.0002 * c, P['target'], lv, P)
        if t:
            t['src'] = 'REV'; out.append(t); free = t['mx'] + 1
    return out

def pullback(d, P):
    first = [x for x in one[d] if x[0] < 570]; orh, orl = max(x[2] for x in first), min(x[3] for x in first)
    gap, poc, rel = W.FEAT[d]['gap'], Y.PROF30[d]['poc'], C.REL[d]
    lv = LEVELS[d]['all']
    sig = None
    for side, e, start, m in C.candidates(d, 'touch', orh, orl, 570):
        if m >= 600: break
        if side != -rel and gap == side and side * (e - poc) > 0: sig = (side, m); break
    if not sig: return []
    side, m = sig; Lv = orh if side > 0 else orl; tol = 0.0005 * Lv; far = Lv
    rows = [x for x in one[d] if x[0] > m]
    for k, (mm, o, h, l, c) in enumerate(rows):
        if mm >= 720: break
        far = max(far, h) if side > 0 else min(far, l)
        if side * (far - Lv) < 0.001 * Lv: continue
        touched = (l <= Lv + tol) if side > 0 else (h >= Lv - tol)
        if not touched: continue
        if P['entry'] == 'limit':
            px = Lv + side * tol
            e = min(o, px) if side > 0 else max(o, px)
            t = exits(d, side, e, mm + 1, orl if side > 0 else orh, P['target'], lv, P)
            if t: t['src'] = 'PB'; t['m'] = mm
            return [t] if t else []
        # close: the next 5-minute close back on the breakout side, within 30 minutes
        for x in five[d]:
            if x[0] < (mm - 555) // 5 * 5 + 555 or x[0] > mm + 30: continue
            if side * (x[4] - Lv) > tol:
                t = exits(d, side, x[4], x[0] + 5, orl if side > 0 else orh, P['target'], lv, P)
                if t: t['src'] = 'PB'
                return [t] if t else []
        return []
    return []

def book(ts):
    out = []; free = collections.defaultdict(int)
    for t in sorted(ts, key=lambda t: (t['d'], t['m'])):
        if t['m'] >= free[t['d']]: out.append(t); free[t['d']] = t['mx'] + 1
    return out

GRID_A = [dict(fam='A', levels=lv, trigger=tr, filter=fl, target=tg, hold=ho, cap=cp, mode=md)
          for lv, tr, fl, tg, ho, cp, md in itertools.product(('oc7', 'hl7', 'vp7', 'piv', 'all'), ('reject', 'touch'), ('none', 'trend'),
                                                              ('next', '1R', '1.5R', '2R'), (30, 60), CAPS, ('tighten', 'skip'))]
GRID_B = [dict(fam='B', entry=en, target=tg, hold=ho, cap=cp, mode=md)
          for en, tg, ho, cp, md in itertools.product(('limit', 'close'), ('next', '1R', '1.5R', '2R'), (30, 60), CAPS, ('tighten', 'skip'))]

def run(P):
    f = reversal if P['fam'] == 'A' else pullback
    ts = book([t for d in D26 for t in f(d, P)])
    p = [t['pnl'] for t in ts]; a = sum(t['pnl'] for t in ts if t['d'] in H1)
    eq = pk = dd = 0
    for v in p: eq += v; pk = max(pk, eq); dd = min(dd, eq - pk)
    return dict(P=P, n=len(p), w=sum(v > 0 for v in p), net=sum(p), a=a, b=sum(p) - a, dd=dd,
                days=len({t['d'] for t in ts}), worst=min(p) if p else 0, why=dict(collections.Counter(t['why'] for t in ts)))

def label(P):
    return (f"A {P['levels']:4} {P['trigger']:6} {P['filter']:5}" if P['fam'] == 'A' else f"B pullback {P['entry']:5}           ") + \
           f" tgt {P['target']:4} {P['hold']}m stop<={P['cap']} {P['mode']:7}"

def show(r):
    print(f"  {label(r['P'])} {r['n']:4} tr ({r['n'] / 9.3:4.1f}/mo) {100 * r['w'] / max(1, r['n']):3.0f}% won net {r['net']:+7,.0f} "
          f"(Jan-Jun {r['a']:+6,.0f}, Jul-Oct {r['b']:+6,.0f}) fall {r['dd']:6,.0f}")

if __name__ == '__main__':
    import multiprocessing as mp
    with mp.Pool() as pool: res = pool.map(run, GRID_A + GRID_B, chunksize=4)
    json.dump(res, open(f'../.cache/reversal_{NM}.json', 'w'))
    A = [r for r in res if r['P']['fam'] == 'A']; B = [r for r in res if r['P']['fam'] == 'B']
    print(f"{NM.upper()} 2026: A reversals at levels, {len(A)} versions: made money {sum(r['net'] > 0 for r in A)}, in both halves "
          f"{sum(r['a'] > 0 and r['b'] > 0 for r in A)}; middle version {sorted(r['net'] for r in A)[len(A) // 2]:+,.0f}")
    for k in ('levels', 'trigger', 'filter', 'target', 'hold', 'cap', 'mode'):
        g = collections.defaultdict(list)
        for r in A: g[r['P'][k]].append(r)
        print(f"   by {k:7}: " + ' | '.join(f"{v}: {sum(r['a'] > 0 and r['b'] > 0 for r in rs)}/{len(rs)} both +, avg {sum(r['net'] for r in rs) / len(rs):+,.0f}" for v, rs in g.items()))
    print("  best 8 (both halves +):")
    for r in sorted([r for r in A if r['a'] > 0 and r['b'] > 0], key=lambda r: -r['net'])[:8]: show(r)
    print(f"{NM.upper()} 2026: B pullback after the breakout, {len(B)} versions: made money {sum(r['net'] > 0 for r in B)}, both halves "
          f"{sum(r['a'] > 0 and r['b'] > 0 for r in B)}")
    for r in sorted(B, key=lambda r: -r['net'])[:8]: show(r)

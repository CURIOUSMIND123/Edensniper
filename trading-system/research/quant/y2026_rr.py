"""2026 only: trade only when the reward is at least 3x the risk (1:3), from levels and price action.

    python y2026_rr.py nifty        (or sensex)

STOPS, as a share of price (the same for both indices): at most 0.07% / 0.14% / 0.21% of price (Sensex about
50 / 100 / 150 points, Nifty about 16 / 31 / 47).
  tighten  the setup's own stop, pulled in to that limit when it's wider
  skip     the setup's own stop; skip the trade when it's wider than the limit
TARGETS:
  first3   the first key level in the trade's direction must be at least 3x the stop away; target that level
           (no trade otherwise)
  3R / 4R  a fixed 3x / 4x the stop
HOLD: out after 60 / 120 minutes at the latest, or at 3:15. No booking half, no trailing.
KEY LEVELS (every morning, from earlier sessions only): CPR (TC, P, BC), R1 / S1 / R2 / S2, the last 7 sessions'
  highs, lows, opens and closes, the 7-day volume profile (POC, value-area edges, high-volume lines), the 3-day
  volume lines and the 30-day POC; within 0.05% merged.
SETUPS (5-minute candles 9:30-2:30 unless said otherwise):
  PB   the pullback after the 9:30 breakout (limit order back at the broken 15-minute level, y2026_reversal.py);
       own stop: the other side of the 15-minute range
  MAG  CPR Magnet at 9:16 (own stop 0.3%)
  VOL  a 5-minute close through a 3-day volume line (own stop: the previous line)
  REV  a candle pokes through a key level and closes back (rejection) -> the other way; own stop just beyond the
       candle's high / low. Both ways, or only with the day (above the CPR: only BUY at support)
  BRK  a 5-minute close through a key level -> that way; own stop 0.05% back beyond the level. Both ways, or only
       with the day
One trade at a time per setup, at most 5 a day. Costs 4 Nifty / 12 Sensex points. January-June and July-9 October
2026 separately. Then the setups that held up in both halves on both indices are put in one book.
"""
import collections, itertools, json, sys
import y2026 as Y, y2026_vol_lines as V, cpr_orb as C, cpr_orb_winrate as W, y2026_short as S, y2026_reversal as RV

one, five, LV, COST, D26, H1, NM = Y.one, Y.five, Y.LV, Y.COST, Y.D26, Y.H1, Y.B.name
walk = S.walk

def keylevels(d):
    xs = RV.LEVELS[d]['all'] + V.LINES[(d, 3)] + [Y.PROF30[d]['poc']]
    return RV.merge(xs, d)
KEY = {d: keylevels(d) for d in D26}

def plan_exit(d, side, e, start, stp0, P):
    """Apply the stop limit and the target rule; walk the exits. None if the trade isn't taken."""
    cap = P['cap'] * e
    risk = side * (e - stp0)
    if risk <= 0: return None
    stp = stp0
    if risk > cap:
        if P['mode'] == 'skip': return None
        stp, risk = e - side * cap, cap
    if P['target'] == 'first3':
        ahead = [x for x in KEY[d] if side * (x - e) > 0.0002 * e]
        if not ahead: return None
        tgt = min(ahead, key=lambda x: abs(x - e))
        if side * (tgt - e) < 3 * risk: return None
    else:
        tgt = e + side * float(P['target'][:-1]) * risk
    last = start - 1 + P['hold'] if P['hold'] else 915
    pnl, mx, why = walk(d, side, e, start, stp, tgt, None, last)
    return dict(d=d, side=side, m=start, mx=mx, pnl=pnl, why=why, risk=risk, rr=side * (tgt - e) / risk)

def pb(d, P):
    first = [x for x in one[d] if x[0] < 570]; orh, orl = max(x[2] for x in first), min(x[3] for x in first)
    gap, poc, rel = W.FEAT[d]['gap'], Y.PROF30[d]['poc'], C.REL[d]
    sig = None
    for side, e, start, m in C.candidates(d, 'touch', orh, orl, 570):
        if m >= 600: break
        if side != -rel and gap == side and side * (e - poc) > 0: sig = (side, m); break
    if not sig: return []
    side, m = sig; lvl = orh if side > 0 else orl; tol = 0.0005 * lvl; far = lvl
    for mm, o, h, l, c in one[d]:
        if mm <= m: continue
        if mm >= 720: break
        far = max(far, h) if side > 0 else min(far, l)
        if side * (far - lvl) < 0.001 * lvl: continue
        if not ((l <= lvl + tol) if side > 0 else (h >= lvl - tol)): continue
        px = lvl + side * tol; e = min(o, px) if side > 0 else max(o, px)
        t = plan_exit(d, side, e, mm + 1, orl if side > 0 else orh, P)
        if t: t['m'] = mm; t['src'] = 'PB'
        return [t] if t else []
    return []

def mag(d, P):
    lv = LV[d]
    if lv['rank'] < 1 / 3: return []
    o, e = one[d][0][1], one[d][0][4]
    side = -1 if o > lv['top'] else 1 if o < lv['bot'] else 0
    if not side: return []
    edge = lv['top'] if side < 0 else lv['bot']
    if side * (edge - e) < 0.002 * e or side * (e - Y.PROF30[d]['poc']) <= 0: return []
    t = plan_exit(d, side, e, 556, e - side * 0.003 * e, P)
    if t: t['src'] = 'MAG'
    return [t] if t else []

def scan(d, P, signal):
    """5-minute candles 9:30-2:30, one trade at a time, at most 5 a day; signal(j, candle, prev close) -> (side, stop) or None."""
    b5 = five[d]; out = []; free = 0
    for j in range(1, len(b5)):
        m0 = b5[j][0]
        if m0 < 570 or m0 + 5 > 870 or m0 < free or len(out) >= 5: continue
        sig = signal(d, b5[j], b5[j - 1][4])
        if not sig: continue
        side, stp0 = sig
        t = plan_exit(d, side, b5[j][4], m0 + 5, stp0, P)
        if t: t['src'] = P['fam']; out.append(t); free = t['mx'] + 1
    return out

def vol_sig(d, cnd, pc):
    m0, o, h, l, c = cnd; lv = V.LINES[(d, 3)]
    for x in lv:
        side = 1 if pc < x <= c else -1 if pc > x >= c else 0
        if not side: continue
        prv = [y for y in lv if side * (x - y) > 0]
        if not prv: return None
        return side, (max(prv) if side > 0 else min(prv))
    return None

def rev_sig(trend):
    def f(d, cnd, pc):
        m0, o, h, l, c = cnd; L = LV[d]
        for x in KEY[d]:
            if h > x and o < x and c < x: side, ext = -1, h
            elif l < x and o > x and c > x: side, ext = 1, l
            else: continue
            if trend and not (side > 0 and c > L['top'] or side < 0 and c < L['bot']): return None
            return side, ext - side * 0.0002 * c
        return None
    return f

def brk_sig(trend):
    def f(d, cnd, pc):
        m0, o, h, l, c = cnd; L = LV[d]
        for x in KEY[d]:
            side = 1 if pc < x < c else -1 if pc > x > c else 0
            if not side: continue
            if trend and not (side > 0 and c > L['top'] or side < 0 and c < L['bot']): return None
            return side, x - side * 0.0005 * c
        return None
    return f

FAMS = {'PB': lambda d, P: pb(d, P), 'MAG': lambda d, P: mag(d, P), 'VOL': lambda d, P: scan(d, P, vol_sig),
        'REV': lambda d, P: scan(d, P, rev_sig(False)), 'REV-trend': lambda d, P: scan(d, P, rev_sig(True)),
        'BRK': lambda d, P: scan(d, P, brk_sig(False)), 'BRK-trend': lambda d, P: scan(d, P, brk_sig(True))}
GRID = [dict(fam=f, cap=cp, mode=md, target=tg, hold=ho) for f, cp, md, tg, ho in
        itertools.product(FAMS, (0.0007, 0.0014, 0.0021), ('tighten', 'skip'), ('first3', '3R', '4R'), (60, 120, 0))]

def stats(ts):
    p = [t['pnl'] for t in ts]; a = sum(t['pnl'] for t in ts if t['d'] in H1)
    eq = pk = dd = 0
    for v in p: eq += v; pk = max(pk, eq); dd = min(dd, eq - pk)
    w = [v for v in p if v > 0]; l = [v for v in p if v <= 0]
    return dict(n=len(p), w=len(w), net=sum(p), a=a, b=sum(p) - a, dd=dd, avg_w=sum(w) / max(1, len(w)),
                avg_l=sum(l) / max(1, len(l)), worst=min(p) if p else 0, why=dict(collections.Counter(t['why'] for t in ts)))

def run(P):
    return dict(P=P, **stats([t for d in D26 for t in FAMS[P['fam']](d, P)]))

def label(P):
    return f"{P['fam']:9} stop<={100 * P['cap']:.2f}% {P['mode']:7} {P['target']:6} {('out ' + str(P['hold']) + 'm') if P['hold'] else 'to 3:15':8}"

def show(r):
    print(f"  {label(r['P'])} {r['n']:4} tr ({r['n'] / 9.3:4.1f}/mo) {100 * r['w'] / max(1, r['n']):3.0f}% won | avg win {r['avg_w']:+5.0f} "
          f"avg loss {r['avg_l']:+5.0f} | net {r['net']:+7,.0f} (Jan-Jun {r['a']:+6,.0f}, Jul-Oct {r['b']:+6,.0f}) fall {r['dd']:6,.0f}")

if __name__ == '__main__':
    import multiprocessing as mp
    with mp.Pool() as pool: res = pool.map(run, GRID, chunksize=4)
    json.dump(res, open(f'../.cache/rr_{NM}.json', 'w'))
    print(f"{NM.upper()} 2026, reward at least 3x the risk: {len(res)} versions, made money {sum(r['net'] > 0 for r in res)}, "
          f"in both halves {sum(r['a'] > 0 and r['b'] > 0 for r in res)}")
    for f in FAMS:
        rs = [r for r in res if r['P']['fam'] == f]
        print(f" {f}: {sum(r['a'] > 0 and r['b'] > 0 for r in rs)}/{len(rs)} both halves +, middle net {sorted(r['net'] for r in rs)[len(rs) // 2]:+,.0f}")
        for r in sorted([r for r in rs if r['a'] > 0 and r['b'] > 0], key=lambda r: -r['net'])[:3]: show(r)

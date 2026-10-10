"""2026 only: exit changes suggested by y2026_trades.py, tested part by part and then together.

    python y2026_improve.py nifty        (or sensex)

What the trade review showed and what is tested here:
  CPR Magnet winners kept running after we closed at the CPR edge -> after half is booked, instead of closing the
      rest at the CPR edge: the far edge of the CPR / trail 1R behind the best price / hold to 3:15 (stop at entry)
  CPR Breakout winners kept running after the 1R trail closed them -> trail 1.5R or 2R / hold to 3:15
  Volume-line losers were mostly in profit first -> move the stop to entry once price is halfway to the target;
      and "ladder": at the target book half, move the stop to the broken line and aim for the following line
Everything else as in the indicator (one trade at a time; costs 4 Nifty / 12 Sensex points).
January-June and July-9 October 2026 shown separately.
"""
import collections, itertools, sys
import y2026 as Y, y2026_losses as L, y2026_vol_lines as V
import cpr_orb as C, cpr_orb_winrate as W

one, five, LV, COST = Y.one, Y.five, Y.LV, Y.COST

def path(o, h, l, c): return (o, l, h, c) if c >= o else (o, h, l, c)

def walk(d, side, e, start, stp, half_at, final, trail):
    """Book half at half_at (stop to entry), then: final target, trail k*R behind the best price, or hold to 3:15."""
    R = abs(e - stp); half = None; best = e
    for m, o, h, l, c in one[d]:
        if m < start: continue
        for px in path(o, h, l, c):
            if side * (px - stp) <= 0:
                rest = side * (stp - e)
                return (rest if half is None else (half + rest) / 2) - COST, m
            if half is None and side * (px - half_at) >= 0:
                half = side * (half_at - e)
                if side * (e - stp) > 0: stp = e
            if half is not None and final is not None and side * (px - final) >= 0:
                return (half + side * (final - e)) / 2 - COST, m
        best = max(best, h) if side > 0 else min(best, l)
        if trail and half is not None and side * (best - e) >= R:
            ns = best - side * trail * R
            if side * (ns - stp) > 0: stp = ns
        if m >= 915:
            rest = side * (c - e)
            return (rest if half is None else (half + rest) / 2) - COST, m
    rest = side * (one[d][-1][4] - e)
    return (rest if half is None else (half + rest) / 2) - COST, one[d][-1][0]

def magnet(d, rest):
    lv = LV[d]
    if lv['rank'] < 1 / 3: return []
    o, e = one[d][0][1], one[d][0][4]
    side = -1 if o > lv['top'] else 1 if o < lv['bot'] else 0
    if not side: return []
    edge = lv['top'] if side < 0 else lv['bot']; far = lv['bot'] if side < 0 else lv['top']
    if side * (edge - e) < 0.002 * e or side * (e - Y.PROF30[d]['poc']) <= 0: return []
    R = 0.003 * e; stp = e - side * R
    final, trail = {'edge': (edge, 0), 'far': (far, 0), 'trail': (None, 1.0), 'hold': (None, 0)}[rest]
    pnl, mx = walk(d, side, e, 556, stp, e + side * 0.25 * R, final, trail)
    return [dict(d=d, src='MAG', side=side, m=556, mx=mx, pnl=pnl)]

def breakout(d, trail):
    lv = LV[d]; first = [x for x in one[d] if x[0] < 570]; orh, orl = max(x[2] for x in first), min(x[3] for x in first)
    f = W.FEAT[d]; poc = Y.PROF30[d]['poc']
    ok = lambda s, e: s * (e - poc) > 0
    for side, e, start, m in C.candidates(d, 'touch', orh, orl, 570):
        if m >= 600: break
        if side == -C.REL[d] or f['gap'] != side or not ok(side, e): continue
        stp = orl if side > 0 else orh; R = side * (e - stp)
        if R <= 0: continue
        pnl, mx = walk(d, side, e, start, stp, e + side * 0.25 * R, None, trail)
        out = [dict(d=d, src='BO', side=side, m=m, mx=mx, pnl=pnl)]
        if pnl <= 0:
            for s2, e2, st2, m2 in C.candidates(d, 'touch', orh, orl, mx + 1):
                if m2 >= 600: break
                if s2 != -side or not ok(s2, e2): continue
                stp2 = orl if s2 > 0 else orh; R2 = s2 * (e2 - stp2)
                if R2 <= 0: break
                p2, mx2 = walk(d, s2, e2, st2, stp2, e2 + s2 * 0.25 * R2, None, trail)
                out.append(dict(d=d, src='BO', side=s2, m=m2, mx=mx2, pnl=p2)); break
        return out
    return []

def plan(d, mag_rest, bo_trail):
    if LV[d]['rank'] < 1 / 3: return breakout(d, bo_trail)
    return magnet(d, mag_rest) or breakout(d, bo_trail)

def vol(d, mode):
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
            tgt = nxt[0]; stp = max(prv) if side > 0 else min(prv); e = c
            if side * (e - stp) <= 0 or side * (tgt - e) < 1.5 * side * (e - stp): break
            be_at = e + side * 0.5 * (tgt - e) if 'be' in mode else None
            tgt2 = nxt[1] if 'ladder' in mode and len(nxt) > 1 else None
            half = None; pnl = None; mx = None
            for m, op, hh, ll, cc in one[d]:
                if m < m0 + 5: continue
                for px in path(op, hh, ll, cc):
                    if side * (px - stp) <= 0:
                        rest = side * (stp - e); pnl = rest if half is None else (half + rest) / 2; mx = m; break
                    if be_at is not None and side * (px - be_at) >= 0 and side * (e - stp) > 0: stp = e
                    if half is None and side * (px - tgt) >= 0:
                        if tgt2 is None: pnl = side * (tgt - e); mx = m; break
                        half = side * (tgt - e); stp = x                 # book half, stop to the broken line
                    if half is not None and side * (px - tgt2) >= 0:
                        pnl = (half + side * (tgt2 - e)) / 2; mx = m; break
                if pnl is None and m >= 915:
                    rest = side * (cc - e); pnl = rest if half is None else (half + rest) / 2; mx = m
                if pnl is not None: break
            if pnl is None: pnl, mx = side * (one[d][-1][4] - e), one[d][-1][0]
            out.append(dict(d=d, src='VOL', side=side, m=m0 + 5, mx=mx, pnl=pnl - COST)); free = mx + 1
            break
    return out

def one_book(ts):
    out = []; free = collections.defaultdict(int)
    for t in sorted(ts, key=lambda t: (t['d'], t['m'], t['src'] == 'VOL')):
        if t['m'] >= free[t['d']]: out.append(t); free[t['d']] = t['mx'] + 1
    return out

def show(label, ts, base=None):
    p = [t['pnl'] for t in ts]; w = [v for v in p if v > 0]; l = [v for v in p if v <= 0]
    a = sum(t['pnl'] for t in ts if t['d'] in Y.H1); b = sum(p) - a
    tag = ''
    if base: tag = '   <- better in both halves' if a > base[0] and b > base[1] else ''
    print(f"  {label:46} {len(p):3} tr {len(w):3}W/{len(l):<3}L won {sum(w):+7,.0f} lost {sum(l):+7,.0f} net {sum(p):+7,.0f} "
          f"(Jan-Jun {a:+6,.0f}, Jul-Oct {b:+6,.0f}){tag}")
    return a, b

if __name__ == '__main__':
    D = Y.D26
    print(f"{Y.B.name.upper()} 2026, whole indicator (plan + volume lines, one trade at a time)")
    P = {(mr, bt): [t for d in D for t in plan(d, mr, bt)] for mr in ('edge', 'far', 'trail', 'hold') for bt in (1.0, 1.5, 2.0, 0)}
    VV = {md: [t for d in D for t in vol(d, md)] for md in ('fixed', 'be', 'ladder', 'be+ladder')}
    base = show('as now (magnet edge, trail 1R, volume fixed)', one_book(P[('edge', 1.0)] + VV['fixed']))
    print(" one change at a time:")
    for mr in ('far', 'trail', 'hold'): show(f"magnet rest: {mr}", one_book(P[(mr, 1.0)] + VV['fixed']), base)
    for bt in (1.5, 2.0, 0): show(f"breakout trail: {'hold to 3:15' if bt == 0 else f'{bt}R'}", one_book(P[('edge', bt)] + VV['fixed']), base)
    for md in ('be', 'ladder', 'be+ladder'): show(f"volume lines: {md}", one_book(P[('edge', 1.0)] + VV[md]), base)
    print(" every combination, best 8 by net:")
    rows = []
    for (mr, bt), md in itertools.product(P, VV):
        ts = one_book(P[(mr, bt)] + VV[md])
        a = sum(t['pnl'] for t in ts if t['d'] in Y.H1); b = sum(t['pnl'] for t in ts) - a
        rows.append((a + b, mr, bt, md, ts))
    for net, mr, bt, md, ts in sorted(rows, key=lambda r: -r[0])[:8]:
        show(f"magnet {mr}, breakout {'hold' if bt == 0 else f'{bt}R'}, volume {md}", ts, base)

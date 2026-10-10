"""2026 only: a daily playbook that combines CPR Breakout and CPR Magnet so most days get a trade.

    python y2026_daily.py nifty        (or sensex)

Pieces (all rules as in y2026.py; entries known live, costs 4 Nifty / 12 Sensex points):
  BO-narrow   CPR Breakout scalp on narrow-CPR days (gap direction, 30-day volume POC side, before 10:00)
  BO-other    the same breakout on days that are NOT narrow
  MAG         CPR Magnet (9:15 candle 0.2%+ beyond a CPR that isn't narrow, back to the CPR edge, stop 0.3%)
  MAG-half    the same, but book half at 0.25 x the risk, move the stop to entry, the rest to the CPR edge
Playbooks: one plan per day. Narrow day -> BO-narrow. Other day -> MAG (or MAG-half) if the open qualifies,
otherwise BO-other (if switched on). Results for January-June and July-9 October 2026 separately.
"""
import collections, sys
import y2026 as Y

B, one, LV, COST = Y.B, Y.one, Y.LV, Y.COST

def path(o, h, l, c): return (o, l, h, c) if c >= o else (o, h, l, c)

def magnet_half(d):
    lv = LV[d]
    if lv['rank'] < 1 / 3: return []
    o, e = one[d][0][1], one[d][0][4]
    side = -1 if o > lv['top'] else 1 if o < lv['bot'] else 0
    if not side: return []
    edge = lv['top'] if side < 0 else lv['bot']
    if side * (edge - e) < 0.002 * e: return []
    R = 0.003 * e; stp = e - side * R; t1 = e + side * 0.25 * R; half = None
    for m, op, h, l, c in one[d]:
        if m < 556: continue
        for px in path(op, h, l, c):
            if side * (px - stp) <= 0:
                rest = side * (stp - e)
                return [dict(d=d, side=side, m=556, pnl=(rest if half is None else (half + rest) / 2) - COST)]
            if half is None and side * (px - t1) >= 0: half = side * (t1 - e); stp = e
            if half is not None and side * (px - edge) >= 0:
                return [dict(d=d, side=side, m=556, pnl=(half + side * (edge - e)) / 2 - COST)]
        if m >= 915:
            rest = side * (c - e)
            return [dict(d=d, side=side, m=556, pnl=(rest if half is None else (half + rest) / 2) - COST)]
    return []

def bo(d, kind): return Y.breakout_live(d, 'scalp', True, 600, kind)

def plan(d, mag, other):
    if LV[d]['rank'] < 1 / 3: return [dict(t, src='BO-narrow') for t in bo(d, 'narrow')]
    if mag:
        ts = (Y.magnet(d) if mag == 'MAG' else magnet_half(d))
        if ts: return [dict(t, src=mag) for t in ts]
    if other: return [dict(t, src='BO-other') for t in bo(d, 'other')]
    return []

def line(ts, label, ndays):
    out = []
    for nm, xs in (('Jan-Jun', [t for t in ts if t['d'] in Y.H1]), ('Jul-Oct', [t for t in ts if t['d'] not in Y.H1]), ('2026', ts)):
        p = [t['pnl'] for t in xs]
        out.append(f"{nm} {len(p):3}tr {sum(v > 0 for v in p):3}W/{sum(v <= 0 for v in p):<3}L {sum(p):+7,.0f}")
    days = len({t['d'] for t in ts}); w = [t['pnl'] for t in ts if t['pnl'] > 0]; l = [t['pnl'] for t in ts if t['pnl'] <= 0]
    print(f"  {label:34} {' | '.join(out)} | traded on {days} of {ndays} days, {len(ts)/9.3:.1f} trades a month, won {100*len(w)/max(1,len(ts)):.0f}%, "
          f"won {sum(w):+,.0f} / lost {sum(l):+,.0f}")

if __name__ == '__main__':
    n = len(Y.D26)
    print(f"{B.name.upper()} 2026 ({Y.D26[0]} to {Y.D26[-1]}, {n} sessions; narrow-CPR days: {sum(LV[d]['rank'] < 1/3 for d in Y.D26)})")
    print(" pieces:")
    line([t for d in Y.D26 for t in bo(d, 'narrow')], 'BO-narrow (current indicator)', n)
    line([t for d in Y.D26 for t in bo(d, 'other')], 'BO-other', n)
    line([t for d in Y.D26 for t in Y.magnet(d)], 'MAG', n)
    line([t for d in Y.D26 for t in magnet_half(d)], 'MAG-half', n)
    print(" playbooks (one plan per day):")
    for mag in ('MAG', 'MAG-half'):
        for other in (False, True):
            ts = [t for d in Y.D26 for t in plan(d, mag, other)]
            line(ts, f"BO-narrow + {mag}" + (' + BO-other' if other else ''), n)
            if mag == 'MAG-half' and other:
                by = collections.defaultdict(list)
                for t in ts: by[t['src']].append(t['pnl'])
                for k, v in by.items(): print(f"      {k:10} {len(v):3} trades, won {sum(x > 0 for x in v)}, net {sum(v):+,.0f}")
                mo = collections.defaultdict(float)
                for t in ts: mo[t['d'][:7]] += t['pnl']
                print("      by month: " + ', '.join(f"{k[5:]} {v:+,.0f}" for k, v in sorted(mo.items())))

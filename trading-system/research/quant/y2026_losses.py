"""2026 only: the daily plan's losing trades, and which CPR Magnet changes cut losses without cutting more wins.

    python y2026_losses.py nifty        (or sensex)

Daily plan as in y2026_daily.py (narrow day -> breakout; other day -> magnet if the open qualifies, else
breakout). The breakout part is unchanged; the magnet part is varied:
  stop     0.2 / 0.25 / 0.3 (now) / 0.4 % of price
  time     exit if half isn't booked within 10 / 20 / 30 / 60 minutes (or never)
  maxgap   skip when the 9:15 close is more than 0.5 / 0.75 / 1.0 % beyond the CPR edge (or no limit)
  inside   skip when the day opened outside yesterday's high-low range
  first    only when the 9:15 candle already moved toward the CPR
  conf5    enter at 9:20 instead, only if the first 5-minute candle moved toward the CPR
  poc      only on the volume side of the 30-day POC (sells below it, buys above)
  vol      skip when yesterday's range (% of price) was above its 20-day median
Each version is reported for January-June and July-9 October 2026 separately, with the whole plan's total.
"""
import collections, itertools, sys
import y2026 as Y
import y2026_daily as YD

B, one, LV, DAY, COST = Y.B, Y.one, Y.LV, Y.DAY, Y.COST

def path(o, h, l, c): return (o, l, h, c) if c >= o else (o, h, l, c)

def magnet(d, stop=0.3, tstop=0, maxgap=0, inside=False, first=False, conf5=False, poc=False, vol=False):
    lv = LV[d]
    if lv['rank'] < 1 / 3: return []
    o = one[d][0][1]
    side = -1 if o > lv['top'] else 1 if o < lv['bot'] else 0
    if not side: return []
    edge = lv['top'] if side < 0 else lv['bot']
    if conf5:
        b5 = Y.five[d][0]; e, m0 = b5[4], 560
        if side * (e - o) <= 0: return []
    else:
        e, m0 = one[d][0][4], 556
    if side * (edge - e) < 0.002 * e: return []
    if maxgap and side * (edge - e) > maxgap / 100 * e: return []
    ph, pl = DAY[Y.days[Y.IDX[d] - 1]][1:3]
    if inside and (o > ph or o < pl): return []
    if first and side * (one[d][0][4] - o) <= 0: return []
    if poc and side * (e - Y.PROF30[d]['poc']) <= 0: return []
    if vol:                                            # yesterday's range (% of price) above its 20-day median
        rng = lambda x: (DAY[x][1] - DAY[x][2]) / DAY[x][3]
        i = Y.IDX[d]
        if rng(Y.days[i - 1]) > sorted(rng(x) for x in Y.days[i - 21:i - 1])[10]: return []
    R = stop / 100 * e; stp = e - side * R; t1 = e + side * 0.25 * R; half = None
    for m, op, h, l, c in one[d]:
        if m < m0: continue
        for px in path(op, h, l, c):
            if side * (px - stp) <= 0:
                rest = side * (stp - e)
                return [dict(d=d, src='MAG', side=side, pnl=(rest if half is None else (half + rest) / 2) - COST,
                             why='stop' if half is None else 'stop at entry', mins=m - m0)]
            if half is None and side * (px - t1) >= 0: half = side * (t1 - e); stp = e
            if half is not None and side * (px - edge) >= 0:
                return [dict(d=d, src='MAG', side=side, pnl=(half + side * (edge - e)) / 2 - COST, why='target', mins=m - m0)]
        if (tstop and half is None and m >= m0 + tstop) or m >= 915:
            rest = side * (c - e)
            return [dict(d=d, src='MAG', side=side, pnl=(rest if half is None else (half + rest) / 2) - COST,
                         why='time' if m < 915 else '3:15', mins=m - m0)]
    return []

BO = {}
def plan(d, **kw):
    if d not in BO:
        BO[d] = (YD.bo(d, 'narrow'), YD.bo(d, 'other'))
    if LV[d]['rank'] < 1 / 3: return [dict(t, src='BO') for t in BO[d][0]]
    ts = magnet(d, **kw)
    return ts if ts else [dict(t, src='BO') for t in BO[d][1]]

def summary(ts):
    h1 = [t['pnl'] for t in ts if t['d'] in Y.H1]; h2 = [t['pnl'] for t in ts if t['d'] not in Y.H1]; p = h1 + h2
    w = [v for v in p if v > 0]; l = [v for v in p if v <= 0]
    return len(p), len(w), sum(w), sum(l), sum(p), sum(h1), sum(h2)

if __name__ == '__main__':
    base = [t for d in Y.D26 for t in plan(d)]
    n, w, won, lost, net, a, b = summary(base)
    print(f"{B.name.upper()} 2026 daily plan as is: {n} trades, {w} won / {n-w} lost, won {won:+,.0f}, lost {lost:+,.0f}, net {net:+,.0f} (Jan-Jun {a:+,.0f}, Jul-Oct {b:+,.0f})")
    print(" losing trades:")
    for t in base:
        if t['pnl'] <= 0:
            print(f"   {t['d']} {t['src']:3} {'BUY ' if t['side'] > 0 else 'SELL'} {t['pnl']:+7.1f}" + (f"  {t['why']} after {t['mins']} min" if 'why' in t else ''))
    print(" changes to the magnet part (whole plan totals):")
    rows = []
    grid = [dict()] + [dict(stop=s) for s in (0.2, 0.25, 0.4)] + [dict(tstop=t) for t in (10, 20, 30, 60)] + \
           [dict(maxgap=g) for g in (0.5, 0.75, 1.0)] + [dict(inside=True), dict(first=True), dict(conf5=True), dict(poc=True), dict(vol=True)]
    grid += [dict(tstop=t, stop=s) for t in (10, 20, 30) for s in (0.2, 0.25, 0.4)]
    for kw in grid:
        ts = [t for d in Y.D26 for t in plan(d, **kw)]
        n2, w2, won2, lost2, net2, a2, b2 = summary(ts)
        rows.append((kw, n2, w2, won2, lost2, net2, a2, b2))
        print(f"   {str(kw) if kw else 'as is':28} {n2:3} tr {w2:3}W/{n2-w2:<3}L won {won2:+7,.0f} lost {lost2:+7,.0f} net {net2:+7,.0f} | Jan-Jun {a2:+6,.0f} Jul-Oct {b2:+6,.0f}"
              + ('   <- better in both halves' if a2 > a and b2 > b else ''))

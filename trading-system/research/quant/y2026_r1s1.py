"""2026 only: on a gap-up day, when price rises to R1, SELL there (and on a gap-down day, when price falls to S1, BUY
there): the trade back from the pivot level.

    python y2026_r1s1.py nifty        (or sensex)
    python y2026_r1s1.py nifty years  every version year by year, 2023-2026 (the earlier years were not used to choose)

Pivots from the previous session's official high, low and close: P = (H + L + C) / 3, R1 = 2P - L, S1 = 2P - H.
Gap up = open above the previous close and below R1 (so price has to rise to R1); gap down the other way with S1.
Only the first touch of R1 / S1, before 2:30. Entry:
  touch     a limit order at R1 / S1 (filled at the level, or at the candle's open if it jumps through)
  reject    wait for a 5-minute candle that reaches the level and closes back below R1 (above S1), within 30
            minutes of the touch; enter at its close (cancelled if a 5-minute candle closes beyond the stop first)
Stop: 0.1% / 0.2% / 0.3% of price beyond the level. Target: 1x or 2x the risk, the pivot P, or none (held to 3:15).
Out at 3:15 at the latest. Costs 4 Nifty / 12 Sensex points a trade.
Also: after the first touch, how often price came back to P before going 0.2% beyond the level (and the other way).
"""
import collections, itertools, sys
import y2026 as Y

NM, COST = Y.B.name, Y.COST
LAST90 = set(Y.D26[-90:])

def path(o, h, l, c):
    return (o, l, h, c) if c >= o else (o, h, l, c)

def levels(d):
    prev = Y.days[Y.IDX[d] - 1]
    _, H, L, C = Y.DAY[prev][:4]
    P = (H + L + C) / 3
    return C, P, 2 * P - L, 2 * P - H

def walk(c1, k0, start_pts, s, e, stp, tgt):
    """From candle k0 (its path from point index start_pts), short (s=-1) or long (s=1)."""
    for k in range(k0, len(c1)):
        m, o, h, l, c = c1[k]
        if m >= 915: return s * (o - e), m
        pts = path(o, h, l, c)
        for p in pts[start_pts if k == k0 else 0:]:
            if s * (p - stp) <= 0: return s * (stp - e), m
            if tgt is not None and s * (p - tgt) >= 0: return s * (tgt - e), m
    return s * (c1[-1][4] - e), c1[-1][0]

def day_trades(d):
    c1 = [x for x in Y.one[d] if 555 <= x[0] <= 929]
    C, P, R1, S1 = levels(d)
    o = c1[0][1]
    if C < o < R1: s, lv = -1, R1          # gap up below R1 -> SELL at R1
    elif S1 < o < C: s, lv = 1, S1         # gap down above S1 -> BUY at S1
    else: return None
    touch = None
    for k, (m, o_, h, l, c) in enumerate(c1):
        if m > 870: break
        if (h >= lv if s < 0 else l <= lv):
            touch = k; break
    info = dict(d=d, s=s, touch=None)
    if touch is None: return info
    m, o_, h, l, c = c1[touch]
    info['touch'] = m
    # which first after the touch: P (back) or 0.2% beyond the level
    far = lv * (1 - s * 0.002)
    who = None
    for k in range(touch, len(c1)):
        for p in path(*c1[k][1:]):
            if s * (p - P) >= 0 and k > touch or (k == touch and False): who = 'P'; break
            if s * (p - far) <= 0: who = 'beyond'; break
        if who: break
    info['first'] = who
    out = {}
    for stop_pct, tgt in itertools.product((0.001, 0.002, 0.003), ('1R', '2R', 'P', 'none')):
        stp = lv * (1 - s * stop_pct)
        for entry in ('touch', 'reject'):
            if entry == 'touch':
                pts = path(o_, h, l, c)
                hit = next(i for i, p in enumerate(pts) if (p >= lv if s < 0 else p <= lv))
                e = pts[0] if hit == 0 and (pts[0] >= lv if s < 0 else pts[0] <= lv) else lv
                k0, sp = touch, hit
            else:
                e = None
                for k in range(touch, min(len(c1), touch + 35)):
                    mm = c1[k][0]
                    if (mm - 555) % 5 != 4: continue
                    blk = c1[max(0, k - 4):k + 1]
                    hh = max(x[2] for x in blk); ll = min(x[3] for x in blk); cc = c1[k][4]
                    if s * (cc - stp) <= 0: break
                    if mm - c1[touch][0] > 30: break
                    if (hh >= lv and cc < lv) if s < 0 else (ll <= lv and cc > lv):
                        e, k0, sp = cc, k + 1, 0; break
                if e is None or k0 >= len(c1) or c1[k0][0] >= 915:
                    out[(stop_pct, tgt, entry)] = None; continue
            risk = s * (e - stp)
            if risk <= 0:
                out[(stop_pct, tgt, entry)] = None; continue
            t = {'1R': e + s * risk, '2R': e + 2 * s * risk, 'P': P if s * (P - e) > 0 else None, 'none': None}[tgt]
            if tgt == 'P' and t is None:
                out[(stop_pct, tgt, entry)] = None; continue
            pnl, xm = walk(c1, k0, sp, s, e, stp, t)
            out[(stop_pct, tgt, entry)] = pnl - COST
    info['res'] = out
    return info

def summ(v):
    v = [x for x in v if x is not None]
    return len(v), sum(x > 0 for x in v), sum(v)

def years():
    ds = [d for d in Y.days if Y.IDX[d] > 0 and len(Y.one.get(d, [])) >= 300 and Y.days[Y.IDX[d] - 1] in Y.DAY]
    rows = [r for r in (day_trades(d) for d in ds) if r and r['touch']]
    print(f"{NM.upper()} {ds[0]} - {ds[-1]}: net points after costs by year")
    for s in (-1, 1):
        print('  SELL at R1 after a gap up' if s < 0 else '  BUY at S1 after a gap down')
        keys = sorted({k for r in rows for k in r['res']}, key=lambda k: (k[2], k[0], k[1]))
        for k in keys:
            by = collections.defaultdict(list)
            for r in rows:
                if r['s'] == s and r['res'][k] is not None: by[r['d'][:4]].append(r['res'][k])
            tot = sum(sum(v) for v in by.values())
            print(f"    {k[2]:6} stop {k[0] * 100:.1f}% target {k[1]:4}: " +
                  ', '.join(f"{y} {len(v)} tr {sum(x > 0 for x in v)} won {sum(v):+6.0f}" for y, v in sorted(by.items())) +
                  f" | all {tot:+.0f}{'  <- every year 2024-2026 positive' if all(sum(by.get(y, [0])) > 0 for y in ('2024', '2025', '2026')) else ''}")

if __name__ == '__main__':
    if sys.argv[2:3] == ['years']:
        years(); sys.exit()
    rows = [r for r in (day_trades(d) for d in Y.D26) if r]
    print(f"{NM.upper()} 2026 (1 Jan - 9 Oct), first touch of R1 after a gap up / S1 after a gap down, costs {COST:g} points a trade")
    for s, lab in ((-1, 'GAP UP, then R1 touched -> SELL'), (1, 'GAP DOWN, then S1 touched -> BUY')):
        g = [r for r in rows if r['s'] == s]
        t = [r for r in g if r['touch']]
        fc = collections.Counter(r['first'] for r in t)
        print(f"\n  {lab}: {len(g)} gap days, the level touched on {len(t)} (last 90 sessions: {sum(r['d'] in LAST90 for r in t)})")
        print(f"    after the touch: back to the pivot P first {fc['P']}, 0.2% beyond the level first {fc['beyond']}, neither {fc[None]}")
        for entry in ('touch', 'reject'):
            for stop_pct in (0.001, 0.002, 0.003):
                line = []
                for tgt in ('1R', '2R', 'P', 'none'):
                    allv = [r['res'][(stop_pct, tgt, entry)] for r in t]
                    n, w, net = summ(allv)
                    a = summ([r['res'][(stop_pct, tgt, entry)] for r in t if r['d'] in Y.H1])[2]
                    l90 = summ([r['res'][(stop_pct, tgt, entry)] for r in t if r['d'] in LAST90])
                    line.append(f"{tgt}: {n} tr {w} won {net:+.0f} ({a:+.0f}/{net - a:+.0f}; last 90 {l90[0]} tr {l90[2]:+.0f})")
                print(f"    {entry:6} stop {stop_pct * 100:.1f}% | " + ' | '.join(line))

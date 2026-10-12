"""The last 90 sessions: gap-up opens above the pivot (and gap-down opens below it), and what the first 15-minute
candle (9:15-9:30) looked like - a doji (small body) or a green / red candle - and what happened after it.

    python y2026_doji15.py nifty        (or sensex)

Gap up = the open above the previous session's official close; above the pivot = the open above P (the CPR's
middle line), with P, R1, S1 from the previous session's official high, low and close.
First 15-minute candle: doji = body at most 25% of its high-low range (strict doji: at most 10%); 'gravestone' =
a doji closing in the lower third of its range (long upper wick), 'dragonfly' = closing in the upper third (long
lower wick), otherwise 'neutral'. Otherwise green (closed up) or red (closed down).
After 9:30: which side of the 15-minute candle breaks first (its high or its low) and how far price then went that
way (before the other side or 3:15), whether the break failed (the other side broken later), the close of the day
against the candle's close, which pivot level was reached first from 9:30 (the next one above or the next one below
the 9:30 price, among S3 ... P ... R3), and the breakout trade: enter at the break, stop at
the other side of the 15-minute candle, out at 1x the risk or 3:15 (costs 4 Nifty / 12 Sensex points).
"""
import collections, sys
import y2026 as Y

NM, COST, N = Y.B.name, Y.COST, 90

def path(o, h, l, c):
    return (o, l, h, c) if c >= o else (o, h, l, c)

def shape(o, h, l, c):
    rng = h - l; body = abs(c - o)
    if rng <= 0: return 'doji', 'neutral', True
    if body <= 0.25 * rng:
        pos = (c - l) / rng
        return 'doji', ('gravestone' if pos < 1 / 3 else 'dragonfly' if pos > 2 / 3 else 'neutral'), body <= 0.10 * rng
    return ('green' if c > o else 'red'), None, False

def after(c1, hi, lo, LV):
    """From 9:30: first break, the run after it, failure, the trade; and which pivot level came first."""
    rest = [x for x in c1 if 570 <= x[0] <= 929]
    px = rest[0][1]
    up = min(((v, k) for k, v in LV.items() if v > px), default=(None, None))
    dn = max(((v, k) for k, v in LV.items() if v < px), default=(None, None))
    who = None
    for m, o, h, l, c in rest:
        for p in path(o, h, l, c):
            if up[0] is not None and p >= up[0]: who = 'up ' + up[1]; break
            if dn[0] is not None and p <= dn[0]: who = 'down ' + dn[1]; break
        if who: break
    lvl = dict(lv=who, up=up[1], dn=dn[1])
    brk, bm, k0 = None, None, None
    for k, (m, o, h, l, c) in enumerate(rest):
        if m >= 915: break
        for p in path(o, h, l, c):
            if p > hi: brk = 1; break
            if p < lo: brk = -1; break
        if brk: bm, k0 = m, k; break
    r = dict(brk=brk, bm=bm, **lvl)
    if not brk: return r
    e = hi if brk > 0 else lo
    other = lo if brk > 0 else hi
    risk = hi - lo
    run, failed, res = 0.0, False, None
    for m, o, h, l, c in rest[k0:]:
        if m >= 915:
            if res is None: res = brk * (c - e)
            break
        for p in path(o, h, l, c):
            if not failed:
                run = max(run, brk * (p - e))
                if brk * (p - other) <= 0: failed = True
            if res is None:
                if brk * (p - other) <= 0: res = -risk
                elif brk * (p - e) >= risk: res = risk
    r.update(run=run, failed=failed, trade=(res if res is not None else brk * (rest[-1][4] - e)) - COST, risk=risk)
    return r

if __name__ == '__main__':
    ds = Y.D26[-N:]
    rows = []
    for d in ds:
        prev = Y.days[Y.IDX[d] - 1]
        _, H, L, C = Y.DAY[prev][:4]
        P = (H + L + C) / 3
        LV = dict(P=P, R1=2 * P - L, S1=2 * P - H, R2=P + (H - L), S2=P - (H - L), R3=H + 2 * (P - L), S3=L - 2 * (H - P))
        c1 = [x for x in Y.one[d] if 555 <= x[0] <= 929]
        o = c1[0][1]
        f = [x for x in c1 if x[0] < 570]
        h15, l15, c15 = max(x[2] for x in f), min(x[3] for x in f), f[-1][4]
        kind, sub, strict = shape(o, h15, l15, c15)
        gap = 1 if o > C and o > P else -1 if o < C and o < P else 0
        r = dict(d=d, gap=gap, kind=kind, sub=sub, strict=strict, rng=h15 - l15, gpts=o - C,
                 day=c1[-1][4] - c15, o=o, c15=c15)
        r.update(after(c1, h15, l15, LV))
        rows.append(r)
    print(f"{NM.upper()}: the last {N} sessions, {ds[0]} - {ds[-1]}")
    for gsd, lab in ((1, 'GAP UP, opened above the pivot'), (-1, 'GAP DOWN, opened below the pivot')):
        g = [r for r in rows if r['gap'] == gsd]
        print(f"\n  {lab}: {len(g)} days")
        for kind in ('doji', 'green', 'red'):
            gk = [r for r in g if r['kind'] == kind]
            if not gk: continue
            b = collections.Counter(r['brk'] for r in gk)
            up = [r for r in gk if r['brk'] == 1]; dn = [r for r in gk if r['brk'] == -1]
            tr = [r['trade'] for r in gk if r['brk']]
            extra = ''
            if kind == 'doji':
                sc = collections.Counter(r['sub'] for r in gk)
                extra = f" (strict doji {sum(r['strict'] for r in gk)}; gravestone {sc['gravestone']}, dragonfly {sc['dragonfly']}, neutral {sc['neutral']})"
            print(f"    first 15-minute candle {kind.upper()}: {len(gk)} days{extra}, average range {sum(r['rng'] for r in gk) / len(gk):.0f} points")
            print(f"      broke its HIGH first {b[1]}, its LOW first {b[-1]}, neither {b[None]}")
            if up: print(f"        after the high broke: went on {sum(r['run'] for r in up) / len(up):.0f} points on average (middle {sorted(r['run'] for r in up)[len(up) // 2]:.0f}); "
                         f"the low broke later too on {sum(r['failed'] for r in up)} days")
            if dn: print(f"        after the low broke: went on {sum(r['run'] for r in dn) / len(dn):.0f} points on average (middle {sorted(r['run'] for r in dn)[len(dn) // 2]:.0f}); "
                         f"the high broke later too on {sum(r['failed'] for r in dn)} days")
            print(f"      day closed above the candle's close {sum(r['day'] > 0 for r in gk)}, below {sum(r['day'] < 0 for r in gk)}; "
                  f"average {sum(r['day'] for r in gk) / len(gk):+.0f} points")
            rs = collections.Counter((r['lv'] or 'neither').split()[0] for r in gk)
            print(f"      from 9:30, the next pivot level above was reached first {rs['up']}, the next one below {rs['down']}, neither {rs['neither']}")
            print(f"      trade the break (stop the other side, target 1x, costs in): {len(tr)} trades, {sum(x > 0 for x in tr)} won, net {sum(tr):+.0f} points")
        print("      day by day (doji days):")
        for r in g:
            if r['kind'] != 'doji': continue
            print(f"        {r['d']} gap {r['gpts']:+.0f}, {r['sub']}{' (strict)' if r['strict'] else ''}, range {r['rng']:.0f}: "
                  f"{'high' if r['brk'] == 1 else 'low' if r['brk'] == -1 else 'nothing'} broke first"
                  f"{' at ' + format(r['bm'] // 60, '02d') + ':' + format(r['bm'] % 60, '02d') if r['bm'] else ''}"
                  f"{', ran ' + format(r['run'], '.0f') + ' pts' if r['brk'] else ''}{', failed' if r.get('failed') else ''}; "
                  f"day {r['day']:+.0f} from the candle's close; first level: {r['lv'] or 'none'} ({r['dn']} below, {r['up']} above at 9:30); trade {r.get('trade', 0):+.0f}")

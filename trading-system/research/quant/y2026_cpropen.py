"""The last 60 sessions: when the market opens away from the CPR (above it or below it), does it keep going away
(above -> up, below -> down) or turn back toward the CPR? First 1-minute candle, first 5-minute candle, the rest of
the day, and which comes first: the next pivot level (R1 / R2 / R3 above, S1 / S2 / S3 below) or the CPR.

    python y2026_cpropen.py nifty        (or sensex; add 60 for the 60 sessions before those)

CPR and pivots from the previous session's official high, low and close: P = (H + L + C) / 3, BC = (H + L) / 2,
TC = 2P - BC; R1 = 2P - L, S1 = 2P - H, R2 = P + (H - L), S2 = P - (H - L), R3 = H + 2(P - L), S3 = L - 2(H - P).
'Away' = the open is above the CPR's top or below its bottom. 'Continues' = moves further away from the CPR.
Scalps (costs 4 Nifty / 12 Sensex points): at 9:16 or 9:20 in the direction of the first 1- / 5-minute candle,
or against it; out at +0.1% / -0.1% of price, whichever comes first, or after 30 minutes.
"""
import collections, sys
import y2026 as Y

NM, COST = Y.B.name, Y.COST
N = 60

def path(o, h, l, c):
    return (o, l, h, c) if c >= o else (o, h, l, c)

def first_touch(c1, up_level, dn_level, start=0):
    """Which is touched first from candle `start` on: 'up' (price >= up_level) or 'dn' (price <= dn_level)."""
    for m, o, h, l, c in c1[start:]:
        for p in path(o, h, l, c):
            if up_level is not None and p >= up_level: return 'up', m
            if dn_level is not None and p <= dn_level: return 'dn', m
    return None, None

def scalp(c1, i0, side, e, pct):
    """Enter at e at candle i0's open, +pct / -pct of price, out after 30 minutes."""
    x = pct * e; tgt, stp = e + side * x, e - side * x
    for m, o, h, l, c in c1[i0:i0 + 30]:
        for p in path(o, h, l, c):
            if side * (p - stp) <= 0: return -x - COST
            if side * (p - tgt) >= 0: return x - COST
    return side * (c1[min(i0 + 29, len(c1) - 1)][4] - e) - COST

def day(d, prev):
    _, H, L, C = Y.DAY[prev][:4]
    P = (H + L + C) / 3; BC = (H + L) / 2; TC = 2 * P - BC
    top, bot = max(TC, BC), min(TC, BC)
    R = [2 * P - L, P + (H - L), H + 2 * (P - L)]
    S = [2 * P - H, P - (H - L), L - 2 * (H - P)]
    c1 = [x for x in Y.one[d] if 555 <= x[0] <= 929]
    o = c1[0][1]
    side = 1 if o > top else -1 if o < bot else 0
    r = dict(d=d, side=side, o=o, close=c1[-1][4])
    if side == 0: return r
    lv = top if side > 0 else bot
    piv = [x for x in (R if side > 0 else S) if side * (x - o) > 0]
    nxt = piv[0] if piv else None
    names = (['R1', 'R2', 'R3'] if side > 0 else ['S1', 'S2', 'S3'])
    r.update(dist=100 * side * (o - lv) / o,
             zone=('beyond ' + names[2]) if not piv else ('before ' + names[(R if side > 0 else S).index(nxt)]),
             c1=side * (c1[0][4] - c1[0][1]), c5=side * (c1[4][4] - o),
             day=side * (c1[-1][4] - o),
             fav30=max(side * (x[2 if side > 0 else 3] - o) for x in c1[:30]),
             adv30=max(-side * (x[3 if side > 0 else 2] - o) for x in c1[:30]))
    up, dn = (nxt, lv) if side > 0 else (lv, nxt)
    who, m = first_touch(c1, up, dn)
    r['first'] = None if who is None else ('pivot' if (who == 'up') == (side > 0) else 'CPR')
    r['first_m'] = m
    r['pivot_name'] = names[(R if side > 0 else S).index(nxt)] if nxt else None
    d5 = 1 if c1[4][4] > o else -1 if c1[4][4] < o else 0
    d1 = 1 if c1[0][4] > c1[0][1] else -1 if c1[0][4] < c1[0][1] else 0
    r['s1_with'] = scalp(c1, 1, d1, c1[1][1], 0.001) if d1 else None
    r['s5_with'] = scalp(c1, 5, d5, c1[5][1], 0.001) if d5 else None
    r['s5_against'] = scalp(c1, 5, -d5, c1[5][1], 0.001) if d5 else None
    r['s_away'] = scalp(c1, 5, side, c1[5][1], 0.001)
    r['s_back'] = scalp(c1, 5, -side, c1[5][1], 0.001)
    # small-gap magnet: open less than 0.2% beyond the CPR -> at 9:16 trade back to the CPR edge, stop as far the
    # other way (1:1), out by 3:15
    e = c1[1][1]; dist = side * (e - lv)
    r['mag_small'] = None
    if r['dist'] < 0.2 and dist > 0:
        tgt, stp = lv, e + side * dist
        res = None
        for m, o_, h, l, c in c1[1:]:
            if m >= 915: res = -side * (c - e); break
            for p_ in path(o_, h, l, c):
                if side * (p_ - stp) >= 0: res = -dist; break
                if side * (p_ - tgt) <= 0: res = dist; break
            if res is not None: break
        r['mag_small'] = (res if res is not None else -side * (c1[-1][4] - e)) - COST
    return r

def pct(a, b): return f"{a} of {b} ({100 * a / b:.0f}%)" if b else "-"

if __name__ == '__main__':
    off = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    ds = Y.D26[len(Y.D26) - N - off:len(Y.D26) - off]
    print(f"index {Y.one[ds[0]][0][1]:,.0f} at the start, {Y.one[ds[-1]][-1][4]:,.0f} at the end")
    rows = [day(d, Y.days[Y.IDX[d] - 1]) for d in ds]
    print(f"{NM.upper()}: the last {N} sessions, {ds[0]} - {ds[-1]}")
    inside = [r for r in rows if r['side'] == 0]
    print(f"  opened inside the CPR: {len(inside)} days")
    for side, lab in ((1, 'ABOVE the CPR'), (-1, 'BELOW the CPR')):
        g = [r for r in rows if r['side'] == side]
        if not g: continue
        w = 'up' if side > 0 else 'down'
        print(f"\n  OPENED {lab}: {len(g)} days (open {sum(r['dist'] for r in g) / len(g):.2f}% away on average)")
        print(f"    first 1-minute candle went {w} (away from the CPR): {pct(sum(r['c1'] > 0 for r in g), len(g))}; back toward it: {sum(r['c1'] < 0 for r in g)}")
        print(f"    first 5 minutes went {w}: {pct(sum(r['c5'] > 0 for r in g), len(g))}; back toward it: {sum(r['c5'] < 0 for r in g)}")
        print(f"    day closed further {w} than the open: {pct(sum(r['day'] > 0 for r in g), len(g))}; average {sum(r['day'] for r in g) / len(g):+.0f} points")
        print(f"    first 30 minutes: average move {w} {sum(r['fav30'] for r in g) / len(g):.0f} points, the other way {sum(r['adv30'] for r in g) / len(g):.0f}")
        fp = collections.Counter(r['first'] for r in g)
        print(f"    reached first: the next pivot level {fp['pivot']}, the CPR {fp['CPR']}, neither {fp[None]}")
        for z in sorted({r['zone'] for r in g}):
            gz = [r for r in g if r['zone'] == z]
            f = collections.Counter(r['first'] for r in gz)
            print(f"      opened {z}: {len(gz)} days -> pivot first {f['pivot']}, CPR first {f['CPR']}, neither {f[None]}; "
                  f"first 5 min {w} {sum(r['c5'] > 0 for r in gz)}; day closed further {w} {sum(r['day'] > 0 for r in gz)}")
        for lo, hi, lab2 in ((0, 0.2, 'less than 0.2% away'), (0.2, 99, '0.2% or more away (Magnet size)')):
            gz = [r for r in g if lo <= r['dist'] < hi]
            if not gz: continue
            f = collections.Counter(r['first'] for r in gz)
            print(f"      {lab2}: {len(gz)} days -> pivot first {f['pivot']}, CPR first {f['CPR']}, neither {f[None]}; "
                  f"first 5 min {w} {sum(r['c5'] > 0 for r in gz)}; day closed further {w} {sum(r['day'] > 0 for r in gz)}")
        for k, lab3 in (('s_away', f'9:20 trade {w} (away from the CPR)'), ('s_back', '9:20 trade back toward the CPR'),
                        ('s1_with', '9:16 trade with the first 1-minute candle'), ('s5_with', '9:20 trade with the first 5 minutes'),
                        ('s5_against', '9:20 trade against the first 5 minutes')):
            v = [r[k] for r in g if r[k] is not None]
            print(f"    scalp {lab3}: {len(v)} trades, {sum(x > 0 for x in v)} won, net {sum(v):+.0f} points after costs")
        v = [r['mag_small'] for r in g if r.get('mag_small') is not None]
        print(f"    small-gap magnet (open < 0.2% away; 9:16 back to the CPR, stop as far the other way): {len(v)} trades, "
              f"{sum(x > 0 for x in v)} won, net {sum(v):+.0f} points after costs")
    print("\n  day by day (+ = moved away from the CPR, - = back toward it):")
    for r in rows:
        if r['side'] == 0:
            print(f"    {r['d']} opened inside the CPR"); continue
        print(f"    {r['d']} opened {'above' if r['side'] > 0 else 'below'} {r['dist']:.2f}% ({r['zone']}): first 1 min {r['c1']:+5.0f}, "
              f"first 5 min {r['c5']:+5.0f}, day {r['day']:+6.0f}; first reached: {r['first'] or 'neither'}"
              f"{' (' + r['pivot_name'] + ')' if r['first'] == 'pivot' else ''}"
              f"{' at ' + format(r['first_m'] // 60, '02d') + ':' + format(r['first_m'] % 60, '02d') if r['first_m'] else ''}")

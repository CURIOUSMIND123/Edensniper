"""Order-flow delta for the calls (asked on 23 October 2026, after an order-flow / footprint chart on a YouTube stream).
True delta (buyer- minus seller-initiated volume) needs every trade; free data has only 1-minute candles. So each
1-minute candle of the near Nifty future gives an estimate: delta = volume x ((close - low) - (high - close)) / (high -
low) (all buying when it closes at the high, all selling at the low). Data: the October 2026 future (listed 29 July;
Upstox has no free candles of expired contracts), so 29 July - 23 October 2026 only, about 60 sessions: a first look,
not a test like the others. Trades on the index price at a 5-minute close, 9:20-2:30, one at a time; costs 4 / 12; a
candle reaching both the stop and the target counts as the stop.

    python delta_test.py nifty      (or sensex: Sensex trades, with the Nifty future's delta; Sensex's own future is
                                     too thin, 1-3% of Nifty's volume)

SURGE      a 5-minute candle with |delta| >= r x its volume, volume >= k x the day's average 5-minute volume so far,
           and the index candle the same way -> that way
LEVEL      a 5-minute close through a level (the CPR top / bottom, the 15-minute high / low, yesterday's high / low, the
           3-day volume lines) with delta >= r x volume the same way -> that way
ABSORB     a 5-minute candle makes a new high of the day with delta <= -r x volume (sellers absorbing the buying) ->
           SELL; a new low with delta >= r x volume -> BUY
Stop: the candle's other end (at most 55 / 170 points); out at 2x the stop, trailing 1x after +1x, or held to 3:15.
FILTER     the alert program's own calls (default + extra calls), split by the delta of the 5 / 15 minutes before the
           entry: with the call's direction, against it, or flat (under 10% of the volume either way).
"""
import collections, datetime as dt, itertools, json, os, sys
sys.path.insert(0, '../../alerts')
import cprb_alerts as A

NM = sys.argv[1] if len(sys.argv) > 1 else 'nifty'
SPEC = A.SPEC[NM]
COST, CAP = SPEC['cost'], A.STOP_MAX[NM]
C = '../.cache/fut'
FUT = json.load(open(f'{C}/NSE_FO_48704.json'))          # NIFTY FUT 27 OCT 26
D0, D1 = dt.date(2026, 7, 29), dt.date(2026, 10, 23)

def cached(key, a, b):
    p = f"{C}/{key.replace('|', '_')}_{a}_{b}.json"
    if os.path.exists(p):
        return {d: {int(m): v for m, v in mm.items()} for d, mm in json.load(open(p)).items()}
    raw = A.fetch_range(key, a, b)
    if b >= dt.date(2026, 10, 23):
        raw.update(A.fetch_today(key))
    json.dump({d: {str(m): v for m, v in mm.items()} for d, mm in raw.items()}, open(p, 'w'))
    return raw

idx = cached(SPEC['key'], dt.date(2026, 5, 15), D1)
bees = cached(A.BEES, dt.date(2026, 5, 15), D1)
daily = A.fetch_daily(SPEC['key'], dt.date(2026, 5, 15), D1)
sess = {d: [(m,) + tuple(mm[m][:4]) for m in sorted(mm)] for d, mm in idx.items()}
vol = {d: {m: v[4] for m, v in mm.items()} for d, mm in bees.items()}
DAYS = [d for d in sorted(sess) if D0 <= dt.date.fromisoformat(d) <= D1 and len(sess[d]) >= 300 and d in FUT]

def blocks(c1, fut):
    """5-minute candles of the index with the future's volume and estimated delta."""
    out = []
    for k in range(75):
        m0 = A.OPEN + 5 * k
        rows = [x for x in c1 if m0 <= x[0] < m0 + 5]
        if len(rows) < 5:
            continue
        v = dl = 0.0
        for m in range(m0, m0 + 5):
            f = fut.get(str(m))
            if f:
                o, h, l, c, vv = f[:5]
                v += vv
                dl += vv * (((c - l) - (h - c)) / (h - l) if h > l else 0)
        out.append((m0, rows[0][1], max(x[2] for x in rows), min(x[3] for x in rows), rows[-1][4], v, dl))
    return out

def walk(c1, side, e, start, stp, tgt, trail):
    best = e
    for m, o, h, l, c in c1:
        if m < start:
            continue
        adv, fav = (l, h) if side > 0 else (h, l)
        if side * (o - stp) <= 0:
            return side * (o - e) - COST, m
        if side * (adv - stp) <= 0:
            return side * (stp - e) - COST, m
        if tgt is not None and side * (fav - tgt) >= 0:
            return side * (tgt - e) - COST, m
        if trail:
            best = max(best, h) if side > 0 else min(best, l)
            if side * (best - e) >= trail and side * (best - side * trail - stp) > 0:
                stp = best - side * trail
        if m >= A.OUT:
            return side * (c - e) - COST, m
    return side * (c1[-1][4] - e) - COST, c1[-1][0]

CX = {}
def levels(d):
    if d not in CX:
        cx = A.context(SPEC, sess, vol, d, daily)
        lv = cx['lv']
        CX[d] = [lv['top'], lv['bot'], cx['yh'], cx['yl']] + list(cx['lines'])
    return CX[d]

def day(d, rule, r, k, how):
    c1, b5 = sess[d], blocks(sess[d], FUT[d])
    first = [x for x in c1 if x[0] < A.RANGE_END]
    lv = levels(d) + [max(x[2] for x in first), min(x[3] for x in first)]
    out, free = [], 0
    for j in range(1, len(b5)):
        m0, o, h, l, c, v, dl = b5[j]
        if m0 < A.OPEN + 5 or m0 + 5 > A.VOL_END or m0 < free or v <= 0:
            continue
        side = 0
        if rule == 'surge':
            avg = sum(x[5] for x in b5[:j]) / j
            if abs(dl) >= r * v and v >= k * avg and (c - o) * dl > 0:
                side = 1 if dl > 0 else -1
        elif rule == 'level':
            pc = b5[j - 1][4]
            for x in (lv if m0 >= A.RANGE_END else lv[:-2]):
                s = 1 if pc < x <= c else -1 if pc > x >= c else 0
                if s and s * dl >= r * v:
                    side = s
                    break
        else:                                          # absorb
            hi = max(y[2] for y in b5[:j]); lo = min(y[3] for y in b5[:j])
            if h > hi and dl <= -r * v:
                side = -1
            elif l < lo and dl >= r * v:
                side = 1
        if not side:
            continue
        risk = min(CAP, (c - l) if side > 0 else (h - c))
        if risk <= 0:
            continue
        p, mx = walk(c1, side, c, m0 + 5, c - side * risk, c + side * 2 * risk if how == '2x' else None,
                     risk if how == 'trail' else None)
        out.append((d, p))
        free = mx + 1
    return out

def stats(rows):
    halves = (('Aug-Sep', lambda d: d < '2026-10-01'), ('Oct', lambda d: d >= '2026-10-01'), ('all', lambda d: True))
    res = {}
    for nm, f in halves:
        p = [x for d, x in rows if f(d)]
        res[nm] = (len(p), round(100 * sum(x > 0 for x in p) / len(p)) if p else 0, round(sum(p)))
    return res

def calls_by_delta():
    print("\nFILTER: the alert program's calls by the delta before the entry (trades, won %, net: Aug-Sep | Oct | all)")
    A.RULES, A.SWEEP = 'classic', False
    rows = []
    for d in DAYS:
        cx = A.context(SPEC, sess, vol, d, daily)
        cx['tvol'] = vol.get(d, {})
        for t in A.day_trades(cx, sess[d], 929, True, False, 'classic'):
            if t['taken'] and t['exit']:
                rows.append((d, t))
    for mins in (5, 15):
        groups = collections.defaultdict(list)
        for d, t in rows:
            m1 = t['known']                                  # the entry is known at the start of this minute
            v = dl = 0.0
            for m in range(m1 - mins, m1):
                f = FUT[d].get(str(m))
                if f:
                    o, h, l, c, vv = f[:5]
                    v += vv
                    dl += vv * (((c - l) - (h - c)) / (h - l) if h > l else 0)
            g = 'flat' if v <= 0 or abs(dl) < 0.1 * v else 'with' if dl * t['side'] > 0 else 'against'
            groups[g].append((d, t['exit']['pnl']))
        for g in ('with', 'flat', 'against'):
            s_ = stats(groups[g])
            print(f"  last {mins:2} min, delta {g:8} " + ' | '.join(f"{n:3} tr {w:3}% {p:+6}" for n, w, p in s_.values()))

if __name__ == '__main__':
    print(f"{NM.upper()} with the Nifty future's estimated delta, {DAYS[0]} - {DAYS[-1]} ({len(DAYS)} sessions); costs {COST:g}")
    print("  trades, won %, net points: Aug-Sep | Oct | all")
    good = []
    for rule, r, k, how in itertools.chain(
            itertools.product(['surge'], (0.25, 0.35, 0.5), (1.5, 2.0), ('2x', 'trail', '3:15')),
            itertools.product(['level'], (0.15, 0.25, 0.35), (0,), ('2x', 'trail', '3:15')),
            itertools.product(['absorb'], (0.1, 0.2, 0.3), (0,), ('2x', 'trail', '3:15'))):
        s = stats([x for d in DAYS for x in day(d, rule, r, k, how)])
        lab = f"{rule} r {r:g}" + (f" k {k:g}" if rule == 'surge' else '') + f", {how}"
        print(f"  {lab:24} " + ' | '.join(f"{n:3} tr {w:3}% {p:+6}" for n, w, p in s.values()))
        if s['Aug-Sep'][2] > 0 and s['Oct'][2] > 0:
            good.append((lab, s))
    print("\nmade money in both Aug-Sep and Oct:")
    for lab, s in good:
        print(f"  {lab:24} " + ' | '.join(f"{n:3} tr {w:3}% {p:+6}" for n, w, p in s.values()))
    if not good:
        print("  none")
    calls_by_delta()

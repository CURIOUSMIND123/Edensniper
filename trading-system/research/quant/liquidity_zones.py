"""After 12:00: price breaks the morning high, runs up to the next liquidity zone above it, taps it and comes back
(and the other way at the morning low). Asked on 29 October 2026. 2026, and 2023-2025 as a check; 1-minute candles.

    python liquidity_zones.py nifty        (or sensex)

The zones, the nearest one beyond the 9:15-12:00 high (at least 0.03% beyond it): yesterday's high, the highs of the
2-5 sessions before, the pivots R1 / R2 (and the CPR when it is above), the 3-day volume lines, the volume POC, a round
number (Nifty 100s, Sensex 500s). The mirror below the morning low for BUYs.
The event: between 12:00 and 2:45, price trades beyond the morning high and then reaches that zone (a tap).
After the tap: how far it went beyond the zone first, how far it came back, whether it fell T points (75 Nifty / 200
Sensex) before rising S points (35 / 100) beyond the zone, whether it got back to the morning high.
The trades: SELL at the zone on the tap (a limit order), or at the first 5-minute close back below it within 30
minutes; stop S points beyond the zone (or beyond the tap's extreme); target T points or back at the morning high;
out by 3:15. Costs 4 / 12; a candle reaching both the stop and the target counts as the stop.
"""
import collections, datetime as dt, json, os, statistics as st, sys
sys.path.insert(0, '../../alerts')
import cprb_alerts as A

NM = sys.argv[1] if len(sys.argv) > 1 else 'nifty'
SPEC = A.SPEC[NM]
COST, CAP = SPEC['cost'], A.STOP_MAX[NM]
T, SL = {'nifty': (75, 35), 'sensex': (200, 100)}[NM]
ROUND = {'nifty': 100, 'sensex': 500}[NM]
NOON, LAST = 720, 885

def cache_1m(name, key):
    raw = json.load(open(f'../.cache/{name}_1m.json'))
    if os.path.exists(f'../.cache/{name}_1m_old.json'):          # NIFTYBEES 2023-2024
        raw.update(json.load(open(f'../.cache/{name}_1m_old.json')))
    out = collections.defaultdict(dict)
    for k, v in raw.items():
        out[k[:10]][int(k[11:13]) * 60 + int(k[14:16])] = v
    last = dt.date.fromisoformat(max(out))
    p = f'../.cache/lz_{name}_tail.json'
    if not os.path.exists(p):
        json.dump({d: {str(m): v for m, v in mm.items()} for d, mm in
                   A.fetch_range(key, last + dt.timedelta(days=1), dt.date(2026, 10, 28)).items()}, open(p, 'w'))
    for d, mm in json.load(open(p)).items():
        out[d] = {int(m): v for m, v in mm.items()}
    return out

RAW = cache_1m(NM, SPEC['key'])
S = {d: [(m,) + tuple(mm[m][:4]) for m in sorted(mm)] for d, mm in RAW.items() if len(mm) >= 300}
BEES = cache_1m('niftybees', A.BEES)
VOL = {d: {m: v[4] for m, v in mm.items()} for d, mm in BEES.items()}
DAILY = A.fetch_daily(SPEC['key'], dt.date(2022, 11, 1), dt.date(2026, 10, 28))
DAYS = sorted(S)

def zones(d):
    """[(price, kind)] around day d: known before it opens."""
    cx = A.context(SPEC, S, VOL, d, DAILY)
    lv, H, L = cx['lv'], cx['yh'], cx['yl']
    P = lv['p']
    z = [(H, 'yesterday high'), (L, 'yesterday low'), (2 * P - L, 'pivot R1 / S1'), (2 * P - H, 'pivot R1 / S1'),
         (P + (H - L), 'pivot R2 / S2'), (P - (H - L), 'pivot R2 / S2'),
         (lv['top'], 'CPR'), (lv['bot'], 'CPR'), (P, 'CPR')]
    z += [(x, 'volume line') for x in cx['lines']]
    if cx.get('poc_ref') is not None:
        z.append((cx['poc_ref'], 'POC'))
    prev = [x for x in DAYS if x < d][-5:-1]               # the 2-5 sessions before
    for x in prev:
        z += [(max(c[2] for c in S[x]), 'earlier days high / low'), (min(c[3] for c in S[x]), 'earlier days high / low')]
    return z

def first_pass(c1, start, side, e, down, up):
    """Did price go `down` points the trade's way before `up` points against it (from e, minute start on)?"""
    for m, o, h, l, c in c1:
        if m < start:
            continue
        adv, fav = (h, l) if side < 0 else (l, h)
        if side * (adv - e) <= -up:
            return 'against'
        if side * (fav - e) >= down:
            return 'way'
    return 'neither'

def walk(c1, side, e, start, stp, tgt):
    for m, o, h, l, c in c1:
        if m < start:
            continue
        adv, fav = (l, h) if side > 0 else (h, l)
        if side * (o - stp) <= 0:
            return side * (o - e) - COST
        if side * (adv - stp) <= 0:
            return side * (stp - e) - COST
        if tgt is not None and side * (fav - tgt) >= 0:
            return side * (tgt - e) - COST
        if m >= A.OUT:
            return side * (c - e) - COST
    return side * (c1[-1][4] - e) - COST

EV = []
for d in DAYS:
    if d < '2023-03-01':
        continue
    try:
        z = zones(d)
    except (SystemExit, IndexError):                   # too few earlier sessions, or no volume
        continue
    c1 = S[d]
    am, pm = [x for x in c1 if x[0] < NOON], [x for x in c1 if NOON <= x[0] <= LAST]
    mh, ml = max(x[2] for x in am), min(x[3] for x in am)
    for side, lvl in ((-1, mh), (1, ml)):                  # -1: above the high -> SELL at the zone; +1: below the low -> BUY
        gap = 0.0003 * lvl
        cand = [(p, k) for p, k in z if -side * (p - lvl) >= gap]
        r = lvl // ROUND * ROUND if side > 0 else (lvl // ROUND + 1) * ROUND
        while -side * (r - lvl) < gap:
            r -= side * ROUND
        cand.append((r, 'round number'))
        zp, zk = min(cand, key=lambda pk: abs(pk[0] - lvl))
        i0 = next((i for i, x in enumerate(pm) if (x[2] > lvl if side < 0 else x[3] < lvl)), None)
        if i0 is None:
            continue
        it = next((i for i in range(i0, len(pm)) if (pm[i][2] >= zp if side < 0 else pm[i][3] <= zp)), None)
        ev = dict(d=d, side=side, kind=zk, dist=abs(zp - lvl), tapped=it is not None)
        if it is not None:
            tm = pm[it][0]
            rest = [x for x in c1 if x[0] >= tm]
            ev.update(tm=tm, zp=zp, lvl=lvl,
                      over=-side * ((max(x[2] for x in rest) if side < 0 else min(x[3] for x in rest)) - zp),
                      fp=first_pass(c1, tm, side, zp, T, SL), home=any((x[3] <= lvl if side < 0 else x[2] >= lvl) for x in rest[1:]))
            ev['back'] = abs((min(x[3] for x in rest) if side < 0 else max(x[2] for x in rest)) - zp)
            # trades: a limit at the zone; a 5-minute close back inside within 30 minutes
            res = {}
            for nm, stp, tgt in (('limit, stop S beyond, target T', zp - side * SL, zp + side * T),
                                 ('limit, stop S beyond, target the morning side', zp - side * SL, lvl),
                                 ('limit, stop 2S beyond, target T', zp - side * 2 * SL, zp + side * T)):
                res[nm] = walk(c1, side, zp, tm, stp, tgt) if side * (tgt - zp) > 0 else None   # the tap minute too
            b0 = NOON + (tm - NOON) // 5 * 5
            for k in range(7):
                m0 = b0 + 5 * k
                b = [x for x in c1 if m0 <= x[0] < m0 + 5]
                if len(b) < 5 or m0 + 5 > LAST + 15:
                    break
                c = b[-1][4]
                if side * (c - zp) > 0:                    # closed back inside the zone
                    ext = max(x[2] for x in c1 if tm <= x[0] < m0 + 5) if side < 0 else min(x[3] for x in c1 if tm <= x[0] < m0 + 5)
                    stp = ext - side * 0.0002 * ext
                    risk = side * (c - stp)
                    if 0 < risk:
                        if risk > CAP:
                            stp, risk = c - side * CAP, CAP
                        res['5-min close back, stop beyond the tap, target T'] = walk(c1, side, c, m0 + 5, stp, c + side * T)
                    break
            ev['trades'] = res
        EV.append(ev)

def pct(n, d):
    return f"{round(100 * n / d):3}%" if d else '  - '

if __name__ == '__main__':
    for yrs, f in (('2026', lambda d: d >= '2026-01-01'), ('2023-2025', lambda d: d < '2026-01-01')):
        ev = [e for e in EV if f(e['d'])]
        tap = [e for e in ev if e['tapped']]
        print(f"\n{NM.upper()} {yrs}: after 12:00 price went beyond the morning high / low {len(ev)} times; reached the next zone "
              f"{len(tap)} times ({pct(len(tap), len(ev))}), zone on average {st.mean(e['dist'] for e in ev):.0f} points beyond")
        print(f"  after the tap (T = {T}, S = {SL} points): kind of zone, taps, came back T before going S beyond the zone, went S "
              f"beyond first, typical overshoot / come-back (median points), back to the morning high / low")
        groups = collections.defaultdict(list)
        for e in tap:
            groups[e['kind']].append(e)
            groups['ALL ZONES'].append(e)
        for k in ['ALL ZONES'] + sorted(x for x in groups if x != 'ALL ZONES'):
            g = groups[k]
            fp = collections.Counter(e['fp'] for e in g)
            print(f"    {k:24} {len(g):4} taps: back {T} first {pct(fp['way'], len(g))}, {SL} beyond first {pct(fp['against'], len(g))}, "
                  f"overshoot {st.median(e['over'] for e in g):5.0f}, come-back {st.median(e['back'] for e in g):5.0f}, "
                  f"to the morning side {pct(sum(e['home'] for e in g), len(g))}")
        print("  the trades (all zones; and the best kind of zone): trades, won %, net points")
        names = sorted({n for e in tap for n in e['trades']})
        for n in names:
            rows = [(e['kind'], e['trades'][n]) for e in tap if e['trades'].get(n) is not None]
            p = [x for _, x in rows]
            by = collections.defaultdict(list)
            for k, x in rows:
                by[k].append(x)
            best = max(by.items(), key=lambda kv: sum(kv[1]))
            print(f"    {n:48} {len(p):4} tr {pct(sum(x > 0 for x in p), len(p))} {sum(p):+7.0f} | best: {best[0]} "
                  f"{len(best[1])} tr {pct(sum(x > 0 for x in best[1]), len(best[1]))} {sum(best[1]):+6.0f}")

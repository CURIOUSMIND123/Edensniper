"""CPR + pivot strategies: pick on the last 60 sessions, then check the 30 before them and every year since 2023.

    python cpr_backtest.py nifty        (or sensex)

Families (each in both directions, one trade at a time, out by 15:15, exits checked on 1-minute candles):
  magnet    open outside the CPR -> trade back toward it (the "opposite direction" idea)
  orb       break of the opening range (target lvl1 / lvl2 = the nearest / second pivot or CPR line beyond), optionally only on narrow-CPR days (the "squeeze" idea)
  cprbreak  a 5-minute close through the CPR -> trade in the break's direction
  reject    a 5-minute candle pokes through R1 / S1 (or R2 / S2) and closes back -> trade back toward the pivot
  bias      open above / below the CPR -> hold the day in one direction
Percent stops are of the index price (0.1% is about 22 Nifty points). Costs: 4 Nifty / 12 Sensex points a trade.
"""
import json, collections, itertools, statistics as st, sys
name = sys.argv[1] if len(sys.argv) > 1 else 'nifty'
COST = {'nifty': 4.0, 'sensex': 12.0}[name]
T_OUT = 915                                                        # 15:15
raw = json.load(open(f'../.cache/{name}_1m.json'))
by = collections.defaultdict(list)
for k in sorted(raw):
    hm = int(k[11:13]) * 60 + int(k[14:16])
    if 555 <= hm < 930: by[k[:10]].append((hm, *raw[k]))
days = [d for d in sorted(by) if len(by[d]) >= 300]
one = {d: by[d] for d in days}
five = {}
for d in days:
    g = collections.OrderedDict()
    for m, o, h, l, c in one[d]: g.setdefault((m - 555) // 5, []).append((m, o, h, l, c))
    five[d] = [(555 + 5 * k, ch[0][1], max(x[2] for x in ch), min(x[3] for x in ch), ch[-1][4]) for k, ch in g.items()]
DAY = {d: (one[d][0][1], max(x[2] for x in one[d]), min(x[3] for x in one[d]), one[d][-1][4]) for d in days}

def levels(prev):
    h, l, c = DAY[prev][1:]
    p = (h + l + c) / 3; bc = (h + l) / 2; tc = 2 * p - bc
    return dict(p=p, top=max(tc, bc), bot=min(tc, bc), r1=2 * p - l, s1=2 * p - h, r2=p + h - l, s2=p - (h - l),
                r3=h + 2 * (p - l), s3=l - 2 * (h - p), w=abs(tc - bc) / p * 100)

LV, TEST = {}, days[21:]
for i in range(21, len(days)):
    lv = levels(days[i - 1]); past = [levels(days[j - 1])['w'] for j in range(i - 20, i)]
    lv['rank'] = sum(x < lv['w'] for x in past) / 20
    LV[days[i]] = lv

def wid_ok(lv, f): return f == 'any' or (f == 'narrow') == (lv['rank'] < 1 / 3)

def path(o, h, l, c): return (o, l, h, c) if c >= o else (o, h, l, c)

def sim(d, side, start, e, stp, tgt):
    """Enter at price e; exits from the 1-minute candle starting at `start`. Returns (pnl after costs, exit minute)."""
    for m, o, h, l, c in one[d]:
        if m < start: continue
        for px in path(o, h, l, c):
            if side * (px - stp) <= 0: return side * (stp - e) - COST, m
            if tgt is not None and side * (px - tgt) >= 0: return side * (tgt - e) - COST, m
        if m >= T_OUT: return side * (c - e) - COST, m
    return side * (one[d][-1][4] - e) - COST, one[d][-1][0]

def beyond(lv, side, e, n):
    """The n-th pivot level (1 = nearest) beyond price e in the trade's direction, or None."""
    ls = sorted(x for x in (lv['r1'], lv['r2'], lv['r3'], lv['p'], lv['top'], lv['bot']) if x > e) if side > 0 else \
         sorted((x for x in (lv['s1'], lv['s2'], lv['s3'], lv['p'], lv['top'], lv['bot']) if x < e), reverse=True)
    return ls[n - 1] if len(ls) >= n else None

def magnet(d, conf, dmin, tgt_kind, stop, wf):
    lv = LV[d]
    if not wid_ok(lv, wf): return []
    o = one[d][0][1]
    side = -1 if o > lv['top'] else 1 if o < lv['bot'] else 0
    if not side: return []
    if conf == '1m': m, e = 556, one[d][0][4]
    else:
        n = 1 if conf == '5m' else 3
        b = five[d][:n]; e = b[-1][4]; m = b[-1][0] + 5
        if side * (e - b[0][1]) <= 0: return []                    # first candle(s) must move toward the CPR
    edge = lv['top'] if side < 0 else lv['bot']
    if side * (edge - e) < dmin / 100 * e: return []                # already too close to (or inside) the CPR
    tgt = {'edge': edge, 'pivot': lv['p'], 'far': lv['bot'] if side < 0 else lv['top']}[tgt_kind]
    return [(d,) + sim(d, side, m, e, e - side * stop / 100 * e, tgt)]

def orb(d, orm, wf, stop, tgt_kind, cut):
    lv = LV[d]
    if not wid_ok(lv, wf): return []
    b = five[d]; k = orm // 5; hi = max(x[2] for x in b[:k]); lo = min(x[3] for x in b[:k])
    for x in b[k:]:
        if x[0] + 5 > cut: break
        side = 1 if x[4] > hi else -1 if x[4] < lo else 0
        if not side: continue
        e = x[4]
        stp = (lo if side > 0 else hi) if stop == 'or' else e - side * stop / 100 * e
        if side * (e - stp) <= 0: return []
        tgt = {'lvl1': beyond(lv, side, e, 1), 'lvl2': beyond(lv, side, e, 2), '2R': e + side * 2 * abs(e - stp), 'close': None}[tgt_kind]
        return [(d,) + sim(d, side, x[0] + 5, e, stp, tgt)]
    return []

def cprbreak(d, wf, stop, tgt_kind, cut):
    lv = LV[d]
    if not wid_ok(lv, wf): return []
    b = five[d]
    for i in range(1, len(b)):
        x = b[i]
        if x[0] + 5 > cut: break
        side = 1 if x[4] > lv['top'] >= b[i - 1][4] else -1 if x[4] < lv['bot'] <= b[i - 1][4] else 0
        if not side: continue
        e = x[4]
        stp = (lv['bot'] - 0.0005 * e if side > 0 else lv['top'] + 0.0005 * e) if stop == 'cpr' else e - side * stop / 100 * e
        tgt = {'lvl1': beyond(lv, side, e, 1), '2R': e + side * 2 * abs(e - stp), 'close': None}[tgt_kind]
        return [(d,) + sim(d, side, x[0] + 5, e, stp, tgt)]
    return []

def reject(d, lvls, wf, stop, tgt_kind):
    lv = LV[d]
    if not wid_ok(lv, wf): return []
    out, free = [], 0
    for x in five[d]:
        if x[0] < free or x[0] + 5 > 870 or len(out) >= 2: continue
        side = 0
        for r, s in (('r1', 's1'), ('r2', 's2'))[:lvls]:
            if x[2] >= lv[r] > x[4]: side, lvl = -1, lv[r]
            elif x[3] <= lv[s] < x[4]: side, lvl = 1, lv[s]
        if not side: continue
        e = x[4]
        stp = (x[2] if side < 0 else x[3]) + side * -0.0005 * e if stop == 'candle' else e - side * stop / 100 * e
        tgt = {'pivot': lv['p'], 'cpr': lv['top'] if side < 0 else lv['bot'], '2R': e + side * 2 * abs(e - stp)}[tgt_kind]
        if side * (tgt - e) <= 0: continue
        pnl, mx = sim(d, side, x[0] + 5, e, stp, tgt); out.append((d, pnl, mx)); free = mx + 1
    return out

def bias(d, mode, stop, wf):
    lv = LV[d]
    if not wid_ok(lv, wf): return []
    o = one[d][0][1]; pos = 1 if o > lv['top'] else -1 if o < lv['bot'] else 0
    if not pos: return []
    side = -pos if mode == 'fade' else pos; e = one[d][0][4]
    return [(d,) + sim(d, side, 556, e, e - side * stop / 100 * e, None)]

W = ('any', 'narrow', 'notnarrow')
VARIANTS = (
    [('magnet', a) for a in itertools.product(('1m', '5m', '15m'), (0, 0.1, 0.2), ('edge', 'pivot', 'far'), (0.1, 0.2, 0.3, 0.5), W)] +
    [('orb', a) for a in itertools.product((15, 30), W, ('or', 0.2, 0.3), ('lvl1', 'lvl2', '2R', 'close'), (720, 840))] +
    [('cprbreak', a) for a in itertools.product(W, ('cpr', 0.15, 0.3), ('lvl1', '2R', 'close'), (720, 840))] +
    [('reject', a) for a in itertools.product((1, 2), W, ('candle', 0.2), ('pivot', 'cpr', '2R'))] +
    [('bias', a) for a in itertools.product(('fade', 'follow'), (0.3, 0.5, 1.0), W)])
FN = dict(magnet=magnet, orb=orb, cprbreak=cprbreak, reject=reject, bias=bias)

def run(fam, args, ds): return [t for d in ds for t in FN[fam](d, *args)]

L60, P30 = TEST[-60:], TEST[-90:-60]
def summ(ts, ds):
    s = set(ds); p = [t[1] for t in ts if t[0] in s]
    return len(p), sum(p), (100 * sum(v > 0 for v in p) / len(p) if p else 0)

if __name__ == '__main__':
    res = []
    for fam, args in VARIANTS:
        ts = run(fam, args, TEST)
        yrs = collections.defaultdict(float)
        for t in ts: yrs[t[0][:4]] += t[1]
        daily = collections.defaultdict(float)
        for t in ts: daily[t[0]] += t[1]
        res.append(dict(fam=fam, args=args, l60=summ(ts, L60), p30=summ(ts, P30), l90=summ(ts, L60 + P30), all=summ(ts, TEST), yrs=dict(yrs),
                        daily=daily, n=len(ts)))
    json.dump(res, open(f'../.cache/cpr_{name}.json', 'w'))
    fmt = lambda s: f"{s[0]:4} tr {s[1]:+8,.0f} ({s[2]:.0f}% won)"
    print(f"{name.upper()}: {len(VARIANTS)} versions; last 60 sessions {L60[0]} to {L60[-1]}, 30 before {P30[0]} to {P30[-1]}, all {TEST[0]} to {TEST[-1]}")
    for fam in FN:
        rs = [r for r in res if r['fam'] == fam]
        print(f"\n{fam}: {len(rs)} versions; made money in last 60: {sum(r['l60'][1] > 0 for r in rs)}, also in the 30 before: "
              f"{sum(r['l60'][1] > 0 and r['p30'][1] > 0 for r in rs)}, also since 2023: {sum(r['l60'][1] > 0 and r['p30'][1] > 0 and r['all'][1] > 0 for r in rs)}, "
              f"every year 2023-2026: {sum(all(r['yrs'].get(y, 0) > 0 for y in ('2023', '2024', '2025', '2026')) for r in rs)}")
    print("\nBEST 15 IN THE LAST 60 SESSIONS (at least 10 trades):")
    for r in sorted([r for r in res if r['l60'][0] >= 10], key=lambda r: -r['l60'][1])[:15]:
        print(f" {r['fam']:8} {str(r['args']):42} last60 {fmt(r['l60'])} | 30 before {fmt(r['p30'])} | since 2023 {fmt(r['all'])} | "
              + ' '.join(f"{y}:{v:+,.0f}" for y, v in sorted(r['yrs'].items())))
    print("\nPOSITIVE IN THE LAST 60, THE 30 BEFORE, AND EVERY YEAR 2023-2026:")
    for r in sorted([r for r in res if r['l60'][1] > 0 and r['p30'][1] > 0 and all(r['yrs'].get(y, 0) > 0 for y in ('2023', '2024', '2025', '2026'))], key=lambda r: -r['all'][1])[:15]:
        print(f" {r['fam']:8} {str(r['args']):42} last60 {fmt(r['l60'])} | 30 before {fmt(r['p30'])} | since 2023 {fmt(r['all'])} | "
              + ' '.join(f"{y}:{v:+,.0f}" for y, v in sorted(r['yrs'].items())))

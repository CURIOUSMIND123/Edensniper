"""Conditions that lift the win rate to 70%+ with a small target and a stop no bigger than 1.5x the target (asked on
15 October 2026). Chosen on 2023-2025, checked on 2026.

    python highwin2.py nifty        (or sensex)

Entries: the alert program's calls (ours), the A+ setup (5-minute, 2-candle swings, wick sweep; and 5-minute,
1-candle swings, sweep back within 2 candles), entered at the middle of the fair value gap.
Exits: target T (Nifty 30 / 40 / 50, Sensex 100 / 150 / 200) or stop S = 0.75 / 1 / 1.5 x T, out by 3:15;
pessimistic fills (a candle reaching both counts as the stop); costs 4 / 12 points.
Conditions (each with its values), one or two at a time:
  gap      the day opened above / below yesterday's close, with the trade (with) or against it
  pivot    the entry above the pivot for a BUY / below for a SELL (with) or not
  range    after 9:30: the entry beyond the 15-minute high for a BUY / low for a SELL (beyond), inside, or the other side
  mom30    the last 30 minutes moved with the trade (with) or against it
  time     before 10:30 / 10:30-12:30 / after 12:30
  room     the next price level ahead is at least 1x / 1.5x the target away (or none ahead)
  vol      the last 10 days' average daily range as % of price: low / middle / high third (thirds of 2023-2025)
  cpr      narrow CPR day or not
Qualifies: won >= 70% and made money in each of 2023, 2024, 2025, with at least 15 trades a year.
"""
import collections, itertools, json, sys
import numpy as np
import levels_style as LS
import aplus_setup as AP
import highwin as HW

A = LS.A
NM, COST = LS.NM, LS.COST
DAYS = LS.DAYS
TGTS = HW.TGTS
SMULT = (0.75, 1.0, 1.5)

# daily range regime
rng = {}
for i, d in enumerate(LS.Y.days):
    o, h, l, c = LS.Y.DAY[d][:4]
    rng[d] = (h - l) / c
atr10 = {}
for i, d in enumerate(LS.Y.days):
    prev = LS.Y.days[max(0, i - 10):i]
    if len(prev) == 10:
        atr10[d] = sum(rng[x] for x in prev) / 10
train_v = sorted(atr10[d] for d in DAYS if d < '2026' and d in atr10)
cut1, cut2 = train_v[len(train_v) // 3], train_v[2 * len(train_v) // 3]

def entries():
    """[(day, kind, minute the trade starts, side, entry price, limit?)] with fills done for limit orders."""
    out = []
    g = {'ours': HW.gen_ours(), 'A+ 5m piv2 wick': HW.gen_ap(5, 2, 'wick'), 'A+ 5m piv1 2bar': HW.gen_ap(5, 1, '2bar')}
    for kind, sig in g.items():
        for d in DAYS:
            c1 = LS.sess[d]
            for s in sig.get(d, []):
                if s['m'] > 870:
                    continue
                if s['limit']:
                    fill = None
                    for m, o, h, l, c in c1:
                        if m < s['m']:
                            continue
                        if m > min(s['m'] + 59, 870):
                            break
                        if (l <= s['px']) if s['side'] > 0 else (h >= s['px']):
                            fill = (m, min(o, s['px']) if s['side'] > 0 else max(o, s['px'])); break
                    if not fill:
                        continue
                    out.append((d, kind, fill[0], s['side'], fill[1], True))
                else:
                    out.append((d, kind, s['m'], s['side'], s['px'], False))
    return out

def features(d, m, side, e):
    c1 = LS.sess[d]; cx = LS.CX[d]
    before = [x for x in c1 if x[0] < m]
    f = {}
    f['gap'] = 'with' if side * (c1[0][1] - cx['yc']) > 0 else 'against'
    f['pivot'] = 'with' if side * (e - cx['lv']['p']) > 0 else 'against'
    first = [x for x in c1 if x[0] < A.RANGE_END]
    hi, lo = max(x[2] for x in first), min(x[3] for x in first)
    if m < A.RANGE_END:
        f['range'] = 'before 9:30'
    else:
        beyond = (e > hi) if side > 0 else (e < lo)
        other = (e < lo) if side > 0 else (e > hi)
        f['range'] = 'beyond' if beyond else 'other side' if other else 'inside'
    past = [x for x in before if x[0] >= m - 30]
    f['mom30'] = 'with' if past and side * (past[-1][4] - past[0][1]) > 0 else 'against'
    f['time'] = 'before 10:30' if m < 630 else '10:30-12:30' if m < 750 else 'after 12:30'
    L = LS.day_levels(cx, c1)
    ahead = [side * (x - e) for x in L.values() if side * (x - e) > 0.0003 * e]
    f['room'] = min(ahead) if ahead else 1e9
    v = atr10.get(d)
    f['vol'] = 'low' if v is not None and v < cut1 else 'high' if v is not None and v >= cut2 else 'middle'
    f['cpr'] = 'narrow' if cx['narrow'] else 'not narrow'
    return f

def outcome(d, start, side, e, T, S, limit):
    c1 = LS.sess[d]
    stp, tg = e - side * S, e + side * T
    for m, o, h, l, c in c1:
        if m < start:
            continue
        adv, fav = (l, h) if side > 0 else (h, l)
        if side * (adv - stp) <= 0:
            return -S - COST
        if limit and m == start:
            continue
        if side * (fav - tg) >= 0:
            return T - COST
        if m >= LS.OUT:
            return side * (c - e) - COST
    return side * (c1[-1][4] - e) - COST

if __name__ == '__main__':
    E = entries()
    rows = []
    for d, kind, m, side, e, limit in E:
        f = features(d, m, side, e)
        res = {(T, s): outcome(d, m if limit else m, side, e, T, s * T, limit) for T in TGTS for s in SMULT}
        rows.append(dict(d=d, kind=kind, f=f, res=res))
    print(f"{NM.upper()}: {len(rows)} entries ({collections.Counter(r['kind'] for r in rows)}); 10-day range thirds "
          f"{cut1 * 100:.2f}% / {cut2 * 100:.2f}%")
    conds = {'gap': ('with', 'against'), 'pivot': ('with', 'against'), 'range': ('beyond', 'inside', 'other side', 'before 9:30'),
             'mom30': ('with', 'against'), 'time': ('before 10:30', '10:30-12:30', 'after 12:30'),
             'vol': ('low', 'middle', 'high'), 'cpr': ('narrow', 'not narrow')}
    single = [(k, v) for k, vs in conds.items() for v in vs]
    filters = [()] + [(a,) for a in single] + [(a, b) for a, b in itertools.combinations(single, 2) if a[0] != b[0]]
    print(f"  {len(filters)} conditions x 3 entry kinds x {len(TGTS)} targets x {len(SMULT)} stops x 3 room rules")
    found, tested, best = [], 0, []
    for kind in ('ours', 'A+ 5m piv2 wick', 'A+ 5m piv1 2bar'):
        R0 = [r for r in rows if r['kind'] == kind]
        for room in (0, 1.0, 1.5):
            for flt in filters:
                sel = [r for r in R0 if all(r['f'][k] == v for k, v in flt)]
                for T in TGTS:
                    sel2 = [r for r in sel if r['f']['room'] >= room * T]
                    if len(sel2) < 45:
                        continue
                    for s in SMULT:
                        tested += 1
                        by = collections.defaultdict(list)
                        for r in sel2:
                            by[r['d'][:4]].append(r['res'][(T, s)])
                        ok = all(len(by[y]) >= 15 and sum(x > 0 for x in by[y]) >= 0.7 * len(by[y]) and sum(by[y]) > 0
                                 for y in ('2023', '2024', '2025'))
                        wins = [100 * sum(x > 0 for x in by[y]) / max(1, len(by[y])) for y in LS.YEARS]
                        key = (kind, room, flt, T, s)
                        best.append((min(wins[:3]) if all(len(by[y]) >= 15 for y in ('2023', '2024', '2025')) else 0, key, by))
                        if ok:
                            found.append((key, by))
    print(f"  {tested} tested; won >= 70% and made money in each of 2023, 2024, 2025: {len(found)}")
    def show(key, by):
        kind, room, flt, T, s = key
        txt = ', '.join(f'{k} {v}' for k, v in flt) or 'no condition'
        ys = ' | '.join(f"{y} {len(by[y]):3} tr {100 * sum(x > 0 for x in by[y]) / max(1, len(by[y])):3.0f}% {sum(by[y]):+6.0f}" for y in LS.YEARS)
        print(f"    {kind:16} T{T} S{s * T:.0f} room>={room}T | {txt:42} {ys}")
    for key, by in sorted(found, key=lambda kb: -sum(sum(kb[1][y]) for y in ('2023', '2024', '2025')))[:25]:
        show(key, by)
    print("  the highest lowest-year win rate over 2023-2025 (whatever the money):")
    for w, key, by in sorted(best, key=lambda x: -x[0])[:10]:
        show(key, by)
    json.dump([dict(key=str(k), years={y: [len(by[y]), sum(x > 0 for x in by[y]), round(sum(by[y]))] for y in LS.YEARS})
               for k, by in found], open(f'../.cache/highwin2_{NM}.json', 'w'))

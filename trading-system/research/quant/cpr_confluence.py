"""Daily CPR breakouts confirmed by other indicators (asked on 19 October 2026): how often the index then went 60 (Nifty)
/ 200 (Sensex) points the trade's way before 35 / 100 against it, and which indicators raise that chance. 2023-2026;
combinations chosen on 2023-2025, then 2026.

    python cpr_confluence.py nifty        (or sensex)

Breakouts: the first 1-minute touch of the CPR top from below (BUY) / bottom from above (SELL), or the first 5-minute
close beyond it; each once a day, 9:16-2:30. Entry at the touch (or the close), out at the target, the stop or 3:15;
costs 4 / 12 points; a candle reaching both counts as the stop. Every breakout counted on its own (not one at a time).
Indicators at the breakout (5-minute candles, the last one complete):
  ema       the close above EMA 20 and EMA 20 above EMA 50 for a BUY (below for a SELL): with / against / mixed
  st        Supertrend (10, 3) pointing the trade's way: with / against
  rsi       RSI 14: above 55 for a BUY / below 45 for a SELL (strong), 45-55 (neutral), else (weak)
  vol       NIFTYBEES volume of the breakout's 5-minute candle at least 1.5x the last hour's average: surge / normal
  vcheck    over the last 2 hours the up candles carried more volume than the down candles (BUY; SELL the other way)
  poc       the entry beyond yesterday's volume POC the trade's way: with / against
  weekly    the entry beyond the weekly pivot the trade's way: with / against
  range     after 9:30, the entry beyond the 15-minute high (BUY) / low (SELL): beyond / inside / before 9:30
  narrow    narrow CPR day (the narrowest third of the last 20): yes / no
  rel       today's CPR above yesterday's (BUY; below for a SELL): with / overlap / against
  gap       the open above yesterday's close (BUY; below for a SELL): with / against
  opened    where the day opened: beyond the CPR the other way (crossed it) / inside the CPR / beyond it already
  time      before 10:00 / 10:00-11:30 / after 11:30
  trend     yesterday's close above its 20-day average (BUY; below for a SELL): with / against
"""
import collections, itertools
import levels_style as LS
import weekly_cpr as WK

A = LS.A
NM, COST = LS.NM, LS.COST
TP, SL = {'nifty': (60, 35), 'sensex': (200, 100)}[NM]
DAYS = WK.DAYS
BE = 100 * (SL + COST) / (TP + SL)

# ---------------- 5-minute series across all days, with indicators ----------------
bars = []                                 # (day, start minute, o, h, l, c, volume)
for d in LS.Y.days:
    c1 = LS.sess.get(d, [])
    if len(c1) < 300:
        continue
    vol = LS.vol.get(d, {})
    blk = collections.OrderedDict()
    for x in c1:
        blk.setdefault(555 + (x[0] - 555) // 5 * 5, []).append(x)
    for s, v in blk.items():
        if len(v) == 5:
            bars.append((d, s, v[0][1], max(x[2] for x in v), min(x[3] for x in v), v[-1][4], sum(vol.get(x[0], 0) for x in v)))
IDX = {(b[0], b[1]): i for i, b in enumerate(bars)}
n = len(bars)
C = [b[5] for b in bars]

def ema(xs, k):
    out, a, e = [], 2 / (k + 1), None
    for x in xs:
        e = x if e is None else e + a * (x - e)
        out.append(e)
    return out
E20, E50 = ema(C, 20), ema(C, 50)
RSI = [50.0] * n
ag = al = 0.0
for i in range(1, n):
    ch = C[i] - C[i - 1]
    g, l_ = max(ch, 0), max(-ch, 0)
    if i <= 14:
        ag += g / 14; al += l_ / 14
    else:
        ag = (ag * 13 + g) / 14; al = (al * 13 + l_) / 14
    RSI[i] = 100 - 100 / (1 + ag / al) if al > 0 else 100.0
ST = [1] * n                              # Supertrend (10, 3) direction
atr, up_b, dn_b = None, None, None
for i in range(n):
    h, l_, c = bars[i][3], bars[i][4], bars[i][5]
    tr = h - l_ if i == 0 else max(h - l_, abs(h - C[i - 1]), abs(l_ - C[i - 1]))
    atr = tr if atr is None else (atr * 9 + tr) / 10
    mid = (h + l_) / 2
    ub, lb = mid + 3 * atr, mid - 3 * atr
    if i > 0:
        ub = ub if ub < up_b or C[i - 1] > up_b else up_b
        lb = lb if lb > dn_b or C[i - 1] < dn_b else dn_b
        ST[i] = 1 if c > up_b else -1 if c < dn_b else ST[i - 1]
    up_b, dn_b = ub, lb
closes = {d: LS.Y.DAY[d][3] for d in LS.Y.days}
dl = list(LS.Y.days)
SMA20 = {}
for i, d in enumerate(dl):
    if i >= 20:
        SMA20[d] = sum(closes[x] for x in dl[i - 20:i]) / 20

def last_bar(d, m):
    """Index of the last complete 5-minute candle before minute m (the day's or earlier)."""
    s = 555 + (m - 555) // 5 * 5 - 5
    while s >= 555:
        if (d, s) in IDX:
            return IDX[(d, s)]
        s -= 5
    j = next((i for i, b in enumerate(bars) if b[0] == d), None)
    return j - 1 if j else None

def features(d, m, side, e, j):
    cx, c1 = LS.cx_for(d) if hasattr(LS, 'cx_for') else LS.CX[d], LS.sess[d]
    f = {}
    f['ema'] = 'with' if side * (C[j] - E20[j]) > 0 and side * (E20[j] - E50[j]) > 0 else \
        'against' if side * (C[j] - E20[j]) < 0 and side * (E20[j] - E50[j]) < 0 else 'mixed'
    f['st'] = 'with' if ST[j] == side else 'against'
    r = RSI[j] if side > 0 else 100 - RSI[j]
    f['rsi'] = 'strong' if r > 55 else 'neutral' if r >= 45 else 'weak'
    past = [bars[k][6] for k in range(max(0, j - 12), j)]
    f['vol'] = 'surge' if past and bars[j][6] >= 1.5 * sum(past) / len(past) else 'normal'
    upv = sum(bars[k][6] for k in range(max(0, j - 23), j + 1) if bars[k][5] > bars[k][2])
    dnv = sum(bars[k][6] for k in range(max(0, j - 23), j + 1) if bars[k][5] < bars[k][2])
    f['vcheck'] = 'with' if side * (upv - dnv) > 0 else 'against'
    poc = cx.get('poc1')
    f['poc'] = 'none' if poc is None else 'with' if side * (e - poc) > 0 else 'against'
    f['weekly'] = 'with' if side * (e - WK.WEEK[d]['wP']) > 0 else 'against'
    if m < A.RANGE_END:
        f['range'] = 'before 9:30'
    else:
        first = [x for x in c1 if x[0] < A.RANGE_END]
        hi, lo = max(x[2] for x in first), min(x[3] for x in first)
        f['range'] = 'beyond' if ((e > hi) if side > 0 else (e < lo)) else 'inside'
    f['narrow'] = 'yes' if cx['narrow'] else 'no'
    f['rel'] = 'with' if cx['rel'] == side else 'overlap' if cx['rel'] == 0 else 'against'
    o = c1[0][1]
    f['gap'] = 'with' if side * (o - cx['yc']) > 0 else 'against'
    top, bot = cx['lv']['top'], cx['lv']['bot']
    far, near = (bot, top) if side > 0 else (top, bot)
    f['opened'] = 'crossed it' if side * (o - far) < 0 else 'inside' if side * (o - near) <= 0 else 'beyond already'
    f['time'] = 'before 10:00' if m < 600 else '10:00-11:30' if m < 690 else 'after 11:30'
    sma = SMA20.get(d)
    f['trend'] = 'with' if sma is not None and side * (cx['yc'] - sma) > 0 else 'against'
    return f

def events(kind):
    out = []
    for d in DAYS:
        c1, lv = LS.sess[d], LS.CX[d]['lv']
        top, bot = lv['top'], lv['bot']
        done = set()
        if kind == 'touch':
            for i in range(1, len(c1)):
                m, o, h, l, c = c1[i]
                if m < 556 or m > 870:
                    continue
                pc = c1[i - 1][4]
                if 1 not in done and pc < top <= h:
                    done.add(1); out.append((d, m, 1, max(o, top), m + 1))
                if -1 not in done and pc > bot >= l:
                    done.add(-1); out.append((d, m, -1, min(o, bot), m + 1))
        else:
            B = WK.blocks5(c1)
            for i in range(1, len(B)):
                st, o, h, l, c = B[i]
                if st + 4 > 870:
                    continue
                pc = B[i - 1][4]
                side = 1 if pc <= top < c else -1 if pc >= bot > c else 0
                if side and side not in done:
                    done.add(side); out.append((d, st + 4, side, c, st + 5))
    rows = []
    for d, m, side, e, start in out:
        j = IDX.get((d, m - 4)) if (m - 555) % 5 == 4 and (d, m - 4) in IDX else last_bar(d, m)
        if j is None or j < 60:
            continue
        p, x, k = LS.walk(LS.sess[d], side, e, start, e - side * SL, (e + side * TP,), (1,))
        rows.append(dict(d=d, y=d[:4], side=side, hit=k == 1, pnl=p, f=features(d, m, side, e, j)))
    return rows

CHECK = [(('rel', 'overlap'),), (('rel', 'overlap'), ('rsi', 'strong')), (('rel', 'overlap'), ('st', 'with')),
         (('rel', 'overlap'), ('narrow', 'no')), (('rsi', 'strong'), ('opened', 'beyond already')),
         (('ema', 'with'), ('range', 'before 9:30')), (('time', '10:00-11:30'),), (('range', 'inside'),)]

def summ(rs):
    by = collections.defaultdict(list)
    for r in rs:
        by[r['y']].append(r)
    return {y: (len(by[y]), 100 * sum(r['hit'] for r in by[y]) / len(by[y]) if by[y] else 0, sum(r['pnl'] for r in by[y]))
            for y in LS.YEARS}

def line(label, s, w=44):
    print(f"  {label:{w}} " + ' | '.join(f"{y} {s[y][0]:3} tr {s[y][1]:3.0f}% {s[y][2]:+6.0f}" for y in LS.YEARS))

if __name__ == '__main__':
    print(f"{NM.upper()}: daily CPR breakouts, target {TP} before stop {SL}; costs {COST:g} (break-even: target first on "
          f"{BE:.0f}%); per year: breakouts, target first %, net points")
    for kind in ('touch', '5m'):
        R = events(kind)
        print(f"\n{'FIRST TOUCH' if kind == 'touch' else '5-MINUTE CLOSE'} OF THE CPR TOP / BOTTOM: {len(R)} breakouts")
        line('all breakouts', summ(R))
        conds = collections.OrderedDict()
        for r in R:
            for k, v in r['f'].items():
                conds.setdefault(k, set()).add(v)
        print("  one indicator at a time:")
        for k, vs in conds.items():
            for v in sorted(vs):
                rs = [r for r in R if r['f'][k] == v]
                if len(rs) >= 40:
                    line(f"{k} {v}", summ(rs))
        single = [(k, v) for k, vs in conds.items() for v in vs]
        res = []
        for a, b in itertools.combinations(single, 2):
            if a[0] == b[0]:
                continue
            rs = [r for r in R if r['f'][a[0]] == a[1] and r['f'][b[0]] == b[1]]
            s = summ(rs)
            if all(s[y][0] >= 12 for y in ('2023', '2024', '2025')):
                res.append((f"{a[0]} {a[1]} + {b[0]} {b[1]}", s))
        for k, vs in conds.items():
            for v in vs:
                s = summ([r for r in R if r['f'][k] == v])
                if all(s[y][0] >= 12 for y in ('2023', '2024', '2025')):
                    res.append((f"{k} {v}", s))
        good = [x for x in res if all(x[1][y][1] >= BE + 5 and x[1][y][2] > 0 for y in ('2023', '2024', '2025'))]
        print(f"  {len(res)} combinations with 12+ breakouts a year; target first at least {BE + 5:.0f}% and money made in each "
              f"of 2023, 2024, 2025: {len(good)}")
        for lab, s in sorted(good, key=lambda x: -min(x[1][y][1] for y in ('2023', '2024', '2025')))[:12]:
            line(lab, s)
        print("  the highest lowest-year chance over 2023-2025 (whatever the money):")
        for lab, s in sorted(res, key=lambda x: -min(x[1][y][1] for y in ('2023', '2024', '2025')))[:8]:
            line(lab, s)
        print("  the same filters on both indices (the best of each index, checked on the other):")
        for fs in CHECK:
            line(' + '.join(f"{k} {v}" for k, v in fs), summ([r for r in R if all(r['f'][k] == v for k, v in fs)]))

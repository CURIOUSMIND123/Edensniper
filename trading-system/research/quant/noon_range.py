"""The morning range to 12:00 and what the afternoon does with it (asked on 28 October 2026, a strategy heard of: by
12:00 mark the day's high and low; price near the high takes the liquidity above it and goes back to the low, and the
other way). 2026 (and 2023-2025 for the trade, as a check), 1-minute candles.

    python noon_range.py nifty        (or sensex)

Morning range = 9:15-11:59 high / low (MH / ML). Where price is at 12:00: near the high (top 30% of the range),
middle, near the low (bottom 30%). After 12:00 (to 15:29): which side broke first, how far beyond it went, whether
price then came back inside (a 1-minute close back in), to the range's middle, to the other side.
The trade: 12:00-14:30, the first 5-minute candle that went above MH and closed back below it -> SELL at its close
(below ML and closed back above -> BUY); stop just beyond the highest (lowest) price since 12:00 (0.02%), at most
55 / 170 points; out at the middle of the range, the other side of it, 2x the stop or held to 3:15. Costs 4 / 12; a
candle reaching both the stop and the target counts as the stop.
"""
import collections, datetime as dt, json, os, statistics as st, sys
sys.path.insert(0, '../../alerts')
import cprb_alerts as A

NM = sys.argv[1] if len(sys.argv) > 1 else 'nifty'
SPEC = A.SPEC[NM]
COST, CAP = SPEC['cost'], A.STOP_MAX[NM]
NOON, LAST = 720, 870

def sessions():
    raw = json.load(open(f'../.cache/{NM}_1m.json'))
    out = collections.defaultdict(list)
    for k in sorted(raw):
        out[k[:10]].append((int(k[11:13]) * 60 + int(k[14:16]),) + tuple(raw[k][:4]))
    last = dt.date.fromisoformat(max(out))
    p = f'../.cache/noon_{NM}_tail.json'
    if os.path.exists(p):
        tail = json.load(open(p))
    else:
        tail = {d: {str(m): v for m, v in mm.items()} for d, mm in
                A.fetch_range(SPEC['key'], last + dt.timedelta(days=1), dt.date(2026, 10, 27)).items()}
        json.dump(tail, open(p, 'w'))
    for d, mm in tail.items():
        out[d] = [(int(m),) + tuple(v[:4]) for m, v in sorted(mm.items(), key=lambda kv: int(kv[0]))]
    return {d: v for d, v in out.items() if len(v) >= 300}

S = sessions()

def day_study(c1):
    am = [x for x in c1 if x[0] < NOON]
    pm = [x for x in c1 if x[0] >= NOON]
    if not am or not pm:
        return None
    mh, ml = max(x[2] for x in am), min(x[3] for x in am)
    R, p12 = mh - ml, am[-1][4]
    pos = (p12 - ml) / R if R else 0.5
    up = next((i for i, x in enumerate(pm) if x[2] > mh), None)
    dn = next((i for i, x in enumerate(pm) if x[3] < ml), None)
    first = None if up is None and dn is None else 'high' if dn is None or (up is not None and up < dn) else 'low'
    r = dict(R=R, pos=pos, first=first, p12=p12, mh=mh, ml=ml)
    if first:
        s = 1 if first == 'high' else -1                  # the side swept
        i0 = up if s > 0 else dn
        lvl, other, mid = (mh, ml, (mh + ml) / 2) if s > 0 else (ml, mh, (mh + ml) / 2)
        back = next((j for j in range(i0 + 1, len(pm)) if s * (pm[j][4] - lvl) < 0), None)   # a close back inside
        seg = pm[i0:back + 1] if back is not None else pm[i0:]
        peak = max(x[2] for x in seg) if s > 0 else min(x[3] for x in seg)
        r.update(beyond=s * (peak - lvl), back=back is not None)
        if back is not None:
            rest = pm[back:]
            far = min(x[3] for x in rest) if s > 0 else max(x[2] for x in rest)
            r.update(fall=s * (peak - far), past_lvl=s * (lvl - far), mid=s * (far - mid) <= 0, other=s * (far - other) <= 0,
                     t_back=pm[back][0] - pm[i0][0])
        r.update(held=s * (pm[-1][4] - lvl) > 0)
    return r

def pct(n, d):
    return f"{round(100 * n / d):3}%" if d else '  - '

def avg(v):
    return f"{st.mean(v):6.0f} (median {st.median(v):5.0f})" if v else '     -'

def study(days):
    rows = [(d, day_study(S[d])) for d in days]
    rows = [(d, r) for d, r in rows if r]
    print(f"\n{NM.upper()} 2026: {len(rows)} sessions. Morning range (9:15-12:00) on average {st.mean(r['R'] for d, r in rows):.0f} "
          f"points (median {st.median(r['R'] for d, r in rows):.0f}).")
    for where, f in (('anywhere', lambda p: True), ('near the high at 12:00 (top 30%)', lambda p: p >= 0.7),
                     ('in the middle at 12:00', lambda p: 0.3 < p < 0.7), ('near the low at 12:00 (bottom 30%)', lambda p: p <= 0.3)):
        g = [r for d, r in rows if f(r['pos'])]
        if not g:
            continue
        print(f"\n  Price {where}: {len(g)} days")
        print(f"    stayed inside the morning range all afternoon: {pct(sum(r['first'] is None for r in g), len(g))}")
        for side, word, other in (('high', 'above the morning high', 'low'), ('low', 'below the morning low', 'high')):
            s = [r for r in g if r['first'] == side]
            b = [r for r in s if r['back']]
            print(f"    went {word} first: {len(s):3} days ({pct(len(s), len(g))}); how far beyond: {avg([r['beyond'] for r in s])}")
            if s:
                print(f"      came back inside (a 1-minute close): {pct(len(b), len(s))}, after {avg([r['t_back'] for r in b])} minutes")
                print(f"      then reached the middle of the range: {pct(sum(r['mid'] for r in b), len(s))}; the morning {other}: "
                      f"{pct(sum(r['other'] for r in b), len(s))}; the move from the sweep's extreme: {avg([r['fall'] for r in b])} points")
                print(f"      closed the day beyond it (the break held): {pct(sum(r['held'] for r in s), len(s))}")

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

def trades(d, how, near):
    c1 = S[d]
    am = [x for x in c1 if x[0] < NOON]
    mh, ml = max(x[2] for x in am), min(x[3] for x in am)
    pos = (am[-1][4] - ml) / (mh - ml) if mh > ml else 0.5
    out, done = [], set()
    hi, lo = mh, ml
    for k in range((LAST - NOON) // 5):
        m0 = NOON + 5 * k
        b = [x for x in c1 if m0 <= x[0] < m0 + 5]
        if len(b) < 5:
            continue
        h, l, c = max(x[2] for x in b), min(x[3] for x in b), b[-1][4]
        hi, lo = max(hi, h), min(lo, l)
        for s in (-1, 1):                                  # -1: swept the high -> SELL; +1: swept the low -> BUY
            if s in done or (near and not ((s < 0 and pos >= 0.7) or (s > 0 and pos <= 0.3))):
                continue
            if (s < 0 and h > mh and c < mh) or (s > 0 and l < ml and c > ml):
                done.add(s)
                ext = hi if s < 0 else lo
                stp = ext - s * 0.0002 * ext
                risk = s * (c - stp)
                if risk <= 0:
                    continue
                if risk > CAP:
                    stp, risk = c - s * CAP, CAP
                tgt = {'middle': (mh + ml) / 2, 'other side': ml if s < 0 else mh, '2x': c + s * 2 * risk, '3:15': None}[how]
                if tgt is not None and s * (tgt - c) <= 0:
                    continue
                out.append((d, walk(c1, s, c, m0 + 5, stp, tgt)))
    return out

def trade_table():
    print(f"\n{NM.upper()}: THE TRADE (sweep of the morning high -> SELL, of the low -> BUY), trades, won %, net points")
    for near in (False, True):
        for how in ('middle', 'other side', '2x', '3:15'):
            r26 = [x for d in S if d >= '2026-01-01' for x in trades(d, how, near)]
            r_old = [x for d in S if d < '2026-01-01' for x in trades(d, how, near)]
            line = []
            for nm, rows in (('2026', r26), ('2023-2025', r_old)):
                p = [x for _, x in rows]
                line.append(f"{nm} {len(p):4} tr {pct(sum(x > 0 for x in p), len(p))} {sum(p):+7.0f}")
            mon = collections.defaultdict(float)
            for d, x in r26:
                mon[d[:7]] += x
            print(f"  {'only from near that side at 12:00, ' if near else ''}out at {how:10}  " + ' | '.join(line) +
                  f" | 2026 months +: {sum(v > 0 for v in mon.values())} of {len(mon)}")

TGT = {'nifty': 75, 'sensex': 200}[NM]

def exact(d, stop, near):
    """The user's version (29 October 2026): after 12:00, at the first 1-minute close back inside the morning range
    after a poke beyond it -> the other way at that close; target TGT points; stop beyond the poke ('poke', +0.02%, at
    most CAP) or a fixed number of points; held at most to 3:15. -> list of (day, result, 'target' / 'stop' / '3:15')."""
    c1 = S[d]
    am, pm = [x for x in c1 if x[0] < NOON], [x for x in c1 if NOON <= x[0] <= LAST]
    mh, ml = max(x[2] for x in am), min(x[3] for x in am)
    pos = (am[-1][4] - ml) / (mh - ml) if mh > ml else 0.5
    out = []
    for s_, lvl in ((-1, mh), (1, ml)):                  # -1: poke above the high -> SELL; +1: below the low -> BUY
        if near and not ((s_ < 0 and pos >= 0.7) or (s_ > 0 and pos <= 0.3)):
            continue
        i0 = next((i for i, x in enumerate(pm) if (x[2] > lvl if s_ < 0 else x[3] < lvl)), None)   # the poke beyond
        if i0 is None:
            continue
        j = next((j for j in range(i0, len(pm)) if s_ * (pm[j][4] - lvl) > 0), None)   # the close back inside
        if j is None:
            continue
        e = pm[j][4]
        ext = max(x[2] for x in pm[i0:j + 1]) if s_ < 0 else min(x[3] for x in pm[i0:j + 1])
        stp = (ext - s_ * 0.0002 * ext) if stop == 'poke' else e - s_ * stop
        if stop == 'poke' and s_ * (e - stp) > CAP:
            stp = e - s_ * CAP
        tgt, res = e + s_ * TGT, None
        for m, o, h, l, c in c1:
            if m <= pm[j][0]:
                continue
            adv, fav = (l, h) if s_ > 0 else (h, l)
            if s_ * (adv - stp) <= 0:
                res = (s_ * (stp - e) - COST, 'stop'); break
            if s_ * (fav - tgt) >= 0:
                res = (TGT - COST, 'target'); break
            if m >= A.OUT:
                res = (s_ * (c - e) - COST, '3:15'); break
        if res:
            out.append((d, s_, e - stp if s_ > 0 else stp - e) + res)
    return out

def exact_table():
    print(f"\n{NM.upper()}: SELL at the first 1-minute close back below the morning high after 12:00 (BUY back above the low),"
          f" target {TGT} points")
    for near in (False, True):
        for stop in ('poke', {'nifty': 35, 'sensex': 100}[NM], CAP):
            for nm, f in (('2026', lambda d: d >= '2026-01-01'), ('2023-2025', lambda d: d < '2026-01-01')):
                r = [x for d in S if f(d) for x in exact(d, stop, near)]
                n = len(r)
                k = collections.Counter(x[4] for x in r)
                net = sum(x[3] for x in r)
                print(f"  {'near that side at 12:00, ' if near else ''}stop {'beyond the poke' if stop == 'poke' else str(stop) + ' points':16}"
                      f" {nm:9} {n:4} trades: target first {k['target']:3} ({pct(k['target'], n)}), stop first {k['stop']:3} "
                      f"({pct(k['stop'], n)}), neither by 3:15 {k['3:15']:3}; net {net:+7.0f} points"
                      + (f"; average stop {st.mean(x[2] for x in r):.0f} points" if stop == 'poke' and r else ''))

if __name__ == '__main__':
    study([d for d in sorted(S) if d >= '2026-01-01'])
    trade_table()
    exact_table()

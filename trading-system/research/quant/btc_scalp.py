"""BTCUSDT perpetual (Binance) scalping, July - October 2026 (asked on 31 October 2026: trap / liquidity / volume patterns
for 400-500 point targets with a 150-point stop, hoping for 80% winners). Binance's public 1-minute archives
(data.binance.vision, futures UM), with the real taker-buy volume (aggressive buyers) in every candle.

    python -I btc_scalp.py ../.cache/btc_raw
    python -I btc_scalp.py ../.cache/btc_long     January 2024 - October 2026 (btc_data.py fetches it): chosen on
                                                  2024-2025, checked on 2026; targets and stops scaled with the price
                                                  (points at $70,000, as btc_data.py explains)

Patterns are chosen on July-September and checked on October. A trade: entry at the signal candle's close, out at the
target or the stop (a candle reaching both counts as the stop), or after 24 hours at the close; one at a time per
pattern; costs 0.06% of the price a trade (taker fee in and maker out, about $45-50 a BTC). Points = US dollars per BTC.

Patterns (UTC times; a "sweep" = price goes beyond a level and a 5-minute candle closes back inside within an hour):
  PDH / PDL        yesterday's (UTC day's) high / low swept -> the other way
  ASIA             the 00:00-08:00 range swept between 08:00 and 20:00 -> the other way
  SWING 4H / 24H   the highest high / lowest low of the last 4 / 24 hours swept -> the other way
  ROUND            a $1,000 level swept -> the other way
  SPIKE            a 5-minute candle with volume >= 3x the day's median, a new 4-hour high (low) and its upper (lower)
                   wick >= 60% of its range -> the other way
  ABSORB           a 5-minute candle at a new 4-hour high with taker buys >= 60% of its volume but closing in its
                   lower half (buyers trapped) -> SELL; the mirror -> BUY
  BREAKOUT         a 15-minute close beyond the last 24 hours' high (low) with volume >= 2x and taker buys >= 55% (<=
                   45%) -> that way
  ORB LDN / NY     the first 15 minutes after 08:00 / 13:30 UTC; the first 5-minute close beyond it -> that way
"""
import collections, csv, datetime as dt, io, os, statistics as st, sys, zipfile

SRC = sys.argv[1] if len(sys.argv) > 1 else '../.cache/btc_raw'
COST = 0.0006
LONG = os.path.basename(os.path.normpath(SRC)) == 'btc_long'
if LONG:
    SEL_END, START = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc), dt.datetime(2024, 2, 1, tzinfo=dt.timezone.utc)
    SEL_NAME, CHK_NAME = '2024-25', '2026'
else:
    SEL_END, START = dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc), dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    SEL_NAME, CHK_NAME = 'Jul-Sep', 'Oct'
REF = 70000.0
def U(e):
    """Price units per point: 1 (plain points), or e / $70,000 in the long test."""
    return e / REF if LONG else 1.0

def load():
    rows = {}
    for fn in sorted(os.listdir(SRC)):
        if not fn.endswith('.zip') or not zipfile.is_zipfile(os.path.join(SRC, fn)):
            continue                                  # a day not published yet (the archive answers 404)
        with zipfile.ZipFile(os.path.join(SRC, fn)) as z:
            for name in z.namelist():
                for r in csv.reader(io.TextIOWrapper(z.open(name))):
                    if r and r[0].isdigit():
                        rows[int(r[0]) // 60000] = (float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]), float(r[9]))
    ks = sorted(rows)
    return ks, rows

KS, R = load()
POS = {k: i for i, k in enumerate(KS)}
T = lambda k: dt.datetime.fromtimestamp(k * 60, dt.timezone.utc)

def bars(n):
    """n-minute candles: list of (start minute, o, h, l, c, volume, taker buys)."""
    g = collections.OrderedDict()
    for k in KS:
        g.setdefault(k // n * n, []).append(R[k])
    return [(s, v[0][0], max(x[1] for x in v), min(x[2] for x in v), v[-1][3], sum(x[4] for x in v), sum(x[5] for x in v))
            for s, v in g.items() if len(v) == n]

B5, B15 = bars(5), bars(15)

def outcome(k0, side, e, tp, sl, hours=24):
    """From minute k0 on: 'win' / 'loss' / 'time' and the result in points after costs."""
    i = POS.get(k0)
    if i is None:
        return None
    u = U(e)
    cost = COST * e / u
    stp, tgt = e - side * sl * u, e + side * tp * u
    for k in KS[i:i + hours * 60]:
        o, h, l, c, v, tb = R[k]
        if side * ((l if side > 0 else h) - stp) <= 0:
            return 'loss', -sl - cost
        if side * ((h if side > 0 else l) - tgt) >= 0:
            return 'win', tp - cost
    c = R[KS[min(i + hours * 60, len(KS)) - 1]][3]
    return 'time', side * (c - e) / u - cost

def day_levels():
    """UTC day -> (yesterday's high, low), (the Asia range 00:00-08:00 high, low)."""
    by = collections.defaultdict(list)
    for k in KS:
        by[T(k).date()].append(k)
    days = sorted(by)
    out = {}
    for a, b in zip(days, days[1:]):
        hi, lo = max(R[k][1] for k in by[a]), min(R[k][2] for k in by[a])
        asia = [k for k in by[b] if T(k).hour < 8]
        out[b] = ((hi, lo), (max(R[k][1] for k in asia), min(R[k][2] for k in asia)) if asia else None)
    return out

LV = day_levels()

def sweeps(levels_at, name, start_hour=0, end_hour=24):
    """Signals from a sweep of levels: levels_at(i, bar) -> [(price, side_to_trade)] (side -1: a high, so SELL)."""
    out, armed = [], {}
    for i, (s, o, h, l, c, v, tb) in enumerate(B5):
        t = T(s)
        if not (start_hour <= t.hour < end_hour):
            armed.clear()
            continue
        for p, side in levels_at(i, B5[i]):
            key = (round(p, 1), side)
            if side < 0 and h > p and key not in armed:
                armed[key] = s
            if side > 0 and l < p and key not in armed:
                armed[key] = s
            if key in armed and s - armed[key] <= 60 and ((side < 0 and c < p) or (side > 0 and c > p)) and armed[key] != -1:
                out.append((s + 5, side, c, name))
                armed[key] = -1                          # each level once
    return out

def pdh(i, b):
    lv = LV.get(T(b[0]).date())
    return [(lv[0][0], -1), (lv[0][1], 1)] if lv else []

def asia(i, b):
    lv = LV.get(T(b[0]).date())
    return [(lv[1][0], -1), (lv[1][1], 1)] if lv and lv[1] else []

def swing(nbars):
    def f(i, b):
        if i < nbars:
            return []
        w = B5[i - nbars:i]
        return [(max(x[2] for x in w), -1), (min(x[3] for x in w), 1)]
    return f

def rounds(i, b):
    c = b[4]
    base = int(c // 1000) * 1000
    return [(base + 1000, -1), (base, 1)]

def spike_absorb():
    sp, ab = [], []
    vols = collections.defaultdict(list)
    for s, o, h, l, c, v, tb in B5:
        vols[T(s).date()].append(v)
    med = {d: st.median(x) for d, x in vols.items()}
    for i in range(48, len(B5)):
        s, o, h, l, c, v, tb = B5[i]
        w = B5[i - 48:i]
        hi4, lo4 = max(x[2] for x in w), min(x[3] for x in w)
        rng = h - l
        if rng <= 0:
            continue
        m = med.get((T(s) - dt.timedelta(days=1)).date()) or med[T(s).date()]
        if v >= 3 * m and h > hi4 and (h - max(o, c)) >= 0.6 * rng:
            sp.append((s + 5, -1, c, 'SPIKE'))
        if v >= 3 * m and l < lo4 and (min(o, c) - l) >= 0.6 * rng:
            sp.append((s + 5, 1, c, 'SPIKE'))
        if h > hi4 and v > 0 and tb / v >= 0.6 and c < l + rng / 2:
            ab.append((s + 5, -1, c, 'ABSORB'))
        if l < lo4 and v > 0 and tb / v <= 0.4 and c > l + rng / 2:
            ab.append((s + 5, 1, c, 'ABSORB'))
    return sp, ab

def breakouts():
    out = []
    for i in range(96, len(B15)):
        s, o, h, l, c, v, tb = B15[i]
        w = B15[i - 96:i]
        hi, lo, av = max(x[2] for x in w), min(x[3] for x in w), st.mean(x[5] for x in w)
        if c > hi and v >= 2 * av and tb / v >= 0.55:
            out.append((s + 15, 1, c, 'BREAKOUT'))
        if c < lo and v >= 2 * av and tb / v <= 0.45:
            out.append((s + 15, -1, c, 'BREAKOUT'))
    return out

def orb(hh, mm, name):
    out, rng, done = [], {}, set()
    for s, o, h, l, c, v, tb in B5:
        t = T(s)
        d, m = t.date(), t.hour * 60 + t.minute
        m0 = hh * 60 + mm
        if m0 <= m < m0 + 15:
            r = rng.get(d)
            rng[d] = (max(r[0], h), min(r[1], l)) if r else (h, l)
        elif m0 + 15 <= m < m0 + 240 and d in rng and d not in done:
            hi, lo = rng[d]
            if c > hi or c < lo:
                out.append((s + 5, 1 if c > hi else -1, c, name))
                done.add(d)
    return out

def run(signals, tp, sl):
    """One trade at a time: -> [(time, result kind, points)]."""
    out, free = [], 0
    for k, side, e, name in sorted(signals):
        if k < free or T(k) < START:
            continue
        r = outcome(k, side, e, tp, sl)
        if r is None:
            continue
        out.append((k, r[0], r[1]))
        i = POS[k]
        # free again when the trade is over: find its exit minute
        stp, tgt = e - side * sl * U(e), e + side * tp * U(e)
        j = i
        for j in range(i, min(i + 24 * 60, len(KS))):
            o, h, l, c, v, tb = R[KS[j]]
            if side * ((l if side > 0 else h) - stp) <= 0 or side * ((h if side > 0 else l) - tgt) >= 0:
                break
        free = KS[j] + 1
    return out

def line(rows):
    sel = [x for x in rows if T(x[0]) < SEL_END]
    chk = [x for x in rows if T(x[0]) >= SEL_END]
    f = lambda r: (f"{len(r):4} tr {round(100 * sum(x[1] == 'win' for x in r) / len(r)) if r else 0:3}% won {sum(x[2] for x in r):+8,.0f}")
    return f"{SEL_NAME} {f(sel)} | {CHK_NAME} {f(chk)}"

if __name__ == '__main__':
    print(f"BTCUSDT perpetual, {T(KS[0]):%Y-%m-%d} - {T(KS[-1]):%Y-%m-%d %H:%M} UTC; trades from {START:%Y-%m-%d}; "
          f"a win = the target before the stop; points = $ per BTC after costs")
    sp, ab = spike_absorb()
    P = {'PDH / PDL': sweeps(pdh, 'PDH / PDL'), 'ASIA range': sweeps(asia, 'ASIA', 8, 20),
         'SWING 4H': sweeps(swing(48), 'SWING 4H'), 'SWING 24H': sweeps(swing(288), 'SWING 24H'), 'ROUND $1,000': sweeps(rounds, 'ROUND'),
         'SPIKE': sp, 'ABSORB': ab, 'BREAKOUT': breakouts(), 'ORB LDN': orb(8, 0, 'ORB LDN'), 'ORB NY': orb(13, 30, 'ORB NY')}
    for tp, sl in ((450, 150), (400, 150), (500, 150), (150, 150), (150, 450)):
        print(f"\n  target {tp} / stop {sl}:")
        for nm, sig in P.items():
            print(f"    {nm:14} " + line(run(sig, tp, sl)))
    # how often any moment reaches +450 before -150 (a coin with no edge): the base rate
    import random
    random.seed(1)
    ks = [k for k in KS if T(k) >= START]
    base = collections.Counter(outcome(k, random.choice((1, -1)), R[k][3], 450, 150)[0] for k in random.sample(ks, 3000))
    print(f"\n  random entries, target 450 / stop 150: {round(100 * base['win'] / sum(base.values()))}% reach the target first")

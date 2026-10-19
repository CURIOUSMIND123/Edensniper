"""The user's rule (19 October 2026): a trade wins when the index goes 60 points (Nifty) / 200 points (Sensex) its way
before a stop of 35 / 100 points. Every entry of the losing families and the daily CPR top / bottom breakouts, taken
as they are and reversed, with that target and stop; out at 3:15 otherwise; one trade at a time per family; costs 4 /
12 points a trade; a 1-minute candle reaching both counts as the stop. 2026 first, then 2023-2025.

    python user_rule.py nifty        (or sensex)

Entries (enter at the signal's price, managed from the next minute, 9:20-2:30):
  key level c1 / c3 / c5   price reaches a key level (P, CPR, R1 / S1, R2 / S2, yesterday's high / low, 15-minute
                           range, volume lines, POC) and the 1-minute candle / 3 one-minute closes / the 5-minute candle
                           close back: the trade back from the level (levels_style.py)
  A+ tf / piv / sweep      sweep -> change of character -> fill in the middle of the fair value gap (aplus_setup.py)
  weekly level             a 5-minute candle reaches a weekly level and closes back (all / near a daily level; any
                           candle / long wick), from 10:00 (weekly_cpr.py)
  weekly CPR break         a 5-minute close through the weekly CPR after 10:00
  rejection + volume       a 5-minute candle with a long wick back from a key level (any volume / 1.5x) (pullback.py)
  CPR break 5m / touch     the daily CPR: a 5-minute close above its top from below -> BUY, below its bottom from above
                           -> SELL (or the first 1-minute touch of the top / bottom from inside or the other side);
                           each once a day
"""
import collections, itertools
import levels_style as LS
import aplus_setup as AP
import weekly_cpr as WK

A = LS.A
NM, COST = LS.NM, LS.COST
TP, SL = {'nifty': (60, 35), 'sensex': (200, 100)}[NM]
DAYS = WK.DAYS

def sim(sig, flip):
    """sig: {day: [(start minute, side, entry)]} -> per trade (day, points, outcome)."""
    out = []
    for d in DAYS:
        c1, busy = LS.sess[d], -1
        for m, side, e in sorted(sig.get(d, [])):
            if m <= busy or m > 871:
                continue
            sd = -side if flip else side
            stp, tg = e - sd * SL, e + sd * TP
            p, x, k = LS.walk(c1, sd, e, m, stp, (tg,), (1,))
            out.append((d, p, 'target' if k == 1 else 'stop' if p <= -SL - COST + 0.01 else '3:15'))
            busy = x
    return out

def g_key(confirm):
    s = collections.defaultdict(list)
    for d in DAYS:
        for m, side, e, *_ in LS.signals(d, confirm, 2):
            if m >= 560:
                s[d].append((m + 1, side, e))
    return s

def g_ap(tf, piv, sweep):
    s = collections.defaultdict(list)
    for d in DAYS:
        c1 = LS.sess[d]
        for placed, side, top, mid, ext, c1x, far in AP.setups(d, tf, piv, sweep):
            for m, o, h, l, c in c1:
                if m < placed:
                    continue
                if m > min(placed + 59, 870):
                    break
                if (l <= mid) if side > 0 else (h >= mid):
                    s[d].append((m + 1, side, min(o, mid) if side > 0 else max(o, mid)))
                    break
    return s

def g_weekly(conf, wick):
    s = collections.defaultdict(list)
    for d in DAYS:
        W, D = WK.WEEK[d], WK.daily_cpr(LS.CX[d])
        L = {k: v for k, v in W.items() if not conf or any(abs(v - x) <= 0.001 * v for x in D.values())}
        B = WK.blocks5(LS.sess[d])
        used = set()
        for i in range(1, len(B)):
            st, o, h, l, c = B[i]
            if st < 600 or st + 4 > 870:
                continue
            pc = B[i - 1][4]
            for name, lv in L.items():
                for side in (-1, 1):
                    if (name, side) in used:
                        continue
                    if (side < 0 and pc < lv <= h and c < lv) or (side > 0 and pc > lv >= l and c > lv):
                        used.add((name, side))
                        if wick and ((h - max(o, c)) if side < 0 else (min(o, c) - l)) < 0.5 * (h - l):
                            continue
                        s[d].append((st + 5, side, c))
    return s

def g_wbreak():
    s = collections.defaultdict(list)
    for d in DAYS:
        W = WK.WEEK[d]
        B = WK.blocks5(LS.sess[d])
        done = set()
        for i in range(1, len(B)):
            st, o, h, l, c = B[i]
            if st < 600 or st + 4 > 870:
                continue
            pc = B[i - 1][4]
            side = 1 if pc <= W['wTop'] < c else -1 if pc >= W['wBot'] > c else 0
            if side and side not in done:
                done.add(side)
                s[d].append((st + 5, side, c))
    return s

def g_reject(volk):
    s = collections.defaultdict(list)
    for d in DAYS:
        c1, cx = LS.sess[d], LS.CX[d]
        L = LS.day_levels(cx, c1)
        vol = LS.vol.get(d, {})
        B = WK.blocks5(c1)
        for bi, (st, o, h, l, c) in enumerate(B):
            if st < 570 or st + 4 > 870 or h - l <= 0:
                continue
            if volk:
                v = sum(vol.get(m, 0) for m in range(st, st + 5))
                past = [sum(vol.get(m, 0) for m in range(b[0], b[0] + 5)) for b in B[max(0, bi - 12):bi]]
                if not past or v < volk * sum(past) / len(past):
                    continue
            for name, lv in L.items():
                if h >= lv > c and (h - max(o, c)) >= 0.5 * (h - l):
                    s[d].append((st + 5, -1, c)); break
                if l <= lv < c and (min(o, c) - l) >= 0.5 * (h - l):
                    s[d].append((st + 5, 1, c)); break
    return s

def g_cpr(kind):
    s = collections.defaultdict(list)
    for d in DAYS:
        c1, lv = LS.sess[d], LS.CX[d]['lv']
        top, bot = lv['top'], lv['bot']
        done = set()
        if kind == '5m':
            B = WK.blocks5(c1)
            for i in range(1, len(B)):
                st, o, h, l, c = B[i]
                if st < 560 or st + 4 > 870:
                    continue
                pc = B[i - 1][4]
                side = 1 if pc <= top < c else -1 if pc >= bot > c else 0
                if side and side not in done:
                    done.add(side)
                    s[d].append((st + 5, side, c))
        else:
            for i in range(1, len(c1)):
                m, o, h, l, c = c1[i]
                if m < 556 or m > 870:
                    continue
                pc = c1[i - 1][4]
                if 1 not in done and pc < top <= h:
                    done.add(1); s[d].append((m + 1, 1, max(o, top)))
                if -1 not in done and pc > bot >= l:
                    done.add(-1); s[d].append((m + 1, -1, min(o, bot)))
    return s

def show(label, rows):
    st = LS.stats([(d, p) for d, p, _ in rows])
    r26 = [x for x in rows if x[0] >= '2026']
    n = len(r26)
    k = collections.Counter(o for _, _, o in r26)
    early = ' '.join(f"{y} {st[y]['net']:+6,}" for y in ('2023', '2024', '2025'))
    flag = '  <- every year +' if all(st[y]['net'] > 0 for y in LS.YEARS) else ''
    print(f"  {label:34} 2026: {n:4} trades | {TP} first {100 * k['target'] / max(1, n):3.0f}% | {SL} stop first "
          f"{100 * k['stop'] / max(1, n):3.0f}% | 3:15 {100 * k['3:15'] / max(1, n):3.0f}% | net {st['2026']['net']:+7,} || {early}{flag}")
    return st

if __name__ == '__main__':
    print(f"{NM.upper()}: target {TP} / stop {SL} points (the user's rule), costs {COST:g}; break-even: the target first on "
          f"{100 * (SL + COST) / (TP + SL):.0f}% of the trades (pure chance: {100 * SL / (TP + SL):.0f}%)")
    gens = {}
    gens['CPR break, 5-min close'] = g_cpr('5m')
    gens['CPR break, first touch'] = g_cpr('touch')
    for c in ('c1', 'c3', 'c5'):
        gens[f'key level {c}'] = g_key(c)
    for tf, piv, sw in itertools.product((1, 3, 5), (1, 2), ('wick', '2bar')):
        gens[f'A+ {tf}m piv{piv} {sw}'] = g_ap(tf, piv, sw)
    for conf, wick in itertools.product((False, True), (False, True)):
        gens[f"weekly {'confluence' if conf else 'all'} {'wick' if wick else 'any'}"] = g_weekly(conf, wick)
    gens['weekly CPR break'] = g_wbreak()
    for v in (0, 1.5):
        gens[f'rejection, volume {v or "any"}'] = g_reject(v)
    best = []
    for label, sig in gens.items():
        print(f"\n{label}")
        a = show('as it is', sim(sig, False))
        b = show('reversed', sim(sig, True))
        best += [(label + ' | as it is', a), (label + ' | reversed', b)]
    print("\nmade money in every year 2023-2026:", [k for k, s in best if all(s[y]['net'] > 0 for y in LS.YEARS)] or 'none')
    print("the best five in 2026:")
    for k, s in sorted(best, key=lambda kv: -kv[1]['2026']['net'])[:5]:
        print(f"  {k:52} 2026 {s['2026']['net']:+7,} ({s['2026']['n']} trades, {s['2026']['win']}% won) | 2023-25 "
              f"{s['2023']['net']:+,} / {s['2024']['net']:+,} / {s['2025']['net']:+,}")

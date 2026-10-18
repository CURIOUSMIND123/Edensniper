"""The weekly CPR next to the daily one (asked on 18 October 2026): as a filter on the calls, as levels for reversal
trades later in the day, and weekly CPR breaks after 10:00. 2023-2026, both indices, the calls with today's defaults
(largest stop Nifty 55 / Sensex 170); costs in; a 1-minute candle reaching both the stop and the target counts as the
stop.

    python weekly_cpr.py nifty        (or sensex)

Weekly levels from the previous week's high / low / close (official daily candles): pivot P = (H + L + C) / 3, CPR
bottom (H + L) / 2 and top 2P - bottom, R1 = 2P - L, S1 = 2P - H, R2 = P + (H - L), S2 = P - (H - L), and last week's
high / low.
A. FILTERS on the calls: BUY only above the weekly pivot / above the weekly CPR (SELL the other way); or skip a call
   when a weekly level lies between the entry and T1.
B. REVERSALS at weekly levels, 10:00-2:30, one at a time: a 5-minute candle reaches the level from one side and closes
   back (any candle / with a wick of at least half its range); enter at the close the other way, stop beyond the
   candle (+0.02%, at most 55 / 170 points); target 40 / 150 points, 2x the stop, or the next level (daily or weekly).
   Levels: every weekly level, or only those within 0.1% of a daily one (P, CPR, R1 / S1, R2 / S2, yesterday's high /
   low): confluence.
C. WEEKLY CPR BREAKS after 10:00: a 5-minute close above the weekly CPR top (from below) -> BUY, below its bottom ->
   SELL; stop at the other side of the weekly CPR (at most 55 / 170); target weekly R1 / S1, or 40 / 150 points.
D. The calls plus the version of B / C that did best on 2023-2025, one trade at a time.
"""
import collections, datetime as dt, itertools
import levels_style as LS

A = LS.A
NM, COST = LS.NM, LS.COST
CAP = {'nifty': 55, 'sensex': 170}[NM]
FIX = {'nifty': 40, 'sensex': 150}[NM]

# ---------------- weekly levels ----------------
weeks = collections.defaultdict(list)
for d in LS.Y.days:
    y, w, _ = dt.date.fromisoformat(d).isocalendar()
    weeks[(y, w)].append(d)
wkeys = sorted(weeks)
WEEK = {}
for i, k in enumerate(wkeys[1:], 1):
    ds = weeks[wkeys[i - 1]]
    H = max(LS.Y.DAY[x][1] for x in ds); L = min(LS.Y.DAY[x][2] for x in ds); C = LS.Y.DAY[ds[-1]][3]
    P = (H + L + C) / 3; bc = (H + L) / 2; tc = 2 * P - bc
    lv = dict(wP=P, wTop=max(tc, bc), wBot=min(tc, bc), wR1=2 * P - L, wS1=2 * P - H, wR2=P + (H - L), wS2=P - (H - L),
              wHigh=H, wLow=L)
    for d in weeks[k]:
        WEEK[d] = lv

def daily_cpr(cx):
    lv, yh, yl = cx['lv'], cx['yh'], cx['yl']
    P = lv['p']
    return dict(P=P, top=lv['top'], bot=lv['bot'], R1=2 * P - yl, S1=2 * P - yh, R2=P + (yh - yl), S2=P - (yh - yl),
                yh=yh, yl=yl)

DAYS = [d for d in LS.DAYS if d in WEEK]

def calls():
    out = []
    for d in DAYS:
        for t in A.day_trades(LS.CX[d], LS.sess[d], 929, True, False, 'classic'):
            if t['taken'] and t['exit']:
                out.append(dict(d=d, t=t, m=t['m'], x=t['exit']['m'], pnl=t['exit']['pnl']))
    return out

def blocks5(c1):
    b = collections.OrderedDict()
    for x in c1:
        b.setdefault(555 + (x[0] - 555) // 5 * 5, []).append(x)
    return [(s, v[0][1], max(x[2] for x in v), min(x[3] for x in v), v[-1][4]) for s, v in b.items() if len(v) == 5]

def exit_trade(c1, side, e, start, stp, tgt):
    p, x, _ = LS.walk(c1, side, e, start, stp, (tgt,), (1,))
    return p, x

def reversals(conf, wick, tgt):
    out = []
    for d in DAYS:
        c1, W, D = LS.sess[d], WEEK[d], daily_cpr(LS.CX[d])
        L = {k: v for k, v in W.items() if not conf or any(abs(v - x) <= 0.001 * v for x in D.values())}
        if not L:
            continue
        allv = sorted(set(list(W.values()) + list(D.values())))
        B = blocks5(c1)
        busy, used = -1, set()
        for i in range(1, len(B)):
            s, o, h, l, c = B[i]
            if s < 600 or s + 4 > 870 or s <= busy:
                continue
            pc = B[i - 1][4]
            for name, lv in L.items():
                for side in (-1, 1):
                    if (name, side) in used:
                        continue
                    if side < 0 and not (pc < lv <= h and c < lv):
                        continue
                    if side > 0 and not (pc > lv >= l and c > lv):
                        continue
                    used.add((name, side))
                    if wick and ((h - max(o, c)) if side < 0 else (min(o, c) - l)) < 0.5 * (h - l):
                        continue
                    e = c
                    stp = (h if side < 0 else l) - side * 0.0002 * lv
                    R = side * (e - stp)
                    if R <= 0:
                        continue
                    if R > CAP:
                        stp, R = e - side * CAP, CAP
                    if tgt == 'fixed':
                        T = e + side * FIX
                    elif tgt == '2R':
                        T = e + side * 2 * R
                    else:
                        ahead = [x for x in allv if side * (x - e) >= max(0.5 * R, 0.0005 * e)]
                        if not ahead:
                            continue
                        T = min(ahead, key=lambda x: side * (x - e))
                    p, x = exit_trade(c1, side, e, s + 5, stp, T)
                    out.append(dict(d=d, m=s + 4, x=x, pnl=p))
                    busy = x
                    break
                if busy >= s:
                    break
    return out

def breaks(tgt):
    out = []
    for d in DAYS:
        c1, W = LS.sess[d], WEEK[d]
        B = blocks5(c1)
        busy, done = -1, set()
        for i in range(1, len(B)):
            s, o, h, l, c = B[i]
            if s < 600 or s + 4 > 870 or s <= busy:
                continue
            pc = B[i - 1][4]
            side = 1 if pc <= W['wTop'] < c else -1 if pc >= W['wBot'] > c else 0
            if not side or side in done:
                continue
            done.add(side)
            e = c
            stp = W['wBot'] if side > 0 else W['wTop']
            R = side * (e - stp)
            if R <= 0:
                continue
            if R > CAP:
                stp, R = e - side * CAP, CAP
            T = (W['wR1'] if side > 0 else W['wS1']) if tgt == 'R1' else e + side * FIX
            if side * (T - e) <= 0.5 * R:
                continue
            p, x = exit_trade(c1, side, e, s + 5, stp, T)
            out.append(dict(d=d, m=s + 4, x=x, pnl=p))
            busy = x
    return out

def one_book(a, b):
    by = collections.defaultdict(list)
    for t in a + b:
        by[t['d']].append(t)
    out = []
    for d, ts in by.items():
        busy = -1
        for t in sorted(ts, key=lambda t: t['m']):
            if t['m'] > busy:
                out.append(t); busy = t['x']
    return out

rows = lambda ts: [(t['d'], t['pnl']) for t in ts]

if __name__ == '__main__':
    print(f"{NM.upper()} {DAYS[0]} - {DAYS[-1]}: the weekly CPR; costs {COST:g} points a trade; per year: trades, won %, net points")
    C = calls()
    LS.line('the calls now (stop at most %d)' % CAP, LS.stats(rows(C)), 46)
    print("\nA. THE WEEKLY CPR AS A FILTER ON THE CALLS")
    def keep(c, how):
        t, W = c['t'], WEEK[c['d']]
        sd, e = t['side'], t['e']
        if how == 'pivot':
            return sd * (e - W['wP']) > 0
        if how == 'cpr':
            return (e > W['wTop']) if sd > 0 else (e < W['wBot'])
        T1 = A.half_price(t)
        return not any(min(e, T1) < v < max(e, T1) for v in W.values())
    for how, lab in (('pivot', 'BUY above / SELL below the weekly pivot'), ('cpr', 'BUY above / SELL below the weekly CPR'),
                     ('room', 'no weekly level between the entry and T1')):
        k = [c for c in C if keep(c, how)]
        LS.line(lab, LS.stats(rows(k)), 46)
        LS.line('   the calls it took away', LS.stats(rows([c for c in C if not keep(c, how)])), 46)
    print("\nB. REVERSALS AT WEEKLY LEVELS, 10:00-2:30")
    res = {}
    for conf, wick, tgt in itertools.product((False, True), (False, True), ('fixed', '2R', 'next')):
        res[('rev', conf, wick, tgt)] = reversals(conf, wick, tgt)
        LS.line(f"{'confluence' if conf else 'all weekly'} | {'wick' if wick else 'any candle'} | target {tgt}",
                LS.stats(rows(res[('rev', conf, wick, tgt)])), 46)
    print("\nC. WEEKLY CPR BREAKS AFTER 10:00")
    for tgt in ('R1', 'fixed'):
        res[('brk', tgt)] = breaks(tgt)
        LS.line(f"break of the weekly CPR | target {'weekly R1 / S1' if tgt == 'R1' else 'fixed'}", LS.stats(rows(res[('brk', tgt)])), 46)
    best = max(res, key=lambda k: sum(t['pnl'] for t in res[k] if t['d'] < '2026'))
    print(f"\nD. THE CALLS + THE BEST OF B / C ON 2023-2025 ({best}), one trade at a time")
    LS.line('calls + that', LS.stats(rows(one_book(C, res[best]))), 46)
    LS.line('that alone', LS.stats(rows(res[best])), 46)

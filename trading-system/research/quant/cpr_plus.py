"""The CPR breakout calls with other indicators as one extra call type (asked on 19 October 2026: "use all strategies
that make money"). The filters of cpr_confluence.py that made money in each of 2023, 2024 and 2025 on BOTH indices,
taken together, with the user's rule (target 60 / 200 points, stop 35 / 100; out at 3:15); one trade at a time;
costs 4 / 12; a candle reaching both counts as the stop.

    python cpr_plus.py nifty        (or sensex)

The four filters (any one is enough; 'n2' = at least two):
  overlap    today's CPR overlaps yesterday's
  10-11:30   the breakout between 10:00 and 11:30
  pullback   the day opened beyond the CPR the trade's way, came back into it and broke out again, RSI 14 (5-minute)
             above 55 for a BUY / below 45 for a SELL
  inside     after 9:30, the breakout still inside the first 15-minute range
Entry, three ways: at the CPR top / bottom the moment it is touched (an order waiting there, or an alert from the
price every second); at the close of the 1-minute candle that touched it (an alert when the candle ends); or that
close only when it is beyond the CPR.
Also: with the current calls (default settings), each on its own (both may be open at once); and the CPR BREAK calls
as the alert program makes them (cprb_alerts.py: entry at the candle's close, any of the four), which should match.
"""
import collections
import cpr_confluence as CC
import levels_style as LS
import weekly_cpr as WK

A = LS.A
NM, COST, TP, SL = CC.NM, CC.COST, CC.TP, CC.SL

def ok(f, how):
    if how == 'all':
        return True
    hits = [f['rel'] == 'overlap', f['time'] == '10:00-11:30', f['opened'] == 'beyond already' and f['rsi'] == 'strong',
            f['range'] == 'inside']
    if how in ('overlap', '10-11:30', 'pullback', 'inside'):
        return hits[('overlap', '10-11:30', 'pullback', 'inside').index(how)]
    return sum(hits) >= (2 if how == 'n2' else 1)

def touches(entry, retry=False):
    """[(day, minute, side, entry price, first managed minute, features)] - each side once a day, 9:16-2:30 (retry:
    every touch until one meets a condition)."""
    out = []
    for d in CC.DAYS:
        c1, lv = LS.sess[d], LS.CX[d]['lv']
        top, bot = lv['top'], lv['bot']
        done = set()
        for i in range(1, len(c1)):
            m, o, h, l, c = c1[i]
            if m < 556 or m > 870:
                continue
            pc = c1[i - 1][4]
            for side, hit, lvl in ((1, pc < top <= h, top), (-1, pc > bot >= l, bot)):
                if side in done or not hit:
                    continue
                if not retry:
                    done.add(side)
                if entry == 'touch':
                    e, start = (max(o, lvl) if side > 0 else min(o, lvl)), m + 1
                else:
                    if entry == 'close beyond' and side * (c - lvl) <= 0:
                        continue
                    e, start = c, m + 1
                j = CC.last_bar(d, m)
                if j is None or j < 60:
                    continue
                f = CC.features(d, m, side, e, j)
                if retry and ok(f, 'any'):
                    done.add(side)
                if retry and not ok(f, 'any'):
                    continue
                out.append((d, m, side, e, start, f))
    return out

def run(ev, how):
    rows, busy = [], {}
    for d, m, side, e, start, f in ev:
        if not ok(f, how) or m <= busy.get(d, -1):
            continue
        p, x, k = LS.walk(LS.sess[d], side, e, start, e - side * SL, (e + side * TP,), (1,))
        rows.append(dict(d=d, m=m, x=x, pnl=p, hit=k == 1))
        busy[d] = x
    return rows

def show(label, rows):
    s = LS.stats([(r['d'], r['pnl']) for r in rows])
    hit = {y: [r['hit'] for r in rows if r['d'][:4] == y] for y in LS.YEARS}
    ys = ' | '.join(f"{y} {s[y]['n']:3} tr {100 * sum(hit[y]) / max(1, len(hit[y])):3.0f}% {s[y]['net']:+7,}" for y in LS.YEARS)
    flag = '  <- every year +' if all(s[y]['net'] > 0 for y in LS.YEARS) else ''
    print(f"  {label:34} {ys} | worst {s['all']['worst']:+5} dd {s['all']['dd']:+6,}{flag}")
    return s

if __name__ == '__main__':
    print(f"{NM.upper()}: CPR breakouts + filters, target {TP} / stop {SL}, costs {COST:g}; one at a time; per year: "
          f"trades, target first %, net points")
    best = {}
    for entry in ('touch', 'close', 'close beyond'):
        ev = touches(entry)
        print(f"\nENTRY: {entry}")
        show('all breakouts', run(ev, 'all'))
        for how in ('overlap', '10-11:30', 'pullback', 'inside', 'any', 'n2'):
            best[(entry, how)] = run(ev, how)
            show(how, best[(entry, how)])
    for entry in ('touch', 'close'):
        print(f"\nENTRY: {entry}, a later touch counts when the first ones met no condition")
        best[(entry + ' retry', 'any')] = run(touches(entry, True), 'any')
        show('any', best[(entry + ' retry', 'any')])
    calls = WK.calls()
    print("\nWITH THE CURRENT CALLS (each its own trade; both may be open)")
    show('current calls', [dict(d=c['d'], pnl=c['pnl'], hit=c['pnl'] > 0) for c in calls])
    for entry in ('touch', 'close'):
        for how in ('any', 'n2'):
            both = [dict(d=c['d'], pnl=c['pnl'], hit=c['pnl'] > 0) for c in calls] + best[(entry, how)]
            show(f'calls + {how} ({entry})', both)
    print("\nPER MONTH IN 2026 (entry at the touch, any filter)")
    by = collections.defaultdict(list)
    for r in best[('touch', 'any')]:
        if r['d'] >= '2026':
            by[r['d'][:7]].append(r)
    for mth, rs in sorted(by.items()):
        print(f"  {mth}: {len(rs):2} trades, target first {sum(r['hit'] for r in rs):2}, net {sum(r['pnl'] for r in rs):+6.0f}")
    print("\nTHE ALERT PROGRAM'S CPR BREAK CALLS (cprb_alerts.py, as it runs) against this test")
    A.CPR_CALLS = True
    rows = []
    for d in CC.DAYS:
        for t in A.day_trades(LS.CX[d], LS.sess[d], 929, True, False, 'classic'):
            if t['src'] == 'CPR BREAK' and t['taken'] and t['exit']:
                rows.append(dict(d=d, m=t['m'], x=t['exit']['m'], pnl=t['exit']['pnl'], hit=t['exit']['why'] == 'target'))
    A.CPR_CALLS = False
    show('alert program: CPR BREAK', rows)
    show('this test: close, any', best[('close', 'any')])

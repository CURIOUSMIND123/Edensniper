"""The alert program's extra calls (cprb_alerts.py: OPEN HIGH LOW on Nifty, GAP FILL, SECOND CHANCE and OI WALL on
Sensex), worked out minute by minute as it runs, against their tests (classic_setups.py, reentry.py, oi_test.py). The
CPR BREAK calls: cpr_plus.py.

    python extras_check.py nifty        (or sensex)
"""
import collections
import levels_style as LS
import classic_setups as C
import reentry as RE
import oi_test as OT

A = LS.A
LS.extras(True)
rows = collections.defaultdict(list)
for d in LS.DAYS:
    for t in A.day_trades(LS.CX[d], LS.sess[d], 929, True, False, 'classic'):
        if t['src'] in ('OPEN HIGH LOW', 'GAP FILL', 'SECOND CHANCE', 'OI WALL') and t['taken'] and t['exit']:
            rows[t['src']].append((d, t['exit']['pnl']))
LS.extras(False)
print(f"{LS.NM.upper()}: the alert program's extra calls against their tests")
if LS.NM == 'nifty':
    LS.line('alert program: OPEN HIGH LOW', LS.stats(rows['OPEN HIGH LOW']), 40)
    LS.line('test: open = high / low, 15 min, 1R', LS.stats(C.open_hl(15, '1R')), 40)
else:
    LS.line('alert program: GAP FILL', LS.stats(rows['GAP FILL']), 40)
    LS.line('test: gap fill 0.5%+, 9:20, half', LS.stats(C.gap_fill(0.5, '9:20', 'half', 'ext')), 40)
    LS.line('alert program: SECOND CHANCE', LS.stats(rows['SECOND CHANCE']), 40)
    test, seen = [], set()
    for d, t in RE.stopped_calls():
        if d in seen:
            continue
        en = RE.entry(d, t, 'pullback')
        if en:
            seen.add(d)
            test.append((d, RE.manage(LS.sess[d], t['side'], en[1], en[0] + 1, 170, '3:15')))
    LS.line('test: pullback, stop 170, 3:15', LS.stats(test), 40)
    LS.line('alert program: OI WALL', LS.stats(rows['OI WALL']), 40)
    LS.line('test: wall fade, candle stop 170, 2x, CPR', LS.stats([r for d in LS.DAYS for r in
                                                              OT.wall_trades(d, 'fade', A.OIWALL_STOP, 'candle:2x', True)]), 40)

"""2026 only: reward at least 3x (or 4x) the risk, put together: the pullback entry + CPR Magnet (+ volume lines),
stops at most 0.21% of price, out at the target, the stop, a time limit (60 / 120 minutes) or 3:15.

    python y2026_rr_combo.py nifty        (or sensex)
"""
import sys, collections
import y2026 as Y, y2026_rr as RR, y2026_short as S
D26 = Y.D26
def show(label, ts):
    r = RR.stats(ts)
    print(f"  {label:62} {r['n']:4} tr ({r['n']/9.3:4.1f}/mo) {100*r['w']/max(1,r['n']):3.0f}% won | avg win {r['avg_w']:+5.0f} avg loss {r['avg_l']:+5.0f} worst {r['worst']:+5.0f} | net {r['net']:+7,.0f} (Jan-Jun {r['a']:+6,.0f}, Jul-Oct {r['b']:+6,.0f}) fall {r['dd']:6,.0f} | {r['why']}")
def get(fam, cap, mode, tg, hold):
    P = dict(fam=fam, cap=cap, mode=mode, target=tg, hold=hold)
    return [dict(t, src='VOL' if fam == 'VOL' else 'PLAN') for d in D26 for t in RR.FAMS[fam](d, P)]
print(Y.B.name.upper())
for tg, hold, lab in (('4R', 0, '1:4, to 3:15'), ('3R', 0, '1:3, to 3:15'), ('3R', 120, '1:3, out within 2 hours'), ('3R', 60, '1:3, out within 60 min')):
    pb = get('PB', 0.0021, 'tighten', tg, hold); mg = get('MAG', 0.0021, 'tighten', tg, hold); vo = get('VOL', 0.0021, 'skip', tg, hold)
    show(f'pullback, stop<=0.21%, {lab}', pb)
    show(f'pullback + magnet, {lab}', S.one_book(pb + mg))
    show(f'pullback + magnet + volume lines (own stop <=0.21%), {lab}', S.one_book(pb + mg + vo))

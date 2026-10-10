"""2026 only: a short-trade system: the pullback after the 9:30 breakout + CPR Magnet + 3-day volume lines, every stop
at most 150 Sensex / 45 Nifty points, out within 30 or 60 minutes, no trailing, one trade at a time.

    python y2026_short_combo.py nifty        (or sensex)

Pullback: y2026_reversal.pullback (limit order at the broken 15-minute high / low, target 1.5R or 2R).
Magnet and volume lines: y2026_short (stop capped, target the CPR edge / the next volume line, all at the target).
"""
import sys, collections
import y2026 as Y, y2026_short as S, y2026_reversal as RV
D26, H1, CAP = Y.D26, Y.H1, S.CAPS[1]
def summ(label, ts):
    p = [t['pnl'] for t in ts]; a = sum(t['pnl'] for t in ts if t['d'] in H1)
    eq = pk = dd = 0
    for v in p: eq += v; pk = max(pk, eq); dd = min(dd, eq - pk)
    print(f"  {label:58} {len(p):4} tr ({len(p)/9.3:4.1f}/mo) {100*sum(v>0 for v in p)/max(1,len(p)):3.0f}% won net {sum(p):+7,.0f} (Jan-Jun {a:+6,.0f}, Jul-Oct {sum(p)-a:+6,.0f}) worst {min(p) if p else 0:+5.0f} fall {dd:6,.0f}")
for hold in (30, 60):
    for tg in ('1.5R', '2R'):
        P = (CAP, 'tighten', hold, 'target', False)
        PB = dict(fam='B', entry='limit', target=tg, hold=hold, cap=CAP, mode='tighten')
        pb = [t for d in D26 for t in RV.pullback(d, PB)]
        mag = [t for d in D26 for t in (S.magnet(d, P) or [])]
        vol = [t for d in D26 for t in S.vol(d, P)]
        print(f"{Y.B.name.upper()} stop<={CAP}, out within {hold} min, pullback target {tg}")
        summ('pullback after the breakout', pb)
        summ('CPR Magnet (stop capped, CPR edge, time limit)', mag)
        summ('volume lines (stop capped, next line, time limit)', vol)
        summ('pullback + magnet', S.one_book([dict(t, src='BO') for t in pb] + mag))
        summ('pullback + magnet + volume lines (one at a time)', S.one_book([dict(t, src='BO') for t in pb] + mag + vol))

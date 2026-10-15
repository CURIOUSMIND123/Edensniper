"""The same calls and entries as now, only the first stop closer: k x the distance to the setup's stop (k = 0.5 / 0.6 /
0.75 / 1 = now). Book half, the targets and the trail stay where they are now (measured on the setup's stop), so the
winners are managed the same; only a call that goes against us is cut sooner. 2023-2026, costs in, pessimistic fills.

    python tighter_stop.py nifty        (or sensex)
"""
import collections, sys
import levels_style as LS

A = LS.A

def run(k):
    rows = collections.defaultdict(list)
    for d in LS.DAYS:
        c1 = LS.sess[d]
        for t in A.day_trades(LS.CX[d], c1, 929, True, False, 'classic'):
            if not (t['taken'] and t['exit']):
                continue
            sd, e, st = t['side'], t['e'], t['known']
            R0 = sd * (e - t['stp0'])
            stp = e - sd * k * R0
            if t['src'] == 'VOLUME LINE':
                tg, fr = ((t['tgt'], t['tgt2']), (0.5, 0.5)) if t.get('tgt2') else ((t['tgt'],), (1,))
                p, _, _ = LS.walk(c1, sd, e, st, stp, tg, fr, be_at=1 if t.get('tgt2') else None)
            elif t['src'] == 'MAGNET':
                p, _, _ = LS.walk(c1, sd, e, st, stp, (t['t1'], t['edge']), (0.5, 0.5), be_at=1)
            else:
                R = t.get('R') or R0
                p, _, _ = LS.walk(c1, sd, e, st, stp, (e + sd * 0.25 * R,), (0.5,), be_at=1, trail=R)
            rows[t['src']].append((d, p))
            rows['ALL'].append((d, p))
    return rows

if __name__ == '__main__':
    print(f"{LS.NM.upper()} 2023-2026: the first stop at k x the setup's distance; per year: trades, won %, net points")
    for k in (1.0, 0.75, 0.6, 0.5):
        rows = run(k)
        for src in ('ALL', 'BREAKOUT', 'VOLUME LINE', 'MAGNET'):
            if len(rows[src]) >= 20:
                LS.line(f"k {k:.2f} {src}", LS.stats(rows[src]), 22)

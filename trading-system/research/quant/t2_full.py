"""The same calls, booked in full at T2, no half booking, no trailing; the stop at half the distance to T2 (asked on
16 October 2026). T1 / T2 as the app shows them (T1 = where half was booked, T2 = the next price level beyond it).
Out at T2, at the stop, or at 3:15. 2023-2026, costs 4 Nifty / 12 Sensex points, a candle reaching both counts as
the stop.

    python t2_full.py nifty        (or sensex)
"""
import collections
import levels_style as LS

A = LS.A

if __name__ == '__main__':
    now, new, info = [], [], collections.defaultdict(list)
    for d in LS.DAYS:
        cx, c1 = LS.CX[d], LS.sess[d]
        for t in A.day_trades(cx, c1, 929, True, False, 'classic'):
            if not (t['taken'] and t['exit']):
                continue
            sd, e, st = t['side'], t['e'], t['known']
            T2 = A.target_levels(cx, c1, sd, e, st, A.half_price(t))[1]
            d2 = sd * (T2 - e)
            stp = e - sd * 0.5 * d2
            pnl, xm, k = LS.walk(c1, sd, e, st, stp, (T2,), (1,))
            now.append((d, t['exit']['pnl']))
            new.append((d, pnl))
            y = d[:4]
            info[y].append(dict(hit=k == 1, stop=pnl <= -0.5 * d2 - LS.COST + 0.01, d2=d2, old=sd * (e - t['stp0']), pnl=pnl))
            info['all'].append(info[y][-1])
    print(f"{LS.NM.upper()} 2023-2026, the same {len(new)} calls; per year: trades, won %, net points")
    LS.line('now (half at T1, stop to entry, trail)', LS.stats(now))
    LS.line('all at T2, stop half of T2, no trailing', LS.stats(new))
    for y in LS.YEARS + ('all',):
        r = info[y]
        w = [x['pnl'] for x in r if x['pnl'] > 0]; l_ = [x['pnl'] for x in r if x['pnl'] <= 0]
        print(f"  {y:4}: T2 reached {100 * sum(x['hit'] for x in r) / len(r):3.0f}%, stop hit {100 * sum(x['stop'] for x in r) / len(r):3.0f}%, "
              f"the rest out at 3:15 | T2 on average {sum(x['d2'] for x in r) / len(r):4.0f} pts away, stop {sum(x['d2'] for x in r) / len(r) / 2:4.0f} "
              f"(now {sum(x['old'] for x in r) / len(r):4.0f}) | average win {sum(w) / max(1, len(w)):+5.0f}, loss {sum(l_) / max(1, len(l_)):+5.0f}")

"""Buy lower than the call (asked on 17 October 2026): the call comes at the breakout as now, but the order waits
30 points (Nifty) / 100 points (Sensex) better, until 2:30, with the stop at the same price (so the risk is 30 / 100
points smaller) and the same T1 / management. Which calls get filled, and what it makes. 2023-2026, costs in.

    python lower_buy.py nifty        (or sensex)
"""
import collections
import mae_study as M
LS, A = M.LS, M.A
OFF = 30 if LS.NM == 'nifty' else 100
rows, kinds, now = [], collections.Counter(), []
fill_kind = collections.Counter()
for d in LS.DAYS:
    c1 = LS.sess[d]
    for t in A.day_trades(LS.CX[d], c1, 929, True, False, 'classic'):
        if not (t['taken'] and t['exit']): continue
        out, worst, _ = M.path_info(c1, t)
        kind = 'reached T1 first' if out == 'T1' else 'hit the full SL' if out == 'stop' else 'neither by 3:15'
        kinds[kind] += 1
        now.append((d, t['exit']['pnl']))
        sd = t['side']; px = t['e'] - sd * OFF
        fill = None
        for m, o, h, l, c in c1:
            if m < t['known']: continue
            if m > 870: break
            if (o <= t['stp0']) if sd > 0 else (o >= t['stp0']): break
            if (l <= px) if sd > 0 else (h >= px):
                fill = (m, min(o, px) if sd > 0 else max(o, px)); break
        if not fill: continue
        fill_kind[kind] += 1
        stp = t['stp0']
        if sd * (fill[1] - stp) <= 0: continue
        fc = next(x for x in c1 if x[0] == fill[0])
        if (fc[3] <= stp) if sd > 0 else (fc[2] >= stp):
            rows.append((d, sd * (stp - fill[1]) - LS.COST)); continue
        rows.append((d, M.manage(c1, t, fill[1], fill[0] + 1, stp)[0]))
n = sum(kinds.values())
print(f"{LS.NM.upper()}: {n} calls; buy order {OFF} points lower than today's entry, valid until 2:30, same SL price")
for k in ('reached T1 first', 'hit the full SL', 'neither by 3:15'):
    print(f"  {k:17}: {kinds[k]:3} calls, the lower order filled on {fill_kind[k]:3} of them ({100 * fill_kind[k] / max(1, kinds[k]):.0f}%)")
print(f"  filled in all: {sum(fill_kind.values())} of {n} ({100 * sum(fill_kind.values()) / n:.0f}%)")
LS.line('now', LS.stats(now), 26)
LS.line(f'buy {OFF} lower', LS.stats(rows), 26)

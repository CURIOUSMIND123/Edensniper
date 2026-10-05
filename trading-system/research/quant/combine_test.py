"""All four strategies on Nifty together (one unit each), their correlation, and the agreement / conflict rules.

Run from this folder after levels15_build.py. The *_timed.py files are copies of the strategy references that also
return each trade's entry minute."""
import sys, csv, collections, statistics as st, numpy as np
sys.path.insert(0, '.')
import liquidity_trap_timed as lib5c, breakout_retest_timed as bpc, levels15_timed as simc
COST = 4.0
LT = dict(setup='trap', levels='pd', sweep=0.08, tp=0.25, sl=0.6, stop='fixed', start=570, last=870)
BR = dict(setup='levels', filter='expand', tol=0.12, trig='prevhigh', stop='fixed', sl=0.3, exit='trail', rr=0, trail=0.6, be=0.5, maxn=3)
LV = dict(lv='D', mt=0.1, smin=2, mode='break', tt=0.03, sb=0.12, rr=2.0, tgt='level', maxn=3)
T = []   # (strategy, day, entry minute, side, net points)
for d, b5, U, prev in lib5c.days5('nifty'):
    for side, e, x, why, m0 in lib5c.run_day(b5, U, prev, LT): T.append(('Liquidity Trap', d, m0, side, side * (x - e) - COST))
for d, s, e, x, why, m0 in bpc.run('nifty', BR): T.append(('Breakout Retest', d, m0, s, s * (x - e) - COST))
D = simc.data('nifty')
for dd in D['days']:
    if dd['d'] in D['levels']:
        for sd, e, x, why, m0 in simc.day_trades(dd['b5'], dd['U'], D['levels'][dd['d']]['D|0.1'], LV): T.append(('15-Day Levels', dd['d'], m0, sd, sd * (x - e) - COST))
for r in csv.DictReader(open('../fair_price_reversal_2023_2026.csv')):
    if r['index'] == 'nifty':
        hh, mm = map(int, r['opened'].split(':'))
        T.append(('Fair Price Reversal', r['day'], hh * 60 + mm, 1 if r['side'] == 'BUY' else -1, float(r['points']) - COST))
days = sorted({d for d, *_ in lib5c.days5('nifty')})
days = [d for d in days if d >= '2023-02-06']           # every strategy has its warm-up done by here
T = [t for t in T if t[1] >= days[0]]
names = ['Fair Price Reversal', 'Liquidity Trap', 'Breakout Retest', '15-Day Levels']
P = {'last 90 days': ('2026-07-03', '2026-10-01'), '90 days before': ('2026-04-04', '2026-07-02'), '2023': ('2023-01-01', '2023-12-31'),
     '2024': ('2024-01-01', '2024-12-31'), '2025': ('2025-01-01', '2025-12-31'), '2026': ('2026-01-01', '2026-10-01'), 'all': ('2023-01-01', '2026-10-01')}
def daily(ts):
    v = collections.defaultdict(float)
    for t in ts: v[t[1]] += t[4]
    return np.array([v.get(d, 0.0) for d in days])
def summary(label, ts):
    arr = daily(ts); out = [label]
    for pl, (a, b) in P.items():
        m = np.array([a <= d <= b for d in days]); out.append(f"{pl} {arr[m].sum():+,.0f}")
    cum = np.cumsum(arr); dd = (cum - np.maximum.accumulate(cum)).min()
    traded = (arr != 0).sum()
    print(f"{label:22s} | " + ' | '.join(out[1:]) + f" || {len(ts)/len(days):.1f} trades/day, green days {100*(arr>0).mean():.0f}%, red {100*(arr<0).mean():.0f}%, no trade {100*(arr==0).mean():.0f}%, worst day {arr.min():+,.0f}, deepest fall {dd:+,.0f}")
    return arr
print(f"{len(days)} days, {days[0]} to {days[-1]}; Nifty points after 4 pts cost per trade, one unit per trade\n")
arrs = {n: summary(n, [t for t in T if t[0] == n]) for n in names}
print()
allarr = summary('ALL FOUR TOGETHER', T)
print('\nCorrelation of daily results (1 = always move together, 0 = unrelated):')
M = np.corrcoef([arrs[n] for n in names])
for i, n in enumerate(names): print(f"  {n:22s} " + ' '.join(f"{M[i, j]:+.2f}" for j in range(len(names))))
# agreement: two different strategies enter the same direction within 30 minutes on the same day
by = collections.defaultdict(list)
for t in T: by[t[1]].append(t)
agree, disagree = [], []
for d, ts in by.items():
    ts.sort(key=lambda t: t[2])
    for i, a in enumerate(ts):
        for b in ts[i + 1:]:
            if b[2] - a[2] > 30: break
            if a[0] != b[0]:
                (agree if a[3] == b[3] else disagree).append((a, b))
def evals(pairs):
    later = [b[4] for a, b in pairs]
    return f"{len(pairs)} times ({len(pairs)/len(days):.2f} a day); the second trade made {sum(later):+,.0f} pts, won {100*sum(x > 0 for x in later)/max(1,len(later)):.0f}%"
print('\nTwo strategies signal the SAME direction within 30 minutes:', evals(agree))
print('Two strategies signal OPPOSITE directions within 30 minutes:', evals(disagree))
yrs = collections.defaultdict(float)
for a, b in agree: yrs[a[1][:4]] += b[4]
print('  same-direction second trades by year:', {k: round(v) for k, v in sorted(yrs.items())})
l90 = [b[4] for a, b in agree if a[1] >= '2026-07-03']
print('  same-direction second trades, last 90 days:', len(l90), 'trades', round(sum(l90)), 'pts')

print('\n== as trading rules')
def conflict_or_agree(t, window=30):
    prior = [u for u in by[t[1]] if u[0] != t[0] and 0 <= t[2] - u[2] <= window]
    return any(u[3] == t[3] for u in prior), any(u[3] != t[3] for u in prior)
agree_only = [t for t in T if conflict_or_agree(t)[0] and not conflict_or_agree(t)[1]]
no_conflict = [t for t in T if not conflict_or_agree(t)[1]]
summary('Agreement only', agree_only)
summary('All, skip conflicts', no_conflict)
for n in names:
    ts = [t for t in T if t[0] == n]
    a = [t[4] for t in ts if conflict_or_agree(t)[0] and not conflict_or_agree(t)[1]]
    c = [t[4] for t in ts if conflict_or_agree(t)[1]]
    o = [t[4] for t in ts if not any(conflict_or_agree(t))]
    print(f"  {n:22s} avg per trade: confirmed {st.mean(a) if a else 0:+6.1f} ({len(a)}) | contradicted {st.mean(c) if c else 0:+6.1f} ({len(c)}) | alone {st.mean(o) if o else 0:+6.1f} ({len(o)})")

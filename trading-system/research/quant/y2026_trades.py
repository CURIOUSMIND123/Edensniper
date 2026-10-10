"""2026 only: every trade of the CPR Breakout indicator (daily plan + 3-day volume lines, one trade at a time),
looked at one by one.

    python y2026_trades.py nifty        (or sensex)

For each trade: BUY (call) or SELL (put), which part of the plan, entry and exit, and
  before the exit   the best and worst point reached (how far it went our way / against us)
  after the exit    how far price kept going our way, and against us, until 3:15
Then: winners whose price kept running after we booked (money left), losers that were in profit first.
"""
import collections, statistics as st, sys
import y2026 as Y, y2026_losses as L, y2026_vol_lines as V

one, COST = Y.one, Y.COST
SC = {'nifty': 1.0, 'sensex': 3.2}[Y.B.name]          # Sensex points / 3.2 = Nifty-sized

def plan_trades(d):
    out = []
    for t in L.plan(d, poc=True):
        if t['src'] == 'MAG':
            out.append(dict(d=d, src='MAG', side=t['side'], m=556, e=one[d][0][4], mx=556 + t['mins'], pnl=t['pnl'], why=t['why']))
        else:
            out.append(dict(d=d, src='BO', side=t['side'], m=t['m'], e=t['e'], mx=t['mx'], pnl=t['pnl'], why='rev' if t.get('rev') else ''))
    return out

def one_book(ts):
    out = []; free = collections.defaultdict(int)
    for t in sorted(ts, key=lambda t: (t['d'], t['m'], t['src'] == 'VOL')):
        if t['m'] >= free[t['d']]: out.append(t); free[t['d']] = t['mx'] + 1
    return out

def excursions(t):
    d, s, e = t['d'], t['side'], t['e']
    inside = [x for x in one[d] if t['m'] <= x[0] <= t['mx']]
    after = [x for x in one[d] if t['mx'] < x[0] <= 915]
    t['mfe'] = max([s * ((x[2] if s > 0 else x[3]) - e) for x in inside] or [0])
    t['mae'] = max([s * (e - (x[3] if s > 0 else x[2])) for x in inside] or [0])
    ref = [x for x in one[d] if x[0] == t['mx']][0][4]
    t['after_fav'] = max([s * ((x[2] if s > 0 else x[3]) - ref) for x in after] or [0])
    t['after_adv'] = max([s * (ref - (x[3] if s > 0 else x[2])) for x in after] or [0])
    return t

TRADES = [excursions(t) for t in one_book([t for d in Y.D26 for t in plan_trades(d)] +
                                         [t for d in Y.D26 for t in V.day(d, 3, 'prev', 1.5, detail=True)])]

if __name__ == '__main__':
    ts = TRADES; n = lambda x: x / SC
    print(f"{Y.B.name.upper()} 2026: {len(ts)} trades (points{' / 3.2 = Nifty-sized' if SC != 1 else ''})")
    print("\nBY DIRECTION AND PART")
    for lab, f in (('BUY = call', lambda t: t['side'] > 0), ('SELL = put', lambda t: t['side'] < 0),
                   ('CPR Magnet', lambda t: t['src'] == 'MAG'), ('CPR Breakout', lambda t: t['src'] == 'BO'), ('3-day volume lines', lambda t: t['src'] == 'VOL')):
        xs = [t for t in ts if f(t)]; p = [t['pnl'] for t in xs]
        print(f"  {lab:20} {len(xs):3} trades, {sum(v > 0 for v in p):3} won / {sum(v <= 0 for v in p):3} lost, net {sum(p):+8,.0f}")
    win = [t for t in ts if t['pnl'] > 0]; lose = [t for t in ts if t['pnl'] <= 0]
    print("\nWINNERS: after we booked, did price turn (good exit) or keep going (money left)?")
    for src in ('MAG', 'BO', 'VOL'):
        xs = [t for t in win if t['src'] == src]
        if not xs: continue
        gains = [t['pnl'] + COST for t in xs]; more = [t['after_fav'] for t in xs]
        print(f"  {src:3} {len(xs):3} winners: average gain {n(st.mean(gains)):5.0f}; after the exit price went on another {n(st.median(more)):4.0f} "
              f"our way (median) before 3:15; went on more than the gain itself in {100*sum(m > g for m, g in zip(more, gains))/len(xs):3.0f}%; "
              f"turned against us first by over half the gain in {100*sum(t['after_adv'] > 0.5 * g for t, g in zip(xs, gains))/len(xs):3.0f}%")
    print("\nLOSERS: were they ever in profit first?")
    for src in ('MAG', 'BO', 'VOL'):
        xs = [t for t in lose if t['src'] == src]
        if not xs: continue
        mfe = [n(t['mfe']) for t in xs]
        print(f"  {src:3} {len(xs):3} losers: average loss {n(st.mean(t['pnl'] for t in xs)):5.0f}; best point before losing: median {st.median(mfe):4.0f}; "
              f"were up 10+ in {100*sum(v >= 10 for v in mfe)/len(xs):3.0f}%, 20+ in {100*sum(v >= 20 for v in mfe)/len(xs):3.0f}%; "
              f"stopped within 15 min in {100*sum(t['mx'] - t['m'] <= 15 for t in xs)/len(xs):3.0f}%")

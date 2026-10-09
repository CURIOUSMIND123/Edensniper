"""Closer look at the CPR "magnet" trade that held up in cpr_backtest.py.

    python cpr_magnet_check.py nifty        (or sensex)

Rule: today's CPR is NOT among the narrowest third of the last 20 days, and the 9:15 candle closes at least 0.2%
above the CPR top (or below its bottom). Sell (buy) at that close, target the CPR's near edge, stop 0.3% away,
out by 15:15. Prints narrow vs other days, a random-direction baseline, drawdown, and the last 90 sessions.
"""
import random, collections, statistics as st
import cpr_backtest as B

ARGS = ('1m', 0.2, 'edge', 0.3)

def stats(ts, label):
    p = [t[1] for t in ts]
    if not p: print(f'  {label}: no trades'); return
    eq = pk = dd = 0; streak = worst = 0
    for v in p:
        eq += v; pk = max(pk, eq); dd = min(dd, eq - pk)
        streak = streak + 1 if v <= 0 else 0; worst = max(worst, streak)
    w = [v for v in p if v > 0]; lo = [v for v in p if v <= 0]
    print(f"  {label}: {len(p)} trades, won {100*len(w)/len(p):.0f}%, avg win {st.mean(w):+.0f} / loss {st.mean(lo):+.0f}, "
          f"total {sum(p):+,.0f}, per trade {sum(p)/len(p):+.1f}, deepest fall {dd:,.0f}, longest losing run {worst}")

if __name__ == '__main__':
    print(f"{B.name.upper()} CPR magnet {ARGS}")
    for wf in ('notnarrow', 'narrow', 'any'):
        stats(B.run('magnet', ARGS + (wf,), B.TEST), f"{wf:9} since 2023")
    ts = B.run('magnet', ARGS + ('notnarrow',), B.TEST)
    real = sum(t[1] for t in ts)
    # same days, entries, stop and target distances; direction picked by a coin toss
    trades = []
    for d in sorted({t[0] for t in ts}):
        lv = B.LV[d]; e = B.one[d][0][4]; o = B.one[d][0][1]
        side = -1 if o > lv['top'] else 1
        edge = lv['top'] if side < 0 else lv['bot']
        trades.append((d, e, abs(edge - e), 0.003 * e))
    rnd = []
    for k in range(300):
        random.seed(k); tot = 0
        for d, e, tdist, sdist in trades:
            s = random.choice((1, -1)); tot += B.sim(d, s, 556, e, e - s * sdist, e + s * tdist)[0]
        rnd.append(tot)
    print(f"  random direction, same entries / stop / target distance: median {st.median(rnd):+,.0f}, "
          f"beat the real rule in {sum(x >= real for x in rnd)} of 300 runs (real {real:+,.0f})")
    mo = collections.defaultdict(float)
    for t in ts: mo[t[0][:7]] += t[1]
    print(f"  months: {sum(v > 0 for v in mo.values())} up, {sum(v <= 0 for v in mo.values())} down of {len(mo)}")
    l90 = set(B.TEST[-90:])
    print("  last 90 sessions, trade by trade (date, side, entry, CPR edge, result after costs):")
    for t in ts:
        if t[0] not in l90: continue
        lv = B.LV[t[0]]; o = B.one[t[0]][0][1]; side = 'SELL' if o > lv['top'] else 'BUY'
        edge = lv['top'] if side == 'SELL' else lv['bot']
        print(f"    {t[0]} {side:4} at {B.one[t[0]][0][4]:,.1f}  target {edge:,.1f}  {t[1]:+7.1f}  out {t[2]//60}:{t[2]%60:02d}")
    stats([t for t in ts if t[0] in l90], 'last 90 sessions')
    stats([t for t in ts if t[0] in set(B.TEST[-60:])], 'last 60 sessions')

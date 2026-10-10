"""2026 only: every strategy built so far, run on Bitcoin, and what leverage does to Rs 30,000.

    python btc_all.py

Bitcoin (Binance BTCUSDT futures) is fed through the same code as Nifty, as "btcist": its 1-minute candles during
Indian market hours, 9:15 am - 3:30 pm IST, every day including weekends. That gives Bitcoin the same session
shape the strategies were built for: an open, a gap from the night before, an opening range, a previous day.
Costs: 0.05% taker fee a side + 0.01% slippage = 0.11% of the price, about $79 at Bitcoin's 2026 median price.
Rules are each strategy's defaults; strategies sized in "usual range" units adapt to Bitcoin's size by themselves.
Leverage: the whole balance as margin at 1x-150x, compounding; a trade is counted as liquidated when its loss
before costs reaches 1/leverage - 0.4% (Binance maintenance margin). Moves against a trade that later recovered
aren't seen here, so real liquidations would come sooner than shown.
"""
import collections, datetime as dt, json, statistics as st, sys
sys.argv = ['x', 'btcist']
sys.path.insert(0, '..'); sys.path.insert(0, '../..')
COST = 78.8
D0, D1 = '2026-01-01', '2026-10-09'

def fair_price():
    import fair_price_backtest as FP
    from tci.fairprice import run_day, tested_params, usual_range
    ds = FP.days(json.load(open('../.cache/btcist_1m.json')))
    out, ranges, prev = [], [], None
    for d, bars in ds:
        rng = usual_range(ranges)
        if rng is not None and len(ranges) >= 10 and prev and D0 <= d <= D1:
            for t in run_day([prev[0]], bars, tested_params(rng)).trades:
                out.append((d, t.points - COST, bars[0].o))
        am = [b for b in bars if b.t.time() < dt.time(10, 45)]
        ranges.append(max(b.h for b in am) - min(b.l for b in am)); prev = bars
    return out

def liquidity_trap():
    import liquidity_trap_test as LT
    out = []
    for d, b5, U, prev in LT.days5('btcist'):
        if D0 <= d <= D1:
            for side, e, x, why, m in LT.run_day(b5, U, prev, LT.DEFAULT): out.append((d, side * (x - e) - COST, e))
    return out

def breakout_retest():
    import liquidity_trap_test as LT, breakout_retest_test as BR
    LT.COST['btcist'] = COST
    return [(d, s * (x - e) - COST, e) for d, s, e, x, why in BR.run('btcist', BR.DEFAULT) if D0 <= d <= D1]

def levels15():
    import levels15_test as L15
    L15.COST['btcist'] = COST
    price = {x['d']: x['b5'][0][1] for x in L15.data('btcist')['days']}
    return [(d, p, price[d]) for d, p, why in L15.run('btcist', L15.DEFAULT) if D0 <= d <= D1]

def bp_scalp():
    import breakout_probability_scalp as BP
    calls = BP.calls_in(D0, D1)
    first = {}
    for b in BP.bars: first.setdefault(b[0], b[2])
    return [(d, p, first[d]) for d, p, *_ in BP.scalp(calls, 20, 'break')]

def cpr_magnet():
    import cpr_backtest as B
    ds = [d for d in B.TEST if D0 <= d <= D1]
    return [(d, p, B.one[d][0][4]) for d, p, m in B.run('magnet', ('1m', 0.2, 'edge', 0.3, 'notnarrow'), ds)]

def cpr_breakout_trail():
    import cpr_orb as C
    P = ('none', 'none', 'none', 'notagainst', 'narrow', 'touch', 'range', 'trail', 'yes')
    return [(d, p, C.one[d][0][1]) for d in C.TEST if D0 <= d <= D1 for d, p, side, R in C.day(d, P)]

def cpr_breakout_scalp():
    import cpr_orb_winrate as W
    return [(d, p, W.one[d][0][1]) for d in W.TEST if D0 <= d <= D1 for d, p in W.day(d, 'narrow', ('half', 0.25), True, ('gap',))]

def cpr_level_scalp():
    import cpr_scalp as X
    return [(d, p, X.one[d][0][1]) for d in X.TEST if D0 <= d <= D1 for d, p, hold in X.day(d, ('cpr', 'break', 30, 30, 0, 'any', 'cpr'))]

def daily_plan():
    import y2026 as Y, y2026_losses as L
    return [(t['d'], t['pnl'], Y.one[t['d']][0][1]) for d in Y.D26 for t in L.plan(d, poc=True)]

STRATS = [('Fair Price Reversal', fair_price), ('Liquidity Trap', liquidity_trap), ('Breakout Retest', breakout_retest),
          ('15-Day Levels', levels15), ('Breakout Probability scalp (stop 20 / target 40)', bp_scalp),
          ('CPR Magnet', cpr_magnet), ('CPR Breakout, trail', cpr_breakout_trail), ('CPR Breakout, scalp mode', cpr_breakout_scalp),
          ('CPR level scalp (best on both indices)', cpr_level_scalp), ('Daily plan (CPR Breakout indicator default)', daily_plan)]

def lever(ts, L):
    eq = 30000.0; liq = 1 / L - 0.004
    for d, p, ref in sorted(ts):
        if -(p + COST) / ref >= liq: return 0.0, d
        eq *= 1 + L * p / ref
        if eq < 100: return eq, d
    return eq, None

if __name__ == '__main__':
    print(f"Bitcoin, 9:15 am - 3:30 pm IST sessions, {D0} to {D1}, cost {COST} points (0.11%) a trade")
    rows = []
    for nm, fn in STRATS:
        ts = fn(); p = [t[1] for t in ts]
        if not p: print(f"  {nm}: no trades"); continue
        pct = [t[1] / t[2] for t in ts]; w = sum(v > 0 for v in p)
        h1 = sum(t[1] / t[2] for t in ts if t[0] < '2026-07-01'); h2 = sum(pct) - h1
        print(f"\n  {nm}: {len(p)} trades ({len(p)/9.3:.1f} a month), {w} won / {len(p)-w} lost, total {100*sum(pct):+.1f}% of price "
              f"(Jan-Jun {100*h1:+.1f}%, Jul-Oct {100*h2:+.1f}%), average {100*st.mean(pct):+.3f}% a trade; before costs {100*(sum(pct) + len(p)*0.0011):+.1f}%")
        out = []
        for L in (1, 2, 3, 5, 10, 20, 50, 100, 150):
            eq, bust = lever(ts, L)
            out.append(f"{L}x Rs {eq:,.0f}" + (f" (wiped out {bust})" if bust else ''))
        print('     ' + ' | '.join(out))

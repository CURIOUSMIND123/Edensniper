"""2026 only: what Rs 30,000 becomes with the indicator as it is now (daily plan + 3-day volume lines, one trade at a
time per index), trading both Nifty and Sensex from one account.

    python y2026_money.py

Lots: 2 per trade / 5 per trade / 2 until the account reaches Rs 75,000, then 5.
Conversion as in y2026_rupees.py: an at-the-money option moves about half the index, so one index point is worth
Rs 32.5 per Nifty lot (65) and Rs 10 per Sensex lot (20); costs are already in the points. Time decay and the extra
brokerage of booking half are left out. Also: the same trades in random order (10,000 runs).
"""
import collections, random, sys

RS = {'nifty': 32.5, 'sensex': 10.0}

def trades(name):
    sys.argv = ['x', name]
    for m in [m for m in sys.modules if m.startswith(('y2026', 'cpr_', 'pa_ml'))]: sys.modules.pop(m)
    import y2026_combo as K
    return [(d, m, name, p) for d, p, m, mx, src in K.one_book(K.plan_trades() + K.vol_trades(1.5))]

def run(ts, lots_rule):
    eq = pk = low = 30000.0; dd = 0; mo = collections.defaultdict(float); won = lost = 0
    for d, m, name, p in ts:
        r = p * RS[name] * lots_rule(eq); eq += r; mo[d[:7]] += r
        pk = max(pk, eq); dd = min(dd, eq - pk); low = min(low, eq); won += r > 0; lost += r <= 0
    return eq, dd, low, mo, won, lost

if __name__ == '__main__':
    ts = sorted(trades('nifty') + trades('sensex'))
    n = len(ts); w = sum(t[3] > 0 for t in ts)
    print(f"Both indices, 2026 (1 Jan - 9 Oct): {n} trades ({n / 9.3:.0f} a month), {w} won / {n - w} lost ({100 * w / n:.0f}%)")
    rules = {'2 lots': lambda eq: 2, '5 lots': lambda eq: 5, '2 lots, 5 from Rs 75,000': lambda eq: 5 if eq >= 75000 else 2}
    for lab, rule in rules.items():
        eq, dd, low, mo, _, _ = run(ts, rule)
        print(f"  {lab:26} Rs 30,000 -> Rs {eq:,.0f}. Biggest fall Rs {-dd:,.0f}; lowest Rs {low:,.0f}; "
              f"losing months {sum(v < 0 for v in mo.values())} of {len(mo)}")
        print("     by month: " + ', '.join(f"{k[5:]} {v / 1000:+.0f}k" for k, v in sorted(mo.items())))
        random.seed(1); bust = half = 0
        for _ in range(10000):
            sh = ts[:]; random.shuffle(sh)
            _, _, lo, _, _, _ = run(sh, rule); bust += lo <= 0; half += lo < 15000
        print(f"     random order: below Rs 15,000 in {half / 100:.1f}% of runs, below zero in {bust / 100:.1f}%")

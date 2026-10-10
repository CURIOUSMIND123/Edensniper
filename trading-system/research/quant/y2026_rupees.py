"""2026 only: what the daily plan would have done to Rs 30,000 traded with at-the-money options.

    python y2026_rupees.py

Conversion: an at-the-money option moves about half as much as the index (delta 0.5), so one index point is worth
0.5 x lot size rupees per lot: Nifty lot 65 -> Rs 32.5, Sensex lot 20 -> Rs 10. Costs are already in the points
(4 Nifty / 12 Sensex points a trade = about Rs 130 / Rs 120 per lot). 2 lots per trade (the plan books half).
Ignores time decay and the extra cost of booking half separately, so treat the rupee figures as rough.
"""
import collections, sys

START, LOTS = 30000, 2
RS = {'nifty': 0.5 * 65, 'sensex': 0.5 * 20}

def trades(name, poc):
    sys.argv = ['x', name]
    for m in ('y2026_losses', 'y2026_daily', 'y2026', 'pa_ml', 'cpr_orb_winrate', 'cpr_orb', 'cpr_backtest'):
        sys.modules.pop(m, None)
    import y2026 as Y, y2026_losses as L
    return [(t['d'], t['pnl'] * RS[name] * LOTS) for d in Y.D26 for t in L.plan(d, poc=poc)]

def report(label, ts):
    ts = sorted(ts); eq = START; pk = START; dd = 0; streak = worst = 0
    mo = collections.defaultdict(float)
    for d, r in ts:
        eq += r; pk = max(pk, eq); dd = min(dd, eq - pk); mo[d[:7]] += r
        streak = streak + 1 if r <= 0 else 0; worst = max(worst, streak)
    w = [r for _, r in ts if r > 0]; l = [r for _, r in ts if r <= 0]
    print(f"{label}: {len(ts)} trades on {len({d for d, _ in ts})} days ({len(ts)/9.3:.1f} a month), {len(w)} won / {len(l)} lost")
    print(f"   Rs 30,000 -> Rs {eq:,.0f} ({100*(eq-START)/START:+.0f}%). Won Rs {sum(w):,.0f}, lost Rs {-sum(l):,.0f}. "
          f"Biggest fall from a high: Rs {-dd:,.0f}. Longest losing run: {worst}. Biggest single loss: Rs {-min(l) if l else 0:,.0f}")
    print("   by month: " + ', '.join(f"{k[5:]} {v:+,.0f}" for k, v in sorted(mo.items())))

if __name__ == '__main__':
    for poc, lab in ((True, 'indicator default (magnet only on the POC side)'), (False, 'earlier daily plan (more trades)')):
        n, s = trades('nifty', poc), trades('sensex', poc)
        print(f"\n=== {lab} ===")
        report('Nifty, 2 lots', n)
        report('Sensex, 2 lots', s)
        report('Both indices (needs about Rs 30,000 of premium on days both trade)', n + s)

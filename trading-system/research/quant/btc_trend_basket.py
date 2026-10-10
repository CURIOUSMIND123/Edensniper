"""The 4-hour trend-following family from btc_trend.py, traded as a basket (run btc_trend.py first).

    python btc_trend_basket.py

All 20 four-hour Donchian and EMA versions made money over 2023-2025. Rs 30,000 split equally across them, each
compounding on its own at 1x-150x (liquidation when the worst move inside a trade reaches 1/leverage - 0.4%), or
sized by risk per trade from each trade's stop. Shown for 2026 and for the 2023-2025 design years.
"""
import json
R = json.load(open('../.cache/btc_trend_trades.json'))
fam4 = [k for k in R if k.startswith('donchian|(4,') or k.startswith('ema|(4,')]
def grow(ts, L, start):
    eq = start
    for t in ts:
        if t[5] >= 1 / L - 0.004: return 0.0
        eq *= 1 + L * t[4]
    return eq
def grow_risk(ts, r, start, cap=10):
    eq = start
    for t in ts:
        L = min(cap, r / max(t[6], 1e-4))
        if t[5] >= 1 / L - 0.004: return 0.0
        eq *= 1 + L * t[4]
    return eq
for period, a, b in (('2026', '2026-01-01', '2027'), ('2023-2025 (design years)', '2023-01-01', '2026-01-01')):
    pick = {k: [t for t in R[k] if a <= t[0] < b] for k in fam4}
    print(f"{period}: {sum(sum(t[4] for t in v) > 0 for v in pick.values())} of {len(fam4)} versions made money; "
          f"average {100 * sum(sum(t[4] for t in v) for v in pick.values()) / len(fam4):+.1f}% per version at 1x")
    for L in (1, 2, 3, 5, 10, 20, 150):
        res = [grow(v, L, 30000 / len(fam4)) for v in pick.values()]
        print(f"   {L:3}x: Rs {sum(res):,.0f}" + (f"  ({sum(x == 0 for x in res)} of {len(fam4)} versions wiped out)" if any(x == 0 for x in res) else ''))
    for r in (0.01, 0.02):
        print(f"   risk {int(r*100)}% per trade (leverage from the stop, at most 10x): Rs {sum(grow_risk(v, r, 30000 / len(fam4)) for v in pick.values()):,.0f}")

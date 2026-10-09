"""Walk-forward check of every CPR + pivot version in cpr_backtest.py (run that first for nifty and sensex).

    python cpr_walkforward.py

Picks the versions with the best combined result (Nifty points + Sensex points / 3.2) from February 2023 to June
2025 only, then shows what they did from July 2025 to today, which they never saw.
"""
import json
CUT = '2025-07-01'
N = {(r['fam'], *r['args']): r for r in json.load(open('../.cache/cpr_nifty.json'))}
S = {(r['fam'], *r['args']): r for r in json.load(open('../.cache/cpr_sensex.json'))}
def part(r, before):
    return sum(v for d, v in r['daily'].items() if (d < CUT) == before)
def comb(k, before): return part(N[k], before) + part(S[k], before) / 3.2
ks = sorted(N, key=lambda k: -comb(k, True))
print(f"Best 10 versions on Feb 2023 - Jun 2025 (combined Nifty-equivalent points), and the same versions from {CUT}:")
for k in ks[:10]:
    print(f"  {str(k):55} before {comb(k, True):+7,.0f} | after: Nifty {part(N[k], False):+7,.0f}, Sensex {part(S[k], False):+8,.0f}, combined {comb(k, False):+7,.0f}")
after = [comb(k, False) for k in ks]
print(f"\nAll {len(ks)} versions after {CUT}: {sum(x > 0 for x in after)} made money. Top 10 before -> {sum(comb(k, False) > 0 for k in ks[:10])} of 10 made money after;"
      f" top 50 -> {sum(comb(k, False) > 0 for k in ks[:50])} of 50.")

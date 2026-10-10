"""Win rate vs profit for the cpr_orb_winrate.py versions (run that for nifty and sensex first).

    python cpr_winrate_pick.py
"""
import json
N = {json.dumps(r['P']): r for r in json.load(open('../.cache/cpr_winrate_nifty.json'))}
S = {json.dumps(r['P']): r for r in json.load(open('../.cache/cpr_winrate_sensex.json'))}
wr = lambda r, k='90': r['w' + ('90' if k == '90' else '')] / max(1, r['n' + ('90' if k == '90' else '')])

print("How many versions reached each win rate in the last 90 sessions (10+ trades), and how many of those made money:")
for lab, D in (('Nifty', N), ('Sensex', S)):
    for thr in (0.9, 0.8, 0.7):
        hi = [r for r in D.values() if r['n90'] >= 10 and wr(r) >= thr]
        print(f"  {lab} {int(thr*100)}%+: {len(hi)} versions; made money in the last 90: {sum(r['net90'] > 0 for r in hi)}; "
              f"also since 2023: {sum(r['net90'] > 0 and r['net'] > 0 for r in hi)}; won {int(thr*100)}%+ since 2023 too: "
              f"{sum(r['net90'] > 0 and r['net'] > 0 and wr(r, 'all') >= thr for r in hi)}")

print("\nHighest win rate that made money in the last 90 AND since 2023 on BOTH indices (12+ trades in 90 sessions each):")
ok = [k for k in N if N[k]['n90'] >= 12 and S[k]['n90'] >= 12 and min(N[k]['net90'], S[k]['net90'], N[k]['net'], S[k]['net']) > 0]
for k in sorted(ok, key=lambda k: -min(wr(N[k]), wr(S[k])))[:12]:
    n, s = N[k], S[k]
    print(f"  {k}\n     Nifty  last90 {n['n90']} tr, {n['w90']} won / {n['n90']-n['w90']} lost ({100*wr(n):.0f}%), {n['won90']:+,.0f} / {n['lost90']:+,.0f} = {n['net90']:+,.0f}; "
          f"since 2023 {n['n']} tr {100*wr(n,'all'):.0f}% {n['net']:+,.0f} [{', '.join(f'{v:+,.0f}' for _, v in sorted(n['yrs'].items()))}]"
          f"\n     Sensex last90 {s['n90']} tr, {s['w90']} won / {s['n90']-s['w90']} lost ({100*wr(s):.0f}%), {s['won90']:+,.0f} / {s['lost90']:+,.0f} = {s['net90']:+,.0f}; "
          f"since 2023 {s['n']} tr {100*wr(s,'all'):.0f}% {s['net']:+,.0f} [{', '.join(f'{v:+,.0f}' for _, v in sorted(s['yrs'].items()))}]")

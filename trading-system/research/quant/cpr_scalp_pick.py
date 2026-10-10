"""Which cpr_scalp.py scalping versions hold up on both indices (run cpr_scalp.py for nifty and sensex first).

    python cpr_scalp_pick.py
"""
import json
N = {json.dumps(r['P']): r for r in json.load(open('../.cache/cpr_scalp_nifty.json'))}
S = {json.dumps(r['P']): r for r in json.load(open('../.cache/cpr_scalp_sensex.json'))}
wr = lambda r, a='90': r['w' + a] / max(1, r['n' + a]) if a else r['w'] / max(1, r['n'])
ok = [k for k in N if N[k]['n90'] >= 20 and S[k]['n90'] >= 20 and min(N[k]['net90'], S[k]['net90'], N[k]['net'], S[k]['net']) > 0]
print(f"{len(N)} scalping versions; made money in the last 90 sessions and since 2023 on both indices (20+ trades): {len(ok)}")
print("Highest win rates among them:")
for k in sorted(ok, key=lambda k: -min(wr(N[k]), wr(S[k])))[:10]:
    n, s = N[k], S[k]
    print(f"  {k}\n     Nifty  last90 {n['n90']} tr, {n['w90']} won / {n['n90']-n['w90']} lost ({100*wr(n):.0f}%), {n['won90']:+,.0f} / {n['lost90']:+,.0f} = {n['net90']:+,.0f}; "
          f"since 2023 {n['n']} tr {100*wr(n, ''):.0f}% {n['net']:+,.0f} ({n['net']/max(1,n['n']):+.1f} a trade) [{', '.join(f'{v:+,.0f}' for _, v in sorted(n['yrs'].items()))}] hold {n['hold']:.0f} min"
          f"\n     Sensex last90 {s['n90']} tr, {s['w90']} won / {s['n90']-s['w90']} lost ({100*wr(s):.0f}%), {s['won90']:+,.0f} / {s['lost90']:+,.0f} = {s['net90']:+,.0f}; "
          f"since 2023 {s['n']} tr {100*wr(s, ''):.0f}% {s['net']:+,.0f} ({s['net']/max(1,s['n']):+.1f} a trade) [{', '.join(f'{v:+,.0f}' for _, v in sorted(s['yrs'].items()))}] hold {s['hold']:.0f} min")

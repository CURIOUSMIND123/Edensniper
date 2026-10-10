"""Which cpr_orb.py versions hold up on both indices (run cpr_orb.py for nifty and sensex first).

    python cpr_orb_pick.py

Sensex points are divided by 3.2 to put them in Nifty-sized points. Shows versions that made money in the last 90
sessions and since 2023 on both indices, every year if any, and a walk-forward check: versions picked on
February 2023 to June 2025 only, then what they did from July 2025.
"""
import json
CUT = '2025-07-01'
YRS = ('2023', '2024', '2025', '2026')
N = {tuple(r['P']): r for r in json.load(open('../.cache/cpr_orb_nifty.json'))}
S = {tuple(r['P']): r for r in json.load(open('../.cache/cpr_orb_sensex.json'))}
def yr(r, y): return sum(v for d, v in r['daily'].items() if d.startswith(y))
def part(r, before): return sum(v for d, v in r['daily'].items() if (d < CUT) == before)
def comb(k, f): return f(N[k]) + f(S[k]) / 3.2
def line(k):
    out = []
    for lab, r in (('Nifty', N[k]), ('Sensex', S[k])):
        out.append(f"{lab} last90 {r['n90']}tr {100*r['w90']/max(1,r['n90']):.0f}% won {r['net90']:+,.0f} "
                   f"(won {r['win_pts']:+,.0f} / lost {r['loss_pts']:+,.0f}); since 2023 {r['n']}tr {100*r['w']/max(1,r['n']):.0f}% {r['net']:+,.0f} ["
                   + ' '.join(f"{yr(r, y):+,.0f}" for y in YRS) + ']')
    return '\n      '.join(out)
both = [k for k in N if N[k]['net90'] > 0 and S[k]['net90'] > 0 and N[k]['net'] > 0 and S[k]['net'] > 0]
every = [k for k in both if all(yr(N[k], y) > 0 and yr(S[k], y) > 0 for y in YRS)]
print(f"{len(N)} versions. Made money in the last 90 sessions AND since 2023 on both indices: {len(both)}; of those, every year on both: {len(every)}")
print("\nTop 10 of those by combined result since 2023:")
for k in sorted(both, key=lambda k: -comb(k, lambda r: r['net']))[:10]:
    print(f"  {k}\n      {line(k)}")
print("\nEvery year on both indices:")
for k in sorted(every, key=lambda k: -comb(k, lambda r: r['net'])):
    print(f"  {k}\n      {line(k)}")
ks = sorted(N, key=lambda k: -comb(k, lambda r: part(r, True)))
print(f"\nWalk-forward: best 10 on Feb 2023 - Jun 2025, and what they did from {CUT} (Nifty, Sensex):")
for k in ks[:10]:
    print(f"  {str(k):80} before {comb(k, lambda r: part(r, True)):+7,.0f} | after {part(N[k], False):+7,.0f} {part(S[k], False):+8,.0f}")
print(f"  top 50 before: {sum(comb(k, lambda r: part(r, False)) > 0 for k in ks[:50])} of 50 made money after; "
      f"all versions: {sum(comb(k, lambda r: part(r, False)) > 0 for k in ks)} of {len(ks)}")

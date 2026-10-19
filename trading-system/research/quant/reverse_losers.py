"""Reverse the losing strategies (asked on 19 October 2026): every trade of the losing families tested here, taken the
other way - same entry and time, the stop where the target was and the target where the stop was - and the costs paid
again. Which reversed versions won 70%+ and made money in each of 2023, 2024 and 2025 (chosen without 2026); then 2026.

    python reverse_losers.py nifty        (or sensex)

Families: key-level reversals with a very small stop (levels_style.py, 144 versions), the A+ setup (aplus_setup.py,
192), reversals at weekly levels and weekly CPR breaks (weekly_cpr.py, 14), rejection candles with volume
(pullback.py, 4).
A reversed trade's points before costs are the original's with the sign changed (it exits where the original did:
its target is the original's stop and its stop the original's target; a 3:15 exit at the same price), so after costs
it makes -(original + cost) - cost. Where one 1-minute candle reached both the stop and the target the original
counted the stop; the reversed trade is counted as winning there, so the reversed results are if anything a little
better than real.
"""
import collections, itertools
import levels_style as LS
import aplus_setup as AP
import weekly_cpr as WK
import pullback as PB

NM, COST = LS.NM, LS.COST

def rev(rows):
    return [(d, -p - 2 * COST) for d, p in rows]

def qual(s):
    return all(s[y]['n'] >= 20 and s[y]['win'] >= 70 and s[y]['net'] > 0 for y in ('2023', '2024', '2025'))

if __name__ == '__main__':
    fam = {}
    for confirm, nk, maxr, tgt, last in itertools.product(('c1', 'c3', 'c5'), (2, 3), (0.0008, 0.0012, 0.002),
                                                          ('next', '1.5R', '2R', '3R'), ('60m', '3:15')):
        fam[f'key level {confirm} last{nk} stop<={maxr * 100:.2f}% {tgt} {last}'] = \
            [(d, p) for d, p, *_ in LS.level_trades(confirm, nk, maxr, tgt, last)]
    for v in itertools.product((1, 3, 5), (1, 2), ('wick', '2bar'), ('top', 'mid'), ('sweep', 'c1'), ('2R', '3R', 'half', 'liq')):
        fam['A+ ' + ' '.join(map(str, v))] = [(t['d'], t['pnl']) for t in AP.trades(*v)]
    for conf, wick, tgt in itertools.product((False, True), (False, True), ('fixed', '2R', 'next')):
        fam[f"weekly {'confluence' if conf else 'all'} {'wick' if wick else 'any'} {tgt}"] = \
            [(t['d'], t['pnl']) for t in WK.reversals(conf, wick, tgt)]
    for tgt in ('R1', 'fixed'):
        fam[f'weekly CPR break {tgt}'] = [(t['d'], t['pnl']) for t in WK.breaks(tgt)]
    for volk, tgt in itertools.product((0, 1.5), ('fixed', 'next')):
        fam[f'rejection candle vol{volk} {tgt}'] = PB.reversals(volk, tgt)

    print(f"{NM.upper()} 2023-2026: {len(fam)} versions of the losing families, each reversed; costs {COST:g} points a trade")
    orig_lost = [k for k, r in fam.items() if sum(p for d, p in r) < 0]
    print(f"  versions that lost over the four years: {len(orig_lost)} of {len(fam)}")
    S = {k: (LS.stats(r), LS.stats(rev(r))) for k, r in fam.items() if len(r) >= 60}
    gross = {k: sum(p + COST for d, p in fam[k]) / len(fam[k]) for k in S}
    print(f"  points a trade before costs, originals: median {sorted(gross.values())[len(gross) // 2]:+.1f} "
          f"(costs {COST:g}); reversed versions that made money over 2023-2026: "
          f"{sum(1 for k in S if S[k][1]['all']['net'] > 0)} of {len(S)}")
    q = [k for k in S if qual(S[k][1])]
    print(f"  reversed versions with 70%+ won and money made in each of 2023, 2024, 2025: {len(q)}")
    for k in sorted(q, key=lambda k: -S[k][1]['all']['net'])[:15]:
        LS.line(k, S[k][1], 46)
    print("  the reversed versions that made the most over 2023-2025 (whatever the win rate):")
    for k in sorted(S, key=lambda k: -sum(S[k][1][y]['net'] for y in ('2023', '2024', '2025')))[:8]:
        LS.line(k, S[k][1], 46)
    print("  the reversed versions with the highest win rate over 2023-2025:")
    for k in sorted(S, key=lambda k: -min(S[k][1][y]['win'] for y in ('2023', '2024', '2025')))[:6]:
        LS.line(k, S[k][1], 46)

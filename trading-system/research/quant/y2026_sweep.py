"""2026 only: the liquidity sweep of yesterday's high / low (the one setup from y2026_smc.py that improved the
indicator's best version in both halves of 2026 on both indices), checked closely.

    python y2026_sweep.py nifty        (or sensex)

The rule: a 5-minute candle (9:30-2:30) trades above yesterday's high and closes back below it (the candle before
closed below it) -> SELL at the close; the mirror image at yesterday's low -> BUY. Stop 0.02% beyond the candle's
high / low; target 3x the stop; out by 3:15. Added to the indicator's best
version (daily plan + 3-day volume lines) in one book: one trade at a time across everything, whichever signal
comes first (a sweep signal while another trade is open is skipped; at most 3 sweep trades a day).
1. Where the extra profit comes from: the sweep trades themselves, and the indicator trades they pushed out.
2. Small changes to the rule (stop distance, target, trades a day, last entry time, how far price must go beyond
   the level, stop limit) and whether it still helps in both halves.
3. With the volume-line ladder.
"""
import collections, itertools, sys
import y2026_smc as M, y2026_improve as I

Y, D26, H1, DAY, days, IDX, NM = M.Y, M.D26, M.H1, M.DAY, M.days, M.IDX, M.NM
one, five = M.one, M.five

def sweeps(d, buf=0.0002, target=3.0, last=870, depth=0.0, maxstop=0.005, mode='skip', levels='pd'):
    """Sweep trades of one day (every signal; the book picks)."""
    prev = days[IDX[d] - 1]; his, los = [DAY[prev][1]], [DAY[prev][2]]
    if levels == 'p2':
        p2 = days[IDX[d] - 2]; his.append(DAY[p2][1]); los.append(DAY[p2][2])
    b5 = five[d]; out = []
    for j in range(3, len(b5)):
        m0, o, h, l, c = b5[j]; pc = b5[j - 1][4]
        if m0 + 5 > last: break
        sig = None
        for x in his:
            if pc < x and h > x * (1 + depth) and c < x: sig = (-1, h); break
        if not sig:
            for x in los:
                if pc > x and l < x * (1 - depth) and c > x: sig = (1, l); break
        if not sig: continue
        side, ext = sig; e = c; stp = ext - side * buf * e; risk = side * (e - stp)
        if risk > maxstop * e:
            if mode == 'skip': continue
            stp, risk = e - side * maxstop * e, maxstop * e
        tgt = e + side * target * risk
        pnl, mx, why = M.walk(d, side, e, m0 + 5, stp, tgt, None, 915)
        out.append(dict(d=d, src='SWEEP', side=side, m=m0 + 5, mx=mx, pnl=pnl, why=why))
    return out

def combined(base, maxn=3, **kw):
    """The indicator's trades + every sweep signal, one trade at a time, at most maxn sweep trades a day."""
    cands = [t for d in D26 for t in sweeps(d, **kw)]
    return M.one_book(base, cands, maxn), M.book(cands, maxn)

def line(label, s, base=None):
    better = '' if base is None else ('  <- better in both halves' if s['a'] > base['a'] and s['b'] > base['b'] else '')
    return f"  {label:44} {M.fmt(s)}{better}"

if __name__ == '__main__':
    base = M.BASE_RAW; bs = M.stats(M.BASE)
    print(f"{NM.upper()} 2026. Indicator's best version (daily plan + 3-day volume lines): {M.fmt(bs)}")
    ts, new = combined(base)
    s = M.stats(ts); print(line('+ sweep of yesterday high / low', s, bs))
    sw = [t for t in ts if t['src'] == 'SWEEP']
    kept = {(t['d'], t['m'], t['src']) for t in ts}
    out = [t for t in M.BASE if (t['d'], t['m'], t['src']) not in kept]
    print(f"  1. sweep trades taken: {M.fmt(M.stats(sw))}")
    print(f"     sweep trades on their own (no indicator): {M.fmt(M.stats(new))}")
    print(f"     indicator trades pushed out by a sweep trade: {len(out)}, net {sum(t['pnl'] for t in out):+,.0f} "
          f"(plan {sum(t['pnl'] for t in out if t['src'] == 'plan'):+,.0f}, volume lines {sum(t['pnl'] for t in out if t['src'] == 'vol'):+,.0f})")
    print(f"     by exit: " + ', '.join(f"{k} {v}" for k, v in collections.Counter(t['why'] for t in sw).items()) +
          f"; SELLs {sum(t['side'] < 0 for t in sw)} net {sum(t['pnl'] for t in sw if t['side'] < 0):+,.0f}, "
          f"BUYs {sum(t['side'] > 0 for t in sw)} net {sum(t['pnl'] for t in sw if t['side'] > 0):+,.0f}")
    print("  2. small changes (everything else as above):")
    tried = better = 0
    for nm, kws in (('stop 0.02% beyond the candle (as above)', dict()), ('stop 0.05% beyond', dict(buf=0.0005)), ('stop 0.1% beyond', dict(buf=0.001)),
                    ('target 2x', dict(target=2.0)), ('target 4x', dict(target=4.0)), ('target 5x', dict(target=5.0)),
                    ('at most 1 a day', dict(maxn=1)), ('at most 2 a day', dict(maxn=2)), ('at most 5 a day', dict(maxn=5)),
                    ('last entry 12:00', dict(last=720)), ('last entry 1:30', dict(last=810)),
                    ('beyond the level by 0.03%+', dict(depth=0.0003)), ('beyond the level by 0.06%+', dict(depth=0.0006)),
                    ('stop at most 0.3% (skip wider)', dict(maxstop=0.003)), ('stop at most 0.3% (pull in)', dict(maxstop=0.003, mode='tighten')),
                    ('stop at most 0.2% (pull in)', dict(maxstop=0.002, mode='tighten')), ('also the day before\'s high / low', dict(levels='p2'))):
        s2 = M.stats(combined(base, **kws)[0]); tried += 1; better += s2['a'] > bs['a'] and s2['b'] > bs['b']
        print(line(nm, s2, bs))
    print(f"     {better} of {tried} versions better than the indicator alone in both halves")
    lad = [dict(d=t['d'], pnl=t['pnl'], m=t['m'], mx=t['mx'], src='plan' if t['src'] in ('MAG', 'BO') else 'vol')
           for t in [x for d in D26 for x in I.plan(d, 'edge', 1.0)] + [x for d in D26 for x in I.vol(d, 'ladder')]]
    ls = M.stats(M.one_book(lad, []))
    print(f"  3. with the volume-line ladder: indicator {M.fmt(ls)}")
    print(line('   + sweep of yesterday high / low', M.stats(combined(lad)[0]), ls))

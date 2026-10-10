"""2026 only: a reversal candle at the end of a move, a break of structure, then the retest of that candle with a
small stop (its low / high). On its own and added to the indicator's original rules (with and without the volume
check of y2026_volume.py).

    python y2026_pattern.py nifty        (or sensex; then: python y2026_pattern.py both)

BUY (the mirror image for SELL at tops), 5-minute candles:
 1. The end of a down move: the candle makes the lowest low of the last 12 candles; struct = trend: the structure is
    down (lower highs and lower lows: the last break of a swing point was downward, as in y2026_smc.py) / none.
 2. The candle: star = shooting-star shape (long upper wick, at least 60% of the candle, lower wick at most 15%;
    an inverted hammer at a low); hammer = long lower wick (the mirror image); doji = body at most 10% of the
    candle; engulf = a green candle whose body covers the previous red one; pin = star, hammer or doji; any = any
    candle. At least 0.02% of price from high to low.
 3. Break of structure: within the next hour, a 5-minute close above the last swing high before the candle (the
    last lower high), without a new low first.
 4. Entry: retest = a limit order back at the pattern candle's high, valid for an hour after the break (not after
    2:30); mid = at the middle of the candle; bos = at the break's close. Stop 0.02% below the candle's low.
 5. Target 2R / 3R (2x / 3x the stop), half (book half at 1R, stop to entry, rest at 3R), swing (the high of the
    move up to the break, at least 1x the stop). Out by 3:15.
FILTER: none / vol (the volume check: total volume of the up candles over the last 24 five-minute candles above the
  down candles' for a BUY, below for a SELL) / poc / cpr (as in y2026_smc.py). At most 1 / 3 a day, one at a time.
Costs 4 Nifty / 12 Sensex points. January-June and July-October separately.
"""
import collections, itertools, json, sys
import numpy as np

def fmt(s):
    return (f"{s['n']:4} tr {100 * s['w'] / max(1, s['n']):3.0f}% won net {s['net']:+7,.0f} ({s['net'] / max(1, s['n']):+5.1f}/tr; "
            f"Jan-Jun {s['a']:+6,.0f}, Jul-Oct {s['b']:+6,.0f}) fall {s['dd']:6,.0f}")

def label(P):
    return f"{P['pat']:6} {P['struct']:5} {P['entry']:6} {P['target']:5} filter {P['filt']:4} max {P['maxn']}"

def summary_both():
    R = {nm: {json.dumps(r['P'], sort_keys=True): r for r in json.load(open(f'../.cache/pattern_{nm}.json'))} for nm in ('nifty', 'sensex')}
    B = {nm: json.load(open(f'../.cache/pattern_base_{nm}.json')) for nm in R}
    keys = list(R['nifty']); good = lambda s: s['a'] > 0 and s['b'] > 0
    both = [k for k in keys if good(R['nifty'][k]['own']) and good(R['sensex'][k]['own'])]
    print(f"BOTH INDICES, 2026: {len(keys)} versions. On its own, made money in both halves on both indices: {len(both)}. Middle version: "
          f"Nifty {np.median([R['nifty'][k]['own']['net'] for k in keys]):+,.0f}, Sensex {np.median([R['sensex'][k]['own']['net'] for k in keys]):+,.0f}")
    for k in sorted(both, key=lambda k: -sum(R[nm][k]['own']['net'] / B[nm]['orig']['net'] for nm in R))[:10]:
        print(f"   {label(R['nifty'][k]['P'])}\n      Nifty  {fmt(R['nifty'][k]['own'])}\n      Sensex {fmt(R['sensex'][k]['own'])}")
    for mode, txt in (('orig', 'the original rules'), ('vchk', 'the original rules with the volume check')):
        better = [k for k in keys if all(R[nm][k][mode]['a'] > B[nm][mode]['a'] and R[nm][k][mode]['b'] > B[nm][mode]['b'] for nm in R)]
        print(f"\nADDED TO {txt.upper()} (" + ', '.join(f"{nm} {fmt(B[nm][mode])}" for nm in R) + f")\n  better in both halves on both indices: {len(better)}")
        for k in sorted(better, key=lambda k: -sum(R[nm][k][mode]['net'] / B[nm][mode]['net'] for nm in R))[:10]:
            print(f"   {label(R['nifty'][k]['P'])}\n      Nifty  {fmt(R['nifty'][k][mode])}\n      Sensex {fmt(R['sensex'][k][mode])}")

if __name__ == '__main__' and sys.argv[1:2] == ['both']:
    summary_both(); sys.exit()

import y2026_smc as M, y2026_volume as VV

Y, D26, NM, BUF = M.Y, M.D26, M.NM, M.BUF
Hh, Ll, O, Cc, PH, TREND, five = M.Hh, M.Ll, M.O, M.Cc, M.PH, M.TREND, M.five
PL = M.PL
VCHK = VV.check(dict(mode='sum', w=24, k=1.0))

def shape(i, side, pat):
    """Is candle i a reversal candle of kind pat for a move to `side` (+1: at a low, for a BUY)?"""
    h, l, o, c = Hh[i], Ll[i], O[i], Cc[i]; rng = h - l
    if rng < 0.0002 * c: return False
    up, lo, body = h - max(o, c), min(o, c) - l, abs(c - o)
    star, hammer, doji = up >= 0.6 * rng and lo <= 0.15 * rng, lo >= 0.6 * rng and up <= 0.15 * rng, body <= 0.1 * rng
    if pat == 'star': return star
    if pat == 'hammer': return hammer
    if pat == 'doji': return doji
    if pat == 'pin': return star or hammer or doji
    if pat == 'engulf':
        po, pc = O[i - 1], Cc[i - 1]
        return (c > o and pc < po and c >= po and o <= pc) if side > 0 else (c < o and pc > po and c <= po and o >= pc)
    return True

def day(d, P):
    i0, i1 = M.today(d); out = []
    for p in range(i0 + 1, i1):
        if five[d][p - i0][0] + 5 > 860: break
        for side in (1, -1):
            ext = Ll[p] if side > 0 else Hh[p]
            win = Ll[p - 11:p + 1] if side > 0 else Hh[p - 11:p + 1]
            if ext != (win.min() if side > 0 else win.max()): continue
            if P['struct'] == 'trend' and TREND[p - 1] != -side: continue
            if not shape(p, side, P['pat']): continue
            piv = [k for k in (PH if side > 0 else PL) if k + 2 <= p]
            if not piv: continue
            lv = Hh[piv[-1]] if side > 0 else Ll[piv[-1]]
            if side * (lv - (Hh[p] if side > 0 else Ll[p])) <= 0: continue
            b = None
            for k in range(p + 1, min(p + 13, i1)):
                if side * ((Ll[k] if side > 0 else Hh[k]) - ext) < 0: break          # a new low first: no
                if side * (Cc[k] - lv) > 0: b = k; break
            if b is None: continue
            mb = five[d][b - i0][0] + 5                                              # the break is known here
            if mb > 870: continue
            far = Hh[p:b + 1].max() if side > 0 else Ll[p:b + 1].min()
            e0 = Cc[b]
            if not M.passes(d, side, e0, P['filt'] if P['filt'] != 'vol' else 'none'): continue
            if P['filt'] == 'vol' and not VCHK(d, side, mb): continue
            stp = ext - side * BUF * e0
            if P['entry'] == 'bos':
                t = M.make(d, 'PAT', side, e0, mb, stp, far, P)
            else:
                px = (Hh[p] if side > 0 else Ll[p]) if P['entry'] == 'retest' else (Hh[p] + Ll[p]) / 2
                t = M.limit_trade(d, 'PAT', side, px, stp, mb, min(mb + 59, 870), far, P)
            if t: out.append(t)
    return out

def make_target(P):
    return dict(P, target={'swing': 'lvl'}.get(P['target'], P['target']))

GRID = [dict(pat=pa, struct=st, entry=en, target=tg, filt=f, maxn=mn) for pa, st, en, tg, f, mn in
        itertools.product(('star', 'hammer', 'doji', 'engulf', 'pin', 'any'), ('trend', 'none'), ('retest', 'mid', 'bos'),
                          ('2R', '3R', 'half', 'swing'), ('none', 'vol', 'poc', 'cpr'), (1, 3))]

def base_raw(vf):
    """Every signal of the original rules (with the volume check if vf), as the alert program finds them."""
    out = []
    VV.A.SWEEP = False
    for d in D26:
        cx = VV.CX[d]; cx['vf'] = (lambda side, m, src, d=d: vf(d, side, m)) if vf else None
        for t in VV.A.day_trades(cx, Y.one[d], 929, True, False, 'classic'):
            out.append(dict(d=d, m=t['m'], mx=t['exit']['m'], pnl=t['exit']['pnl'], src='vol' if t['src'] == 'VOLUME LINE' else 'plan'))
        cx['vf'] = None
    return out
BASES = {'orig': base_raw(None), 'vchk': base_raw(VCHK)}

def run(P):
    cands = [t for d in D26 for t in day(d, make_target(P))]
    own = M.book(cands, P['maxn'])
    return dict(P=P, own=M.stats(own), **{k: M.stats(M.one_book(b, cands, P['maxn'])) for k, b in BASES.items()})

if __name__ == '__main__':
    import multiprocessing as mp
    with mp.Pool() as pool: res = pool.map(run, GRID, chunksize=8)
    base = {k: M.stats(M.one_book(b, [])) for k, b in BASES.items()}
    json.dump(res, open(f'../.cache/pattern_{NM}.json', 'w')); json.dump(base, open(f'../.cache/pattern_base_{NM}.json', 'w'))
    print(f"{NM.upper()} 2026: original rules {fmt(base['orig'])}\n             with the volume check {fmt(base['vchk'])}")
    print(f"{len(res)} versions; on its own made money {sum(r['own']['net'] > 0 for r in res)}, in both halves "
          f"{sum(r['own']['a'] > 0 and r['own']['b'] > 0 for r in res)}; middle version {np.median([r['own']['net'] for r in res]):+,.0f}")
    for k in ('pat', 'struct', 'entry', 'target', 'filt', 'maxn'):
        g = collections.defaultdict(list)
        for r in res: g[r['P'][k]].append(r['own']['net'])
        print(f"   by {k:6}: " + ' | '.join(f"{v}: middle {np.median(x):+,.0f}, made money {sum(y > 0 for y in x)}/{len(x)}" for v, x in g.items()))
    print(" best 10 on its own (both halves positive):")
    for r in sorted([r for r in res if r['own']['a'] > 0 and r['own']['b'] > 0], key=lambda r: -r['own']['net'])[:10]:
        print(f"   {label(r['P']):46} {fmt(r['own'])}")
    for mode in ('orig', 'vchk'):
        better = [r for r in res if r[mode]['a'] > base[mode]['a'] and r[mode]['b'] > base[mode]['b']]
        print(f" added to the {'original rules' if mode == 'orig' else 'original rules with the volume check'}: better in both halves {len(better)}")
        for r in sorted(better, key=lambda r: -r[mode]['net'])[:6]:
            print(f"   {label(r['P']):46} {fmt(r[mode])}")

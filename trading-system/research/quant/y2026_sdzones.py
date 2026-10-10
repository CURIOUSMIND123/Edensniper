"""2026 only: reversal candle patterns at supply and demand zones, with a break of structure and the retest. On their
own and added to the indicator (original rules with the volume check, the default; and without it).

    python y2026_sdzones.py nifty        (or sensex; then: python y2026_sdzones.py both)

ZONES, from 15-minute or 60-minute candles (the last 5 sessions and today so far, known once formed):
  a base of 1-3 small candles (body at most half the candle) followed by a strong candle away from it (body at least
  1.5x the average body of the last 20 candles and 60% of its own range, closing beyond the base).
  DEMAND (strong candle up): from the base's low to the top of its bodies. SUPPLY (strong candle down): from the
  bottom of its bodies to its high. A zone ends when a 5-minute candle closes through its far side.
  fresh = only the first time price comes back into the zone; any = every time.
PATTERNS on 5-minute candles, with their low inside a demand zone (BUY) / their high inside a supply zone (SELL):
  mstar   morning star (big red candle, small candle, green candle closing above the middle of the red body) /
          evening star
  engulf  bullish / bearish engulfing
  pierce  piercing line / dark cloud cover
  harami  bullish / bearish harami (a small candle inside the previous big body)
  tweezer tweezer bottom / top (two lows / highs within 0.02%, red then green / green then red)
  hammer  hammer at demand / hanging man at supply (long lower wick)
  star    inverted hammer at demand / shooting star at supply (long upper wick)
  all     any of these
ENTRY: close = at the pattern's close; bos = at the 5-minute close beyond the last swing high / low before the
  pattern (break of structure, within an hour, no new low / high first); retest = after the break, a limit order back
  at the pattern's high / low (valid an hour). Stop 0.02% beyond the pattern's low / high (skipped if wider than
  0.5% of price).
TARGET: 2R / 3R, half (half at 1R, stop to entry, rest at 3R), opp (the nearest opposite zone, at least 1x the stop).
FILTER: none / vol (the volume check of y2026_volume.py at the entry decision). Entries 9:30-2:30, out by 3:15, one
at a time, at most 3 a day. Costs 4 Nifty / 12 Sensex points.
"""
import collections, itertools, json, sys
import numpy as np

def fmt(s):
    return (f"{s['n']:4} tr {100 * s['w'] / max(1, s['n']):3.0f}% won net {s['net']:+7,.0f} ({s['net'] / max(1, s['n']):+5.1f}/tr; "
            f"Jan-Jun {s['a']:+6,.0f}, Jul-Oct {s['b']:+6,.0f}) fall {s['dd']:6,.0f}")

def label(P):
    return f"{P['pat']:7} {P['tf']}m {P['fresh']:5} {P['entry']:6} {P['target']:4} filter {P['filt']}"

def summary_both():
    R = {nm: {json.dumps(r['P'], sort_keys=True): r for r in json.load(open(f'../.cache/sdz_{nm}.json'))} for nm in ('nifty', 'sensex')}
    B = {nm: json.load(open(f'../.cache/sdz_base_{nm}.json')) for nm in R}
    keys = list(R['nifty']); good = lambda s: s['a'] > 0 and s['b'] > 0
    both = [k for k in keys if good(R['nifty'][k]['own']) and good(R['sensex'][k]['own'])]
    print(f"BOTH INDICES, 2026: {len(keys)} versions. On its own, made money in both halves on both indices: {len(both)}. Middle version: "
          f"Nifty {np.median([R['nifty'][k]['own']['net'] for k in keys]):+,.0f}, Sensex {np.median([R['sensex'][k]['own']['net'] for k in keys]):+,.0f}")
    for pat in ('mstar', 'engulf', 'pierce', 'harami', 'tweezer', 'hammer', 'star', 'all'):
        ks = [k for k in keys if R['nifty'][k]['P']['pat'] == pat]
        print(f"   {pat:8} made money on its own: Nifty {sum(R['nifty'][k]['own']['net'] > 0 for k in ks)}/{len(ks)}, Sensex "
              f"{sum(R['sensex'][k]['own']['net'] > 0 for k in ks)}/{len(ks)}; both halves both indices {sum(k in both for k in ks)}")
    for k in sorted(both, key=lambda k: -sum(R[nm][k]['own']['net'] / B[nm]['vchk']['net'] for nm in R))[:8]:
        print(f"   {label(R['nifty'][k]['P'])}\n      Nifty  {fmt(R['nifty'][k]['own'])}\n      Sensex {fmt(R['sensex'][k]['own'])}")
    for mode, txt in (('vchk', 'the default (original rules + volume check)'), ('orig', 'the original rules without the volume check')):
        better = [k for k in keys if all(R[nm][k][mode]['a'] > B[nm][mode]['a'] and R[nm][k][mode]['b'] > B[nm][mode]['b'] for nm in R)]
        print(f"\nADDED TO {txt.upper()}\n  (" + ', '.join(f"{nm} {fmt(B[nm][mode])}" for nm in R) + f")\n  better in both halves on both indices: {len(better)}")
        for k in sorted(better, key=lambda k: -sum(R[nm][k][mode]['net'] / B[nm][mode]['net'] for nm in R))[:8]:
            print(f"   {label(R['nifty'][k]['P'])}\n      Nifty  {fmt(R['nifty'][k][mode])}\n      Sensex {fmt(R['sensex'][k][mode])}")

if __name__ == '__main__' and sys.argv[1:2] == ['both']:
    summary_both(); sys.exit()

import y2026_pattern as PT
M, Y, VV = PT.M, PT.Y, PT.VV
D26, NM, BUF, five, days, IDX = M.D26, M.NM, M.BUF, M.five, M.days, M.IDX
Hh, Ll, O, Cc, PH, PL, POS, SEQ = M.Hh, M.Ll, M.O, M.Cc, M.PH, M.PL, M.POS, M.SEQ
VCHK, BASES = PT.VCHK, PT.BASES

# ---------------- supply and demand zones ----------------
def zones(n):
    """Zones from n x 5-minute candles (3 = 15 minutes, 12 = 60 minutes): (side, lo, hi, created at 5-minute index,
    ended at 5-minute index, day index)."""
    big = []
    for d in days[IDX[D26[0]] - 7:]:
        if (d, 0) not in POS: continue
        b5 = five[d]
        for k in range(0, len(b5), n):
            ch = b5[k:k + n]
            big.append((POS[(d, k + len(ch) - 1)], ch[0][1], max(x[2] for x in ch), min(x[3] for x in ch), ch[-1][4], IDX[d]))
    out = []
    for i in range(20, len(big)):
        g, o, h, l, c, di = big[i]
        avg = np.mean([abs(x[4] - x[1]) for x in big[i - 20:i]])
        body = abs(c - o)
        if body < 1.5 * avg or body < 0.6 * (h - l): continue
        base = []
        for j in range(i - 1, max(i - 4, -1), -1):
            x = big[j]
            if abs(x[4] - x[1]) <= 0.5 * (x[2] - x[3]) and x[2] > x[3]: base.append(x)
            else: break
        if not base: continue
        side = 1 if c > o else -1
        bh, bl = max(x[2] for x in base), min(x[3] for x in base)
        if side > 0 and c > bh: lo, hi = bl, max(max(x[1], x[4]) for x in base)
        elif side < 0 and c < bl: lo, hi = min(min(x[1], x[4]) for x in base), bh
        else: continue
        end = next((t for t in range(g + 1, len(SEQ)) if (Cc[t] < lo if side > 0 else Cc[t] > hi)), len(SEQ))
        out.append((side, lo, hi, g, end, di))
    return out
ZONES = {tf: zones(n) for tf, n in ((15, 3), (60, 12))}

def live_zones(tf, side, t):
    """Zones of `side` that are known and still standing at 5-minute candle t, from the last 5 sessions."""
    di = IDX[SEQ[t][0]]
    return [z for z in ZONES[tf] if z[0] == side and z[3] < t and z[4] >= t and z[5] >= di - 5]

# ---------------- patterns ----------------
def pattern(p, side, kind):
    """First candle of the pattern ending at candle p, or None."""
    o, h, l, c = O, Hh, Ll, Cc
    rng = lambda i: h[i] - l[i]
    body = lambda i: abs(c[i] - o[i])
    red = lambda i: c[i] < o[i] if side > 0 else c[i] > o[i]          # against the coming move
    grn = lambda i: c[i] > o[i] if side > 0 else c[i] < o[i]          # with it
    found = []
    if kind in ('engulf', 'all') and red(p - 1) and grn(p) and side * (c[p] - o[p - 1]) >= 0 and side * (c[p - 1] - o[p]) >= 0:
        found.append(p - 1)
    if kind in ('mstar', 'all') and red(p - 2) and body(p - 2) >= 0.5 * rng(p - 2) > 0 and body(p - 1) <= 0.3 * body(p - 2) \
            and grn(p) and side * (c[p] - (o[p - 2] + c[p - 2]) / 2) > 0:
        found.append(p - 2)
    if kind in ('pierce', 'all') and red(p - 1) and body(p - 1) >= 0.5 * rng(p - 1) > 0 and grn(p) and side * (c[p - 1] - o[p]) >= 0 \
            and side * (c[p] - (o[p - 1] + c[p - 1]) / 2) > 0 and side * (o[p - 1] - c[p]) > 0:
        found.append(p - 1)
    if kind in ('harami', 'all') and red(p - 1) and body(p - 1) >= 0.5 * rng(p - 1) > 0 and grn(p) and body(p) <= 0.5 * body(p - 1) \
            and min(o[p], c[p]) >= min(o[p - 1], c[p - 1]) and max(o[p], c[p]) <= max(o[p - 1], c[p - 1]):
        found.append(p - 1)
    if kind in ('tweezer', 'all') and red(p - 1) and grn(p) and \
            abs((l[p] - l[p - 1]) if side > 0 else (h[p] - h[p - 1])) <= 0.0002 * c[p]:
        found.append(p - 1)
    if kind in ('hammer', 'star', 'all') and rng(p) >= 0.0002 * c[p]:
        up, lo = h[p] - max(o[p], c[p]), min(o[p], c[p]) - l[p]
        if kind in ('hammer', 'all') and lo >= 0.6 * rng(p) and up <= 0.15 * rng(p): found.append(p)
        if kind in ('star', 'all') and up >= 0.6 * rng(p) and lo <= 0.15 * rng(p): found.append(p)
    return min(found) if found else None

def day(d, P):
    i0, i1 = M.today(d); out = []; tf = P['tf']
    for p in range(i0 + 2, i1):
        mp = five[d][p - i0][0] + 5
        if mp < 570: continue
        if mp > 870: break
        for side in (1, -1):
            s0 = pattern(p, side, P['pat'])
            if s0 is None or s0 < i0: continue
            ext = Ll[s0:p + 1].min() if side > 0 else Hh[s0:p + 1].max()
            zs = live_zones(tf, side, s0)
            hit = None
            for z in zs:
                _, lo, hi, g, end, _ = z
                inside = (lo * (1 - 0.0005) <= ext <= hi) if side > 0 else (lo <= ext <= hi * (1 + 0.0005))
                if not inside or (Cc[p] < lo if side > 0 else Cc[p] > hi): continue
                if P['fresh'] == 'fresh':
                    first = next((t for t in range(g + 1, p + 1) if (Ll[t] <= hi if side > 0 else Hh[t] >= lo)), None)
                    if first is None or first < s0: continue
                hit = z; break
            if hit is None: continue
            opp = [z for z in live_zones(tf, -side, p)]
            stp_ext = ext
            if P['entry'] == 'close':
                e, mb, b = Cc[p], mp, p
            else:
                piv = [k for k in (PH if side > 0 else PL) if k + 2 <= p]
                if not piv: continue
                lv = Hh[piv[-1]] if side > 0 else Ll[piv[-1]]
                b = p if side * (Cc[p] - lv) > 0 else None
                if b is None:
                    for k in range(p + 1, min(p + 13, i1)):
                        if side * ((Ll[k] if side > 0 else Hh[k]) - ext) < 0: break
                        if side * (Cc[k] - lv) > 0: b = k; break
                if b is None: continue
                mb = five[d][b - i0][0] + 5
                if mb > 870: continue
                e = Cc[b]
            if P['filt'] == 'vol' and not VCHK(d, side, mb): continue
            tgt = None
            if P['target'] == 'opp':
                cands = [(z[1] if side > 0 else z[2]) for z in opp]
                tgt = M.nearest(cands, side, e)
            Pm = dict(P, target='lvl' if P['target'] == 'opp' else P['target'])
            stp = stp_ext - side * BUF * e
            if P['entry'] == 'retest':
                px = Hh[p] if side > 0 else Ll[p]
                t = M.limit_trade(d, 'SDZ', side, px, stp, mb, min(mb + 59, 870), tgt, Pm)
            else:
                t = M.make(d, 'SDZ', side, e, mb, stp, tgt, Pm)
            if t: out.append(t)
    return out

GRID = [dict(pat=pa, tf=tf, fresh=fr, entry=en, target=tg, filt=f) for pa, tf, fr, en, tg, f in
        itertools.product(('mstar', 'engulf', 'pierce', 'harami', 'tweezer', 'hammer', 'star', 'all'), (15, 60), ('fresh', 'any'),
                          ('close', 'bos', 'retest'), ('2R', '3R', 'half', 'opp'), ('none', 'vol'))]

def run(P):
    cands = [t for d in D26 for t in day(d, P)]
    own = M.book(cands, 3)
    return dict(P=P, own=M.stats(own), **{k: M.stats(M.one_book(b, cands, 3)) for k, b in BASES.items()})

if __name__ == '__main__':
    print(f"{NM.upper()}: zones 15m {len(ZONES[15])}, 60m {len(ZONES[60])}", flush=True)
    import multiprocessing as mp
    with mp.Pool() as pool: res = pool.map(run, GRID, chunksize=8)
    base = {k: M.stats(M.one_book(b, [])) for k, b in BASES.items()}
    json.dump(res, open(f'../.cache/sdz_{NM}.json', 'w')); json.dump(base, open(f'../.cache/sdz_base_{NM}.json', 'w'))
    print(f"{NM.upper()} 2026: default (volume check) {fmt(base['vchk'])}\n             original              {fmt(base['orig'])}")
    print(f"{len(res)} versions; on its own made money {sum(r['own']['net'] > 0 for r in res)}, in both halves "
          f"{sum(r['own']['a'] > 0 and r['own']['b'] > 0 for r in res)}; middle version {np.median([r['own']['net'] for r in res]):+,.0f}")
    for k in ('pat', 'tf', 'fresh', 'entry', 'target', 'filt'):
        g = collections.defaultdict(list)
        for r in res: g[r['P'][k]].append(r['own']['net'])
        print(f"   by {k:6}: " + ' | '.join(f"{v}: middle {np.median(x):+,.0f}, made money {sum(y > 0 for y in x)}/{len(x)}" for v, x in g.items()))
    print(" best 10 on its own (both halves positive):")
    for r in sorted([r for r in res if r['own']['a'] > 0 and r['own']['b'] > 0], key=lambda r: -r['own']['net'])[:10]:
        print(f"   {label(r['P']):44} {fmt(r['own'])}")
    for mode in ('vchk', 'orig'):
        better = [r for r in res if r[mode]['a'] > base[mode]['a'] and r[mode]['b'] > base[mode]['b']]
        print(f" added to the {'default (volume check)' if mode == 'vchk' else 'original rules'}: better in both halves {len(better)}")
        for r in sorted(better, key=lambda r: -r[mode]['net'])[:6]:
            print(f"   {label(r['P']):44} {fmt(r[mode])}")

"""2026 only: liquidity sweeps, the squeeze, Smart Money Concepts (break of structure, change of character, order
blocks, fair value gaps) and the low-volume areas of the last 2 sessions' volume profile: on their own, and added to
the indicator's best version (daily plan + 3-day volume lines, the original rules).

    python y2026_smc.py nifty        (or sensex; then: python y2026_smc.py both)

SETUPS (5-minute candles; entries 9:30-2:30; exits on 1-minute candles; out by 3:15; costs 4 Nifty / 12 Sensex):
 SWEEP  liquidity sweep (stop hunt): a 5-minute candle trades above a liquidity level and closes back below it (the
        candle before closed below it) -> SELL; the mirror image at a low -> BUY. Stop just beyond the candle's high /
        low. Liquidity levels: pd = yesterday's high / low; p2 = also the day before's; swing = pd + today's 5-minute
        swing highs / lows; or = pd + the 9:15-9:30 high / low.
        confirm: close = enter at the sweep candle's close; choch = wait (30 minutes at most) for a 5-minute close
        beyond the last swing point the other way (change of character), enter there, stop beyond the sweep.
 SQZ    the squeeze: Bollinger Bands (20, 2) inside the Keltner Channel (20, 1.5 ATR) for at least 3 / 6 candles in a
        row today; a 5-minute close beyond the squeeze's high / low -> that way. Stop at the other side of the
        squeeze box, or its middle.
 SMC    swing points: a 5-minute high / low with 2 lower highs / higher lows on each side.
        bos   = a 5-minute close beyond the last swing high / low in the direction of the structure -> that way,
                stop beyond the low / high the move started from
        choch = the first close beyond a swing point against the structure -> the new way, same stop
        ob    = after either break, a limit order at the order block (the last candle against the move before the
                break), stop beyond the block; valid 60 minutes
        fvg   = a fair value gap (the 3rd candle's low above the 1st candle's high, or the mirror image; at least
                0.03% of price): a limit order at the middle of the gap, stop beyond the 1st candle, valid 60
                minutes; fvg+ = only gaps in the direction of the structure
 LVN    low-volume areas of the last 2 sessions' volume profile (fixed range, NIFTYBEES volume as in y2026.py): price
        bins with volume in the lowest 20 / 35% of the range (smoothed over 3 bins), at least 2 bins wide, with
        heavier volume on both sides.
        brk = a 5-minute close into the area from outside -> that way (thin areas are crossed fast); target the
              first high-volume peak beyond the area; stop beyond the candle
        rev = a candle pokes into the area and closes back out -> the other way (rejected); target the nearest
              high-volume peak behind; stop beyond the candle
TARGETS: 2R / 3R (2x / 3x the stop), half (book half at 1R, stop to entry, rest at 3R or 3:15), lvl (SWEEP: the next
  liquidity level the other way, or today's low / high; LVN: as above; at least 1x the stop away, else no trade).
  Stops wider than 0.5% of price are skipped. Stops are 0.02% beyond the candle / block / gap.
FILTERS: none / poc (buys only above the 30-day POC, sells only below, as the indicator) / cpr (buys only above the
  CPR, sells only below).
TRADES PER DAY: one at a time per setup, at most 1 / 3 a day.
Then every version is added to the indicator's best version (daily plan + 3-day volume lines, Nifty +2,274 / Sensex
+8,102): in one book (one trade at a time across everything, whichever signal comes first, the indicator's own first
in the same minute; at most 1 / 3 new trades a day) and as a second position open at the same time (more trades).
"""
import collections, itertools, json, sys
import numpy as np

FAMS = ('SWEEP', 'SQZ', 'SMC', 'LVN')

def label(P):
    keys = [k for k in P if k not in ('fam', 'target', 'maxn', 'filt')]
    return f"{P['fam']:5} " + ' '.join(f"{P[k]}" for k in keys) + f" | filter {P['filt']} | {P['target']} | max {P['maxn']}/day"

def fmt(s):
    return (f"{s['n']:4} tr {100 * s['w'] / max(1, s['n']):3.0f}% won net {s['net']:+7,.0f} (Jan-Jun {s['a']:+6,.0f}, Jul-Oct {s['b']:+6,.0f}) "
            f"fall {s['dd']:6,.0f}")

def summary_both():
    R = {nm: {json.dumps(r['P'], sort_keys=True): r for r in json.load(open(f'../.cache/smc_{nm}.json'))} for nm in ('nifty', 'sensex')}
    base = {nm: json.load(open(f'../.cache/smc_base_{nm}.json')) for nm in R}
    keys = list(R['nifty'])
    good = lambda s: s['a'] > 0 and s['b'] > 0
    print("BOTH INDICES, 2026. Indicator's best version: " + ', '.join(f"{nm} {fmt(base[nm])}" for nm in base))
    for fam in FAMS:
        ks = [k for k in keys if R['nifty'][k]['P']['fam'] == fam]
        both = [k for k in ks if good(R['nifty'][k]['own']) and good(R['sensex'][k]['own'])]
        print(f"\n{fam}: {len(ks)} versions. On its own, made money in both halves on both indices: {len(both)}. "
              f"Middle version: Nifty {np.median([R['nifty'][k]['own']['net'] for k in ks]):+,.0f}, "
              f"Sensex {np.median([R['sensex'][k]['own']['net'] for k in ks]):+,.0f}")
        for k in sorted(both, key=lambda k: -(R['nifty'][k]['own']['net'] / base['nifty']['net'] + R['sensex'][k]['own']['net'] / base['sensex']['net']))[:6]:
            print(f"   {label(R['nifty'][k]['P'])}\n      Nifty  {fmt(R['nifty'][k]['own'])}\n      Sensex {fmt(R['sensex'][k]['own'])}")
    for mode, txt in (('one', 'one trade at a time'), ('sep', 'as a second position')):
        better = [k for k in keys if all(R[nm][k][mode]['a'] > base[nm]['a'] and R[nm][k][mode]['b'] > base[nm]['b'] for nm in R)]
        print(f"\nADDED TO THE INDICATOR ({txt}): better in both halves on both indices: {len(better)} of {len(keys)}")
        for k in sorted(better, key=lambda k: -sum(R[nm][k][mode]['net'] / base[nm]['net'] for nm in R))[:10]:
            print(f"   {label(R['nifty'][k]['P'])}\n      Nifty  {fmt(R['nifty'][k][mode])}\n      Sensex {fmt(R['sensex'][k][mode])}")

if __name__ == '__main__' and sys.argv[1:2] == ['both']:
    summary_both(); sys.exit()

import y2026 as Y, y2026_combo as K, y2026_short as S

one, five, LV, DAY, COST, D26, H1, NM, BIN = Y.one, Y.five, Y.LV, Y.DAY, Y.COST, Y.D26, Y.H1, Y.B.name, Y.BIN
days, IDX = Y.days, Y.IDX
walk = S.walk
MAXSTOP, BUF = 0.005, 0.0002

# ---------------- 5-minute candles across days (indicators carry over from one day to the next) ----------------
SEQ = [(d, j) for d in days[IDX[D26[0]] - 5:] for j in range(len(five[d]))]
POS = {k: i for i, k in enumerate(SEQ)}
O, Hh, Ll, Cc = (np.array([five[d][j][k] for d, j in SEQ]) for k in (1, 2, 3, 4))
N = len(SEQ)

# squeeze: Bollinger (20, 2) inside Keltner (20, 1.5 x ATR 20)  <=>  2 x stdev < 1.5 x ATR
TR = np.maximum(Hh - Ll, np.maximum(np.abs(Hh - np.roll(Cc, 1)), np.abs(Ll - np.roll(Cc, 1)))); TR[0] = Hh[0] - Ll[0]
SQ = np.zeros(N, bool)
for i in range(19, N):
    SQ[i] = 2 * Cc[i - 19:i + 1].std() < 1.5 * TR[i - 19:i + 1].mean()

# swing points (2 candles each side), known 2 candles later
PH = [i for i in range(2, N - 2) if Hh[i] > Hh[i - 2:i].max() and Hh[i] >= Hh[i + 1:i + 3].max()]
PL = [i for i in range(2, N - 2) if Ll[i] < Ll[i - 2:i].min() and Ll[i] <= Ll[i + 1:i + 3].min()]
SH_AT = collections.defaultdict(list); SL_AT = collections.defaultdict(list)     # confirmed at candle i + 2
for i in PH: SH_AT[i + 2].append(i)
for i in PL: SL_AT[i + 2].append(i)

# structure: breaks of the last swing high / low at a 5-minute close
EV = collections.defaultdict(list)      # candle index -> breaks at its close
TREND = np.zeros(N, int)
sh = sl = None; trend = 0
for t in range(N):
    if sh is not None and Cc[t] > Hh[sh]:
        a = int(np.argmin(Ll[sh:t + 1])) + sh                        # where the up-move started
        ob = max([k for k in range(a, t) if Cc[k] < O[k]] or [a])   # last down candle before the break
        EV[t].append(dict(side=1, kind='bos' if trend == 1 else 'choch', ext=Ll[a], ob=ob)); trend = 1; sh = None
    elif sl is not None and Cc[t] < Ll[sl]:
        a = int(np.argmax(Hh[sl:t + 1])) + sl
        ob = max([k for k in range(a, t) if Cc[k] > O[k]] or [a])
        EV[t].append(dict(side=-1, kind='bos' if trend == -1 else 'choch', ext=Hh[a], ob=ob)); trend = -1; sl = None
    for i in SH_AT.get(t, []): sh = i
    for i in SL_AT.get(t, []): sl = i
    TREND[t] = trend

# ---------------- low-volume areas of the last 2 sessions' volume profile ----------------
def lvn(d, q):
    ds = days[IDX[d] - 2:IDX[d]]
    base = min(Y.VH[x][0] for x in ds); top = max(Y.VH[x][0] + len(Y.VH[x][1]) for x in ds)
    p = np.zeros(top - base)
    for x in ds: b0, h = Y.VH[x]; p[b0 - base:b0 - base + len(h)] += h
    sm = np.convolve(p, np.ones(3) / 3, 'same')
    nz = np.nonzero(p)[0]; a0, a1 = nz[0], nz[-1]
    rng = sm[a0:a1 + 1]; thr = np.percentile(rng, q); med = np.median(rng)
    zones, k = [], a0
    while k <= a1:
        if sm[k] < thr:
            e = k
            while e + 1 <= a1 and sm[e + 1] < thr: e += 1
            if e - k + 1 >= 2 and (sm[a0:k] >= med).any() and (sm[e + 1:a1 + 1] >= med).any():
                zones.append(((base + k) * BIN, (base + e + 1) * BIN))
            k = e + 1
        else: k += 1
    pthr = np.percentile(rng, 70)
    peaks = [(base + i + 0.5) * BIN for i in range(a0 + 1, a1) if sm[i] >= pthr and sm[i] >= sm[i - 1] and sm[i] >= sm[i + 1]]
    return zones, peaks
LVZ = {(d, q): lvn(d, q) for d in D26 for q in (20, 35)}

# ---------------- trades ----------------
def make(d, src, side, e, start, stp, tgt, P, m=None):
    """Stop, target rule, exits on 1-minute candles -> trade dict or None (stop too wide / target too close)."""
    risk = side * (e - stp)
    if risk <= 0 or risk > MAXSTOP * e: return None
    half = None
    if P['target'] == 'lvl':
        if tgt is None or side * (tgt - e) < risk: return None
    elif P['target'] == 'half':
        half, tgt = e + side * risk, e + side * 3 * risk
    else:
        tgt = e + side * float(P['target'][:-1]) * risk
    pnl, mx, why = walk(d, side, e, start, stp, tgt, half, 915)
    return dict(d=d, src=src, side=side, m=start if m is None else m, mx=mx, pnl=pnl, why=why)

def limit_fill(d, side, px, stp, after, until):
    """First 1-minute candle from `after` to `until` that trades at px: (minute, fill price, stopped in that minute)."""
    for m, o, h, l, c in one[d]:
        if m < after: continue
        if m > until: return None
        if (l <= px) if side > 0 else (h >= px):
            e = min(o, px) if side > 0 else max(o, px)
            return m, e, ((l <= stp) if side > 0 else (h >= stp))
    return None

def limit_trade(d, src, side, px, stp, after, until, tgt, P):
    f = limit_fill(d, side, px, stp, after, until)
    if not f: return None
    m, e, hit = f
    risk = side * (e - stp)
    if risk <= 0 or risk > MAXSTOP * e: return None
    if hit:                                                    # filled and stopped inside the same minute
        return dict(d=d, src=src, side=side, m=m, mx=m, pnl=-risk - COST, why='stop')
    return make(d, src, side, e, m + 1, stp, tgt, P, m=m)

def passes(d, side, e, filt):
    if filt == 'poc': return side * (e - Y.PROF30[d]['poc']) > 0
    if filt == 'cpr': return e > LV[d]['top'] if side > 0 else e < LV[d]['bot']
    return True

def today(d):
    i0 = POS[(d, 0)]
    return i0, i0 + len(five[d])
DPH = {d: [k for k in PH if today(d)[0] <= k < today(d)[1]] for d in D26}
DPL = {d: [k for k in PL if today(d)[0] <= k < today(d)[1]] for d in D26}

def nearest(xs, side, e):
    xs = [x for x in xs if side * (x - e) > 0]
    return min(xs, key=lambda x: abs(x - e)) if xs else None

def sweep(d, P):
    i0, i1 = today(d); prev, prev2 = days[IDX[d] - 1], days[IDX[d] - 2]
    hi0, lo0 = [DAY[prev][1]], [DAY[prev][2]]
    if P['levels'] == 'p2': hi0.append(DAY[prev2][1]); lo0.append(DAY[prev2][2])
    if P['levels'] == 'or':
        hi0.append(Hh[i0:i0 + 3].max()); lo0.append(Ll[i0:i0 + 3].min())
    out = []
    for i in range(i0 + 3, i1):
        m0 = five[d][i - i0][0]
        if m0 + 5 > 870: break
        his, los = list(hi0), list(lo0)
        if P['levels'] == 'swing':
            his += [Hh[k] for k in DPH[d] if k + 2 <= i - 1]; los += [Ll[k] for k in DPL[d] if k + 2 <= i - 1]
        pc, c = Cc[i - 1], Cc[i]
        sig = None
        for x in his:
            if pc < x < Hh[i] and c < x: sig = (-1, Hh[i]); break
        if not sig:
            for x in los:
                if pc > x > Ll[i] and c > x: sig = (1, Ll[i]); break
        if not sig: continue
        side, ext = sig
        k = i
        if P['confirm'] == 'choch':
            k = next((t for t in range(i + 1, min(i + 7, i1)) if any(ev['side'] == side for ev in EV[t]) and five[d][t - i0][0] + 5 <= 870), None)
            if k is None: continue
            ext = Hh[i:k + 1].max() if side < 0 else Ll[i:k + 1].min()
        e = Cc[k]
        if not passes(d, side, e, P['filt']): continue
        dlo, dhi = Ll[i0:k + 1].min(), Hh[i0:k + 1].max()
        tgt = nearest((lo0 + [dlo]) if side < 0 else (hi0 + [dhi]), side, e)
        t = make(d, 'SWEEP', side, e, five[d][k - i0][0] + 5, ext - side * BUF * e, tgt, P)
        if t: out.append(t)
    return out

def squeeze(d, P):
    i0, i1 = today(d); out = []
    for i in range(i0 + 3, i1):
        m0 = five[d][i - i0][0]
        if m0 + 5 > 870: break
        k = i - 1; run = 0
        while k >= i0 and SQ[k]: run += 1; k -= 1
        if run < P['nb']: continue
        bh, bl = Hh[k + 1:i].max(), Ll[k + 1:i].min()
        side = 1 if Cc[i] > bh else -1 if Cc[i] < bl else 0
        if not side: continue
        e = Cc[i]
        if not passes(d, side, e, P['filt']): continue
        stp = ((bl if side > 0 else bh) - side * BUF * e) if P['stop'] == 'box' else (bh + bl) / 2
        t = make(d, 'SQZ', side, e, m0 + 5, stp, None, P)
        if t: out.append(t)
    return out

def smc(d, P):
    i0, i1 = today(d); out = []; kind = P['kind']
    for i in range(i0 + 3, i1):
        m0 = five[d][i - i0][0]
        if m0 + 5 > 870: break
        if kind in ('bos', 'choch', 'ob'):
            for ev in EV[i]:
                if kind != 'ob' and ev['kind'] != kind: continue
                side = ev['side']
                if kind == 'ob':
                    b = ev['ob']
                    if b < i0: continue
                    px = Hh[b] if side > 0 else Ll[b]; stp = (Ll[b] if side > 0 else Hh[b]) - side * BUF * px
                    if not passes(d, side, px, P['filt']): continue
                    t = limit_trade(d, 'OB', side, px, stp, m0 + 5, min(m0 + 64, 869), None, P)
                else:
                    e = Cc[i]
                    if not passes(d, side, e, P['filt']): continue
                    t = make(d, kind.upper(), side, e, m0 + 5, ev['ext'] - side * BUF * e, None, P)
                if t: out.append(t)
        else:
            if i - 2 < i0: continue
            side = 1 if Ll[i] - Hh[i - 2] >= 0.0003 * Cc[i] else -1 if Ll[i - 2] - Hh[i] >= 0.0003 * Cc[i] else 0
            if not side or (kind == 'fvg+' and TREND[i] != side): continue
            px = (Ll[i] + Hh[i - 2]) / 2 if side > 0 else (Hh[i] + Ll[i - 2]) / 2
            stp = (Ll[i - 2] if side > 0 else Hh[i - 2]) - side * BUF * px
            if not passes(d, side, px, P['filt']): continue
            t = limit_trade(d, 'FVG', side, px, stp, m0 + 5, min(m0 + 64, 869), None, P)
            if t: out.append(t)
    return out

def lvn_trades(d, P):
    zones, peaks = LVZ[(d, P['q'])]
    i0, i1 = today(d); out = []
    for i in range(i0 + 3, i1):
        m0 = five[d][i - i0][0]
        if m0 + 5 > 870: break
        pc, h, l, c = Cc[i - 1], Hh[i], Ll[i], Cc[i]
        sig = None
        for lo, hi in zones:
            if P['kind'] == 'brk':
                if pc <= lo < c < hi: sig = (1, l, nearest([x for x in peaks if x > hi], 1, c))
                elif pc >= hi > c > lo: sig = (-1, h, nearest([x for x in peaks if x < lo], -1, c))
            else:
                if pc < lo < h and c < lo: sig = (-1, h, nearest(peaks, -1, c))
                elif pc > hi > l and c > hi: sig = (1, l, nearest(peaks, 1, c))
            if sig: break
        if not sig: continue
        side, ext, tgt = sig
        if not passes(d, side, c, P['filt']): continue
        t = make(d, 'LVN', side, c, m0 + 5, ext - side * BUF * c, tgt, P)
        if t: out.append(t)
    return out

FAM = dict(zip(FAMS, (sweep, squeeze, smc, lvn_trades)))

def book(cands, maxn):
    """One trade at a time, at most maxn a day."""
    out = []; free = collections.defaultdict(int); n = collections.Counter()
    for t in sorted(cands, key=lambda t: (t['d'], t['m'])):
        if t['m'] >= free[t['d']] and n[t['d']] < maxn:
            out.append(t); free[t['d']] = t['mx'] + 1; n[t['d']] += 1
    return out

TG = ('2R', '3R', 'half', 'lvl')
GRID = ([dict(fam='SWEEP', levels=lv, confirm=cf, filt=f, target=tg, maxn=mn) for lv, cf, f, tg, mn in
         itertools.product(('pd', 'p2', 'swing', 'or'), ('close', 'choch'), ('none', 'poc', 'cpr'), TG, (1, 3))] +
        [dict(fam='SQZ', nb=nb, stop=sp, filt=f, target=tg, maxn=mn) for nb, sp, f, tg, mn in
         itertools.product((3, 6), ('box', 'mid'), ('none', 'poc', 'cpr'), TG[:3], (1, 3))] +
        [dict(fam='SMC', kind=k, filt=f, target=tg, maxn=mn) for k, f, tg, mn in
         itertools.product(('bos', 'choch', 'ob', 'fvg', 'fvg+'), ('none', 'poc', 'cpr'), TG[:3], (1, 3))] +
        [dict(fam='LVN', kind=k, q=q, filt=f, target=tg, maxn=mn) for k, q, f, tg, mn in
         itertools.product(('brk', 'rev'), (20, 35), ('none', 'poc', 'cpr'), TG, (1, 3))])

# ---------------- the indicator's best version, and the combinations ----------------
BASE_RAW = [dict(d=d, pnl=p, m=m, mx=mx, src=src) for d, p, m, mx, src in K.plan_trades() + K.vol_trades(1.5)]

def one_book(base, new, maxn=99):
    """One trade at a time across everything, as it would be traded live: the indicator's daily plan and volume-line
    trades (each as the indicator finds them) and every new signal, whichever comes first (the indicator's own first
    in the same minute); at most maxn new trades a day."""
    out = []; free = collections.defaultdict(int); n = collections.Counter()
    for t in sorted(base + new, key=lambda t: (t['d'], t['m'], {'plan': 0, 'vol': 1}.get(t['src'], 2))):
        own = t['src'] in ('plan', 'vol')
        if t['m'] >= free[t['d']] and (own or n[t['d']] < maxn):
            out.append(t); free[t['d']] = t['mx'] + 1; n[t['d']] += not own
    return out
BASE = one_book(BASE_RAW, [])

def stats(ts):
    p = [t['pnl'] for t in ts]; a = sum(t['pnl'] for t in ts if t['d'] in H1)
    eq = pk = dd = 0
    for t in sorted(ts, key=lambda t: (t['d'], t['mx'])): eq += t['pnl']; pk = max(pk, eq); dd = min(dd, eq - pk)
    return dict(n=len(p), w=int(sum(v > 0 for v in p)), net=float(sum(p)), a=float(a), b=float(sum(p) - a), dd=float(dd),
                worst=float(min(p)) if p else 0.0)

def run(P):
    cands = [t for d in D26 for t in FAM[P['fam']](d, P)]
    ts = book(cands, P['maxn'])
    return dict(P=P, own=stats(ts), one=stats(one_book(BASE_RAW, cands, P['maxn'])), sep=stats(BASE + ts))

if __name__ == '__main__':
    import multiprocessing as mp
    with mp.Pool() as pool: res = pool.map(run, GRID, chunksize=4)
    base = stats(BASE)
    json.dump(res, open(f'../.cache/smc_{NM}.json', 'w')); json.dump(base, open(f'../.cache/smc_base_{NM}.json', 'w'))
    print(f"{NM.upper()} 2026 ({len(D26)} sessions). Indicator's best version: {fmt(base)}")
    for fam in FAM:
        rs = [r for r in res if r['P']['fam'] == fam]
        print(f"\n{fam}: {len(rs)} versions; on its own made money {sum(r['own']['net'] > 0 for r in rs)}, in both halves "
              f"{sum(r['own']['a'] > 0 and r['own']['b'] > 0 for r in rs)}; middle version {np.median([r['own']['net'] for r in rs]):+,.0f}")
        for r in sorted(rs, key=lambda r: -r['own']['net'])[:5]:
            print(f"   {label(r['P']):58} {fmt(r['own'])}")
    for mode, txt in (('one', 'one trade at a time'), ('sep', 'as a second position')):
        better = [r for r in res if r[mode]['a'] > base['a'] and r[mode]['b'] > base['b']]
        print(f"\nADDED TO THE INDICATOR ({txt}): better in both halves {len(better)} of {len(res)}")
        for r in sorted(better, key=lambda r: -r[mode]['net'])[:8]:
            print(f"   {label(r['P']):58} {fmt(r[mode])}")

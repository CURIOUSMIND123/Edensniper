"""2026 only: does reading the volume under the price (Dr David Paul) make the indicator's calls better?

    python y2026_volume.py nifty        (or sensex)

The idea: in a bullish market price and volume move together (rises on rising volume, dips on falling volume:
accumulation); in a bearish market they pull apart (falls on heavy volume, rallies on light volume: distribution).
Volume: NIFTYBEES 1-minute volume (the index has none; Sensex uses the same Nifty ETF), on the index's 5-minute
candles (up candle = close above open).
VOLUME CHECKS at the moment of each signal, on the 5-minute candles that have closed by then:
  avg   BUY only if the average volume of the up candles beats the down candles' (x k); SELL the other way
  sum   the same with the total volume of up vs down candles
        over the last 6 / 12 / 24 candles or today so far; k = 1 or 1.25
  last  the last candle tells: BUY if it rose on above-average volume (average of the 12 before) or fell on
        below-average volume; SELL if it fell on above-average volume or rose on below-average volume (x k)
Applied to every setup of the original rules (CPR Magnet, breakout, reversal, volume lines, sweeps) or only some of
them, with the sweeps off (original rules) and on. One trade at a time; the alert program's own trade logic
(alerts/cprb_alerts.py), so a filtered signal lets the next one through exactly as it would live.
"""
import bisect, collections, json, sys
import numpy as np
import y2026 as Y
sys.path.insert(0, '../../alerts')
import cprb_alerts as A
A.VOLCHECK = False                 # the checks below are set here, not the alert program's default

NM, D26, H1 = Y.B.name, Y.D26, Y.H1
spec = A.SPEC[NM]; sess = {d: Y.one[d] for d in Y.days}
vol1 = collections.defaultdict(dict)
for k, v in Y.bees.items(): vol1[k[:10]][int(k[11:13]) * 60 + int(k[14:16])] = v[4]
daily = {d: Y.DAY[d] for d in Y.days}
CX = {d: A.context(spec, sess, vol1, d, daily) for d in D26}

# 5-minute candles across days: direction (index) and volume (NIFTYBEES)
G = [(d, j) for d in Y.days[Y.IDX[D26[0]] - 3:] for j in range(len(Y.five[d]))]
POS = {k: i for i, k in enumerate(G)}
DIR = np.array([np.sign(Y.five[d][j][4] - Y.five[d][j][1]) for d, j in G])
VOL = np.array([sum(vol1[d].get(Y.five[d][j][0] + k, 0) for k in range(5)) for d, j in G], float)
M0 = {d: [x[0] for x in Y.five[d]] for d in D26}

def last_closed(d, m):
    """Global index of the last 5-minute candle closed by minute m (the day before's last one before 9:20)."""
    j = bisect.bisect_right(M0[d], m - 5) - 1
    return POS[(d, j)] if j >= 0 else POS[(d, 0)] - 1

def check(F):
    mode, W, k = F['mode'], F['w'], F['k']
    def f(d, side, m):
        g = last_closed(d, m)
        if mode == 'last':
            if g < 12: return True
            avg = VOL[g - 12:g].mean(); heavy, light = VOL[g] > k * avg, VOL[g] * k < avg
            up, dn = DIR[g] > 0, DIR[g] < 0
            return (up and heavy or dn and light) if side > 0 else (dn and heavy or up and light)
        a = POS[(d, 0)] if W == 'day' else g - W + 1
        if g < a: return True
        dr, vv = DIR[a:g + 1], VOL[a:g + 1]
        u, w = vv[dr > 0], vv[dr < 0]
        if mode == 'avg': U, D = (u.mean() if len(u) else 0.0), (w.mean() if len(w) else 0.0)
        else: U, D = u.sum(), w.sum()
        return U > k * D if side > 0 else D > k * U
    return f

SETS = {'all': None, 'plan': ('MAGNET', 'BREAKOUT', 'REVERSAL'), 'vol': ('VOLUME LINE',), 'sweep': ('SWEEP',),
        'vol+sweep': ('VOLUME LINE', 'SWEEP')}

def run(V):
    A.SWEEP = V['sweep']
    f = check(V['F']) if V['F'] else None
    only = SETS[V['on']]
    ts = []
    for d in D26:
        cx = CX[d]
        cx['vf'] = None if f is None else (lambda side, m, src, d=d: (only is not None and src not in only) or f(d, side, m))
        ts += [dict(d=d, src=t['src'], pnl=t['exit']['pnl']) for t in A.day_trades(cx, Y.one[d], 929, True, False, 'classic') if t['taken']]
        cx['vf'] = None
    p = [t['pnl'] for t in ts]; a = sum(t['pnl'] for t in ts if t['d'] in H1)
    eq = pk = dd = 0
    for v in p: eq += v; pk = max(pk, eq); dd = min(dd, eq - pk)
    by = {s: (sum(t['src'] == s for t in ts), sum(t['pnl'] for t in ts if t['src'] == s)) for s in ('MAGNET', 'BREAKOUT', 'REVERSAL', 'VOLUME LINE', 'SWEEP')}
    return dict(V=V, n=len(p), w=sum(v > 0 for v in p), net=sum(p), a=a, b=sum(p) - a, dd=dd, by=by)

FILTERS = [dict(mode=md, w=w, k=k) for md in ('avg', 'sum') for w in (6, 12, 24, 'day') for k in (1.0, 1.25)] + \
          [dict(mode='last', w=12, k=k) for k in (1.0, 1.25)]
GRID = [dict(sweep=False, F=None, on='all'), dict(sweep=True, F=None, on='all')] + \
       [dict(sweep=sw, F=F, on=on) for F in FILTERS for sw, ons in ((False, ('all', 'plan', 'vol')), (True, ('all', 'sweep', 'vol+sweep'))) for on in ons]

def label(V):
    F = V['F']
    f = 'no volume check' if not F else (f"{F['mode']} " + ('' if F['mode'] == 'last' else f"{F['w']} ") + f"k {F['k']:g}")
    return f"{'+sweeps' if V['sweep'] else 'original'} | {f:18} on {V['on']}"

def fmt(r):
    return (f"{r['n']:4} tr {100 * r['w'] / max(1, r['n']):3.0f}% won net {r['net']:+7,.0f} ({r['net'] / max(1, r['n']):+5.1f}/trade; "
            f"Jan-Jun {r['a']:+6,.0f}, Jul-Oct {r['b']:+6,.0f}) fall {r['dd']:6,.0f}")

if __name__ == '__main__':
    import multiprocessing as mp
    with mp.Pool() as pool: res = pool.map(run, GRID, chunksize=2)
    json.dump(res, open(f'../.cache/volume_{NM}.json', 'w'))
    base = {False: res[0], True: res[1]}
    print(f"{NM.upper()} 2026. Original rules: {fmt(base[False])}\n       with sweeps:    {fmt(base[True])}")
    for sw in (False, True):
        rs = [r for r in res[2:] if r['V']['sweep'] == sw]; b = base[sw]
        better = [r for r in rs if r['a'] > b['a'] and r['b'] > b['b']]
        print(f"\n{'WITH SWEEPS' if sw else 'ORIGINAL RULES'}: {len(rs)} volume checks; better in both halves: {len(better)}; "
              f"more net points: {sum(r['net'] > b['net'] for r in rs)}")
        for r in sorted(rs, key=lambda r: -r['net'])[:12]:
            print(f"   {label(r['V']):48} {fmt(r)}" + ('  <- both halves better' if r in better else ''))

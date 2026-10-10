"""Price action + levels + machine learning: find 5-minute moments where +25 comes before -15.

    python pa_ml.py nifty        (or sensex; add --rebuild to recompute the measurements)

At every 5-minute candle close from 9:35 to 14:00 since 2023, about 50 measurements (all known at that moment):
  candle shape   body, wicks, close position, size vs ATR, for this and the previous candle; engulfing, pin bar,
                 inside / outside bar, doji, run of same-colour candles, higher high / lower low
  momentum       moves over the last 5 / 15 / 30 / 60 minutes, distance from EMA 20 / 50, EMA 20 slope
  day            minutes since 9:15, where price sits in the day's range, distance to the day's high / low, move
                 since the open, gap
  levels         signed distance to CPR top / bottom / pivot, R1 / S1 / R2 / S2, the first 15-minute high / low,
                 yesterday's high / low / close, the 15-day point of control and value area (all in ATR units),
                 and whether this candle touched each group
  CPR            width, narrow rank, today's CPR vs yesterday's, open above / inside / below
  volatility     ATR (14 five-minute candles) as % of price, today's range so far vs ATR
Two outcomes are learned for buys and for sells, checked on 1-minute candles:
  fixed  +25 before -15 Nifty points (scaled to price; about 80 / 48 on Sensex), within 60 minutes
  atr    +1.67 x ATR before -1 x ATR, within 60 minutes (the 25 / 15 idea, sized to the day's volatility)
A gradient-boosted tree model is retrained every month on all earlier months only (from 2023) and scores the next
month; results are for 2026 only (January to 9 October), which the model never trained on before scoring it. Each
month it trades the scores in its top 1% / 3% / 10% (the cut-off comes from the previous 3 months' scores), one
trade at a time, at most 5 a day, entries 9:35-14:00. Exits: the fixed target / stop / 60 minutes, or "run":
after the target, lock +10 and trail 15 behind the best price until 15:15 (so +25 can become +40-50).
Costs: 4 Nifty / 12 Sensex points a trade.
"""
import collections, json, statistics as st, sys, warnings
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
import cpr_orb as C

warnings.filterwarnings('ignore')
B = C.B
one, five, LV, DAY, days, COST = B.one, B.five, B.LV, B.DAY, B.days, B.COST
REF = 22500.0
IDX = {d: i for i, d in enumerate(days)}

# ---------------- 5-minute series across days: ATR 14, EMA 20 / 50 ----------------
seq = [(d, j) for d in days for j in range(len(five[d]))]
ATR, E20, E50 = {}, {}, {}
trs, e20, e50, pc = [], None, None, None
for d, j in seq:
    _, o, h, l, c = five[d][j]
    tr = h - l if pc is None else max(h - l, abs(h - pc), abs(l - pc))
    trs.append(tr); trs = trs[-14:]
    ATR[(d, j)] = sum(trs) / len(trs)
    e20 = c if e20 is None else e20 + 2 / 21 * (c - e20); e50 = c if e50 is None else e50 + 2 / 51 * (c - e50)
    E20[(d, j)], E50[(d, j)] = e20, e50
    pc = c
POS = {k: i for i, k in enumerate(seq)}
def bar_back(d, j, k):
    """The 5-minute candle k candles before (d, j), across days."""
    i = POS[(d, j)] - k
    dd, jj = seq[max(0, i)]
    return five[dd][jj], (dd, jj)

def path(o, h, l, c): return (o, l, h, c) if c >= o else (o, h, l, c)

def outcome(d, start, side, e, T, S, run):
    """Result in points before costs. Before the target: stop S, out after 60 minutes. With run, after the target
    the stop locks +10 (Nifty-sized) and trails 15 behind the best price until 15:15."""
    sc = e / REF; stp = e - side * S; tgt = e + side * T; hit = False; best = e
    for m, o, h, l, c in one[d]:
        if m < start: continue
        for px in path(o, h, l, c):
            if side * (px - stp) <= 0: return side * (stp - e), hit, m
            if not hit and side * (px - tgt) >= 0:
                if not run: return side * (tgt - e), True, m
                hit = True; stp = e + side * 10 * sc; best = px
        if hit:
            best = max(best, h) if side > 0 else min(best, l)
            ns = best - side * 15 * sc
            if side * (ns - stp) > 0: stp = ns
        if (not hit and m >= start + 59) or m >= C.T_OUT: return side * (c - e), hit, m
    return side * (one[d][-1][4] - e), hit, one[d][-1][0]

def features():
    import multiprocessing as mp
    with mp.Pool() as pool: parts = pool.map(day_rows, C.TEST, chunksize=8)
    return pd.DataFrame([r for p in parts for r in p])

def day_rows(d):
    rows = []
    if True:
        lv = LV[d]; pr = C.PROF[d]; i = IDX[d]
        po, ph, pl, pcl = DAY[days[i - 1]]
        first = [x for x in one[d] if x[0] < 570]; orh, orl = max(x[2] for x in first), min(x[3] for x in first)
        o0 = one[d][0][1]; cb = 1 if o0 > lv['top'] else -1 if o0 < lv['bot'] else 0
        dh, dl = -1e18, 1e18
        for j, x in enumerate(five[d]):
            m0, o, h, l, c = x; dh, dl = max(dh, h), min(dl, l)
            if m0 < 575 or m0 > 835: continue
            a = ATR[(d, j)]; rng = max(h - l, 1e-6)
            (pm, pO, pH, pL, pC), _ = bar_back(d, j, 1)
            prng = max(pH - pL, 1e-6); body = c - o; pbody = pC - pO
            run, k = 0, 0
            sgn = 1 if body > 0 else -1 if body < 0 else 0
            while sgn and k < 12:
                (_, xo, _, _, xc), _ = bar_back(d, j, k)
                if (xc - xo) * sgn > 0: run += sgn; k += 1
                else: break
            f = dict(d=d, j=j, m=m0 + 5 - 555, c=c, atr=a,
                     body=body / rng, uw=(h - max(o, c)) / rng, lw=(min(o, c) - l) / rng, clv=(c - l) / rng, rng_atr=rng / a,
                     p_body=pbody / prng, p_clv=(pC - pL) / prng, p_rng_atr=prng / a,
                     engulf=(1 if body > 0 > pbody and c >= pO and o <= pC else -1 if body < 0 < pbody and c <= pO and o >= pC else 0),
                     pin=(1 if (min(o, c) - l) / rng > 0.6 else -1 if (h - max(o, c)) / rng > 0.6 else 0),
                     inside=int(h <= pH and l >= pL), outside=int(h > pH and l < pL), doji=int(abs(body) / rng < 0.1),
                     run=run, hh=int(h > pH), ll=int(l < pL),
                     e20=(c - E20[(d, j)]) / a, e50=(c - E50[(d, j)]) / a, e20s=(E20[(d, j)] - E20[bar_back(d, j, 3)[1]]) / a,
                     pos=(c - dl) / max(dh - dl, 1e-6), d_dh=(dh - c) / a, d_dl=(c - dl) / a, from_open=(c - o0) / a,
                     gap=(o0 - pcl) / a, day_rng=(dh - dl) / a,
                     cpr_w=lv['w'], cpr_rank=lv['rank'], rel=C.REL[d], cb=cb, atr_pct=100 * a / c)
            for k in (1, 3, 6, 12):
                f[f'r{k}'] = (c - bar_back(d, j, k)[0][4]) / a
            lvls = dict(top=lv['top'], bot=lv['bot'], piv=lv['p'], r1=lv['r1'], s1=lv['s1'], r2=lv['r2'], s2=lv['s2'],
                        orh=orh, orl=orl, pdh=ph, pdl=pl, pdc=pcl, poc=pr[0], vah=pr[1], val=pr[2])
            for nm, L in lvls.items(): f['L_' + nm] = max(-10.0, min(10.0, (c - L) / a))
            for grp, ks in (('cpr', ('top', 'bot', 'piv')), ('or', ('orh', 'orl')), ('pd', ('pdh', 'pdl', 'pdc')),
                            ('piv', ('r1', 's1', 'r2', 's2')), ('prof', ('poc', 'vah', 'val'))):
                f['t_' + grp] = int(any(l <= lvls[k] <= h for k in ks))
            start = m0 + 5; sc = c / REF
            for side, nm in ((1, 'L'), (-1, 'S')):
                for lab, T, S in (('fix', 25 * sc, 15 * sc), ('atr', 1.67 * a, a)):
                    g, hit, mx = outcome(d, start, side, c, T, S, False)
                    f[f'y_{lab}{nm}'] = int(hit); f[f'g_{lab}{nm}'] = g; f[f'x_{lab}{nm}'] = mx
                    g2, _, mx2 = outcome(d, start, side, c, T, S, True); f[f'run_{lab}{nm}'] = g2; f[f'xr_{lab}{nm}'] = mx2
            rows.append(f)
    return rows

NONFEAT = {'d', 'j', 'c', 'atr', 'mo'}
def walk_forward(df, lab, start='2026-01'):
    feats = sorted(k for k in df.columns if k not in NONFEAT and not k.startswith(('y_', 'g_', 'run_', 'pr_', 'x_', 'xr_')))
    df['mo'] = df.d.str[:7]
    for nm in ('L', 'S'): df[f'pr_{lab}{nm}'] = np.nan
    for mo in sorted(df.mo.unique()):
        if mo < start: continue
        tr = df[df.mo < mo]; te = df.mo == mo
        for nm in ('L', 'S'):
            clf = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=200,
                                                 l2_regularization=1.0, random_state=0)
            clf.fit(tr[feats], tr[f'y_{lab}{nm}'])
            df.loc[te, f'pr_{lab}{nm}'] = clf.predict_proba(df.loc[te, feats])[:, 1]
    return feats

def trade(df, lab, top, run):
    """Each month: signals scoring in the top `top` share (cut-off from the previous 3 months' scores)."""
    out = []
    oos = df[df[f'pr_{lab}L'].notna()]
    mos = sorted(oos.mo.unique())
    for i, mo in enumerate(mos):
        hist = oos[oos.mo.isin(mos[max(0, i - 3):i])] if i else oos[oos.mo == mo]
        thr = {nm: np.quantile(hist[f'pr_{lab}{nm}'], 1 - top) for nm in ('L', 'S')}
        for d, g in oos[oos.mo == mo].groupby('d'):
            free, n = 0, 0
            for _, r in g.iterrows():
                if r.m + 555 < free or n >= 5: continue
                cand = [(r[f'pr_{lab}{nm}'], nm) for nm in ('L', 'S') if r[f'pr_{lab}{nm}'] >= thr[nm]]
                if not cand: continue
                _, nm = max(cand)
                g_pts = r[f'run_{lab}{nm}'] if run else r[f'g_{lab}{nm}']
                out.append((d, g_pts - COST, int(r[f'y_{lab}{nm}'])))
                n += 1; free = (r[f'xr_{lab}{nm}'] if run else r[f'x_{lab}{nm}']) + 1      # one trade at a time
    return out

def report(ts, label):
    if not ts: print(f'   {label}: no trades'); return
    l90 = set(C.TEST[-90:])
    for nm, xs in (('2026 (unseen)', ts), ('last 90 sessions', [t for t in ts if t[0] in l90])):
        p = [t[1] for t in xs]
        if not p: print(f'   {label} {nm}: no trades'); continue
        w = [v for v in p if v > 0]; lo = [v for v in p if v <= 0]
        mos = collections.defaultdict(float)
        for t in xs: mos[t[0][5:7]] += t[1]
        print(f"   {label} {nm}: {len(p)} trades ({len(p)/len({t[0] for t in xs}):.1f} on trading days), target first {100*st.mean(t[2] for t in xs):.0f}%, "
              f"won {len(w)} / lost {len(lo)} ({100*len(w)/len(p):.0f}%), {sum(w):+,.0f} / {sum(lo):+,.0f} = {sum(p):+,.0f}"
              + ('' if nm != '2026 (unseen)' else ' [' + ', '.join(f'{m} {v:+,.0f}' for m, v in sorted(mos.items())) + ']'))

if __name__ == '__main__':
    import os
    cache = f'../.cache/pa_ml_{B.name}.pkl'
    if os.path.exists(cache) and '--rebuild' not in sys.argv: df = pd.read_pickle(cache)
    else:
        df = features(); df.to_pickle(cache)
    print(f"{B.name.upper()}: {len(df):,} five-minute moments, {df.d.nunique()} days")
    for lab in ('fix', 'atr'):
        print(f"\n== {lab}: base rate (target before stop, any moment): buys {100*df[f'y_{lab}L'].mean():.0f}%, sells {100*df[f'y_{lab}S'].mean():.0f}% ==")
        feats = walk_forward(df, lab)
        oos = df[df[f'pr_{lab}L'].notna()]
        print(f"   unseen-month AUC (0.5 = no skill): buys {roc_auc_score(oos[f'y_{lab}L'], oos[f'pr_{lab}L']):.3f}, sells {roc_auc_score(oos[f'y_{lab}S'], oos[f'pr_{lab}S']):.3f}")
        for top in (0.01, 0.03, 0.10):
            for run in (False, True):
                report(trade(df, lab, top, run), f"top {int(top*100)}% {'run' if run else 'fixed'}")

"""Bitcoin: is there a sign before price goes up a lot or down a lot? (asked on 31 October 2026). BTCUSDT perpetual
January 2024 - October 2026 (btc_data.py); every 15 minutes is a moment; the signs are what was known at that moment;
judged on 2024-2025, checked on 2026. Points at $70,000 (moves as a share of the price).

    python -I btc_signs.py

At every moment, what came next:
  UP     price went 450 points up before 150 down (a BUY with the target 450 / stop 150 won)
  DOWN   450 down before 150 up (a SELL won)
  BIG    price went 700 points (1%) one way or the other within 4 hours
For a coin (a market with no memory) UP and DOWN are each about 150 / (450 + 150) = 25%.

The signs: the hour (UTC) and the day; the move of the last 15 minutes / hour / 4 hours / 24 hours; the range of the last
hour / 4 hours / day against its usual size; volume against the usual for that hour; the share of aggressive buying
(taker buys) in the last hour and 4 hours; where price is in the last 24 hours' range; RSI 14 (15-minute); the distance
from the 24-hour average; the change of open interest in 1 / 4 / 24 hours; the funding rate; the top traders' long /
short ratio and its 4-hour change; yesterday's range against usual.

1. Each sign alone, in five equal groups (cut on 2024-2025): UP / DOWN / BIG for each group, 2024-2025 | 2026.
2. All the signs together: a gradient-boosting model trained on 2024-2025 and tried on 2026 (AUC: 0.50 = no better than a
   coin, 1.00 = perfect), and the trades it would take on 2026 at its most confident (one at a time, costs 0.06%).
3. Trading the BIG sign (the size is known, the direction is not): when a big move is likely, a buy order X points above
   and a sell order X points below for an hour; the first one filled is the trade (target 450 / stop 150), the other is
   cancelled. "Likely" = the model's most confident 5% / 20% (trained on 2024 for 2025, on 2024-2025 for 2026), or the
   plain rule "the last hour's range is 1.7x its usual size or more".
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import btc_data as B

D, REF, COST = B.D, B.REF, B.COST
M, O, H, L, C, V, TB, OI, FUND, TOP = (D[k] for k in ('m', 'o', 'h', 'l', 'c', 'v', 'tb', 'oi', 'fund', 'top'))
TP, SL, BIG = 450, 150, 700

def rolling(fn, x, w):
    """fn over the last w values (inclusive) for each position, using a strided view."""
    from numpy.lib.stride_tricks import sliding_window_view as sw
    out = np.full(len(x), np.nan)
    out[w - 1:] = fn(sw(x, w), axis=1)
    return out

# moments: the close of every 15-minute block, with 24 hours of history and 24 hours after
idx = np.flatnonzero((M % 15) == 14)
idx = idx[(idx >= 1440 * 31) & (idx + 1441 < len(M))]
E = C[idx]
year = np.array([B.when(M[i]).year for i in idx])
TRAIN, TEST = year < 2026, year == 2026

# ---------------- what came next ----------------
UP, DOWN, BIGM, NEXT4 = (np.zeros(len(idx), bool), np.zeros(len(idx), bool), np.zeros(len(idx), bool), np.zeros(len(idx)))
for n, i in enumerate(idx):
    e = C[i]
    h, l = H[i + 1:i + 1441], L[i + 1:i + 1441]
    k = e / REF

    def first(mask):
        return int(np.argmax(mask)) if mask.any() else 10 ** 9
    a, b = first(h >= e + TP * k), first(h >= e + SL * k)
    c, d = first(l <= e - SL * k), first(l <= e - TP * k)
    UP[n] = a < c                                   # same candle -> the stop
    DOWN[n] = d < b
    h4, l4 = h[:240].max(), l[:240].min()
    BIGM[n] = (h4 - e) / k >= BIG or (e - l4) / k >= BIG
    NEXT4[n] = (h4 - l4) / k

# ---------------- the signs ----------------
def ret(i, back):
    j = np.maximum(i - back, 0)
    return (C[i] - C[j]) / C[i] * REF

def rng(i, back):
    hh = np.array([H[x - back + 1:x + 1].max() for x in i])
    ll = np.array([L[x - back + 1:x + 1].min() for x in i])
    return (hh - ll) / C[i] * REF, hh, ll

cv, ctb = np.cumsum(V), np.cumsum(TB)
def vol(i, back):
    return cv[i] - cv[i - back]

def tbshare(i, back):
    return (ctb[i] - ctb[i - back]) / np.maximum(cv[i] - cv[i - back], 1e-9)

F = {}
F['hour UTC'] = (M[idx] % 1440) // 60
F['weekend'] = np.array([B.when(M[i]).weekday() >= 5 for i in idx]).astype(float)
for nm, back in (('move 15m', 15), ('move 1h', 60), ('move 4h', 240), ('move 24h', 1440)):
    F[nm] = ret(idx, back)
r1, _, _ = rng(idx, 60)
r4, _, _ = rng(idx, 240)
r24, h24, l24 = rng(idx, 1440)
# usual size: the median over the 30 days before (2,880 moments)
def usual(x):
    out = np.full(len(x), np.nan)
    for n in range(2880, len(x)):
        out[n] = np.median(x[n - 2880:n:4])
    return out
F['range 1h / usual'] = r1 / usual(r1)
F['range 4h / usual'] = r4 / usual(r4)
F['range 24h / usual'] = r24 / usual(r24)
v1 = vol(idx, 60)
hod = F['hour UTC']
vu = np.full(len(idx), np.nan)
for hr in range(24):
    s = np.flatnonzero(hod == hr)
    for k_, n in enumerate(s):
        if k_ >= 20:
            vu[n] = v1[n] / np.median(v1[s[k_ - 20:k_]])
F['volume 1h / usual for the hour'] = vu
F['aggressive buying 1h'] = tbshare(idx, 60)
F['aggressive buying 4h'] = tbshare(idx, 240)
F['place in 24h range'] = (E - l24) / np.maximum(h24 - l24, 1e-9)
c15 = C[idx]
d = np.diff(c15, prepend=c15[0])
g = np.where(d > 0, d, 0.0); lo = np.where(d < 0, -d, 0.0)
def wilder(x, n=14):
    out = np.zeros(len(x)); a = 0.0
    for k_, v_ in enumerate(x):
        a = v_ if k_ == 0 else a + (v_ - a) / n
        out[k_] = a
    return out
ag, al = wilder(g), wilder(lo)
F['RSI 14 (15m)'] = 100 - 100 / (1 + ag / np.maximum(al, 1e-9))
ema = np.zeros(len(c15)); a = c15[0]
for k_, v_ in enumerate(c15):
    a = a + (v_ - a) * 2 / 97
    ema[k_] = a
F['distance from 24h average'] = (c15 - ema) / c15 * REF
for nm, back in (('open interest 1h %', 60), ('open interest 4h %', 240), ('open interest 24h %', 1440)):
    F[nm] = (OI[idx] / OI[idx - back] - 1) * 100
F['funding rate %'] = FUND[idx] * 100
F['top traders long / short'] = TOP[idx]
F['top traders 4h change'] = TOP[idx] - TOP[idx - 240]
day = M[idx] // 1440
F['yesterday range / usual'] = np.full(len(idx), np.nan)
dr = {}
for n, i in enumerate(idx):
    dr.setdefault(day[n], [np.inf, -np.inf])
    dr[day[n]][0] = min(dr[day[n]][0], L[i - 14:i + 1].min())
    dr[day[n]][1] = max(dr[day[n]][1], H[i - 14:i + 1].max())
days = sorted(dr)
dsz = {dd: (dr[dd][1] - dr[dd][0]) for dd in days}
yr = np.array([dsz.get(dd - 1, np.nan) for dd in day])
yu = np.array([np.nanmedian([dsz.get(dd - k_, np.nan) for k_ in range(2, 22)]) for dd in day])
F['yesterday range / usual'] = yr / yu

def pct(x):
    return f"{100 * x.mean():3.0f}%" if len(x) else '  - '

def alone():
    print(f"\n1. EACH SIGN ALONE (UP / DOWN / BIG; 2024-2025 | 2026). All moments: UP {pct(UP[TRAIN])} DOWN {pct(DOWN[TRAIN])} "
          f"BIG {pct(BIGM[TRAIN])} | UP {pct(UP[TEST])} DOWN {pct(DOWN[TEST])} BIG {pct(BIGM[TEST])}")
    flags = []
    for nm, x in F.items():
        print(f"  {nm}")
        ok = ~np.isnan(x)
        if nm == 'hour UTC':
            cuts = [(h_, h_ + 3) for h_ in range(0, 24, 3)]
            groups = [((x >= a_) & (x < b_), f"{a_:02d}-{b_:02d}h") for a_, b_ in cuts]
        elif nm == 'weekend':
            groups = [(x == 0, 'weekday'), (x == 1, 'weekend')]
        else:
            q = np.nanquantile(x[TRAIN & ok], [0.2, 0.4, 0.6, 0.8])
            edges = [-np.inf] + list(q) + [np.inf]
            groups = [(ok & (x >= edges[k_]) & (x < edges[k_ + 1]), f"{edges[k_]:.3g} to {edges[k_ + 1]:.3g}") for k_ in range(5)]
        for gm, lab in groups:
            a_, b_ = gm & TRAIN, gm & TEST
            print(f"    {lab:24} UP {pct(UP[a_])} DOWN {pct(DOWN[a_])} BIG {pct(BIGM[a_])} | UP {pct(UP[b_])} DOWN {pct(DOWN[b_])} BIG {pct(BIGM[b_])}")
            for side, arr in (('UP', UP), ('DOWN', DOWN)):
                if a_.sum() > 200 and b_.sum() > 100 and arr[a_].mean() >= 0.33 and arr[b_].mean() >= 0.33:
                    flags.append(f"{nm} {lab}: {side} {pct(arr[a_])} | {pct(arr[b_])}")
    print("\n  groups where UP or DOWN reached 33%+ in both periods: " + ('; '.join(flags) if flags else 'none'))

def trades(sel_idx, side):
    """One at a time from the moments chosen (positions in idx): -> list of (year, points)."""
    out, free = [], -1
    for n in sel_idx:
        i = idx[n]
        if i <= free:
            continue
        e = C[i]
        r = B.first_hit(i, side, e, TP, SL)
        out.append((year[n], r[2]))
        free = r[1]
    return out

def model():
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import roc_auc_score
    X = np.column_stack(list(F.values()))
    print("\n2. ALL THE SIGNS TOGETHER (trained on 2024-2025, tried on 2026)")
    for nm, y, side in (('UP (a BUY wins)', UP, 1), ('DOWN (a SELL wins)', DOWN, -1), ('BIG (a 1% move within 4h)', BIGM, 0)):
        clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=200,
                                             l2_regularization=1.0, random_state=1)
        clf.fit(X[TRAIN], y[TRAIN])
        p_tr, p_te = clf.predict_proba(X[TRAIN])[:, 1], clf.predict_proba(X[TEST])[:, 1]
        print(f"  {nm}: AUC on 2026 {roc_auc_score(y[TEST], p_te):.3f} (on 2024-2025 itself {roc_auc_score(y[TRAIN], p_tr):.3f}); "
              f"share in 2026 {pct(y[TEST])}")
        te = np.flatnonzero(TEST)
        for top in (0.20, 0.05, 0.01):
            cut = np.quantile(p_tr, 1 - top)
            pick = te[p_te >= cut]
            line = f"    its most confident {int(top * 100):2}% (by 2024-2025's cut): {len(pick):5} moments, came true {pct(y[pick])}"
            if side:
                tr = trades(pick, side)
                line += f"; as trades one at a time: {len(tr)} trades, won {pct(np.array([p > 0 for _, p in tr]))}, {sum(p for _, p in tr):+,.0f} points"
            print(line)
    # how well the size of the next 4 hours follows the last 4 hours
    ok = ~np.isnan(F['range 4h / usual'])
    print(f"  the next 4 hours' range against the last 4 hours' range: correlation {np.corrcoef(r4[ok], NEXT4[ok])[0, 1]:.2f}")

def bracket(pos, X, tp=TP, sl=SL):
    """One at a time from the moments in pos: -> list of (year, points); moments where neither order fills are skipped."""
    out, free = [], -1
    for n in pos:
        i = idx[n]
        if i <= free:
            continue
        e = C[i]
        k = e / REF
        up, dn = e + X * k, e - X * k
        h, l = H[i + 1:i + 61], L[i + 1:i + 61]
        ju = int(np.argmax(h >= up)) if (h >= up).any() else 10 ** 9
        jd = int(np.argmax(l <= dn)) if (l <= dn).any() else 10 ** 9
        if ju == jd:                                  # neither, or both in one candle (unknown order): no trade
            free = i + 60 if ju < 10 ** 9 else free
            continue
        side, t, px = (1, i + 1 + ju, up) if ju < jd else (-1, i + 1 + jd, dn)
        r = B.first_hit(t, side, px, tp, sl)
        out.append((year[n], r[2]))
        free = r[1]
    return out

def trade_big():
    from sklearn.ensemble import HistGradientBoostingClassifier
    X = np.column_stack(list(F.values()))
    print("\n3. TRADING THE BIG SIGN: orders X points above and below, the first filled is the trade (target 450 / stop 150)")
    picks = {}
    for tr_m, te_m, lab in ((year == 2024, year == 2025, '2025'), (year < 2026, year == 2026, '2026')):
        clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=200,
                                             l2_regularization=1.0, random_state=1).fit(X[tr_m], BIGM[tr_m])
        p_tr, p_te = clf.predict_proba(X[tr_m])[:, 1], clf.predict_proba(X[te_m])[:, 1]
        te = np.flatnonzero(te_m)
        for top in (0.05, 0.20):
            picks.setdefault(f"model's top {int(top * 100)}%", {})[lab] = te[p_te >= np.quantile(p_tr, 1 - top)]
    rule = np.flatnonzero(F['range 1h / usual'] >= 1.7)
    picks['last hour 1.7x usual'] = {lab: rule[year[rule] == int(lab)] for lab in ('2024', '2025', '2026')}
    picks['every moment (no sign)'] = {lab: np.flatnonzero(year == int(lab)) for lab in ('2024', '2025', '2026')}
    for nm, by in picks.items():
        for X_ in (50, 150):
            cells = []
            for lab in ('2024', '2025', '2026'):
                if lab not in by:
                    continue
                tr = bracket(by[lab], X_)
                w = np.array([p > 0 for _, p in tr])
                cells.append(f"{lab}: {len(tr):4} tr {100 * w.mean() if len(w) else 0:3.0f}% {sum(p for _, p in tr):+8,.0f}")
            print(f"  {nm:24} X {X_:3}:  " + " | ".join(cells))

if __name__ == '__main__':
    print(f"BTCUSDT perpetual {B.when(M[idx[0]]):%Y-%m-%d} - {B.when(M[idx[-1]]):%Y-%m-%d}: {TRAIN.sum()} moments in 2024-2025, "
          f"{TEST.sum()} in 2026; points at $70,000")
    alone()
    model()
    trade_big()

"""Does yesterday's FII / retail (Client) positioning predict today's Nifty move?"""
import json, sys, numpy as np, pandas as pd
sys.path.insert(0, '.')
from wf import load, walk_forward, trade, report, BASE, roc_auc_score, COST
poi = json.load(open('../.cache/poi.json'))
rows = []
for d in sorted(poi):
    p = poi[d]
    if 'FII' not in p or 'Client' not in p: continue
    def f(who):
        x = p[who]   # FutIdxL, FutIdxS, FutStkL, FutStkS, CallL, PutL, CallS, PutS, ...
        return dict(futL=x[0] / max(1, x[0] + x[1]), optnet=((x[4] - x[6]) - (x[5] - x[7])) / max(1, x[4] + x[5] + x[6] + x[7]), futnet=x[0] - x[1])
    fi, cl = f('FII'), f('Client'); pr = f('Pro') if 'Pro' in p else dict(futL=np.nan, optnet=np.nan, futnet=np.nan)
    rows.append(dict(day=d, fii_futL=fi['futL'], fii_opt=fi['optnet'], cli_futL=cl['futL'], cli_opt=cl['optnet'], pro_futL=pr['futL'], pro_opt=pr['optnet'], fii_futnet=fi['futnet']))
s = pd.DataFrame(rows).sort_values('day')
for c in ['fii_futL', 'fii_opt', 'cli_futL', 'cli_opt', 'pro_opt', 'fii_futnet']:
    s['d_' + c] = s[c].diff()
# shift: positions known at the end of day D-1 are used on day D
feat = [c for c in s.columns if c != 'day']
s[feat] = s[feat].shift(1)
print('days with positions:', s.dropna().shape[0], s.day.min(), s.day.max())
# daily outcomes from the 1-minute data
import collections
up = json.load(open('../.cache/nifty_1m.json'))
by = collections.defaultdict(list)
for k in sorted(up):
    if '09:15' <= k[11:] < '15:30': by[k[:10]].append(up[k])
dd = []
prev_c = None
for d in sorted(by):
    b = by[d]
    if len(b) < 300: continue
    o, c = b[0][0], b[-1][3]
    c920 = b[5][3]; c1515 = [x for x in b][360][3] if len(b) > 360 else c
    dd.append(dict(day=d, gap=(o - prev_c) if prev_c else np.nan, oc=c - o, day_trade=c1515 - c920, cc=(c - prev_c) if prev_c else np.nan))
    prev_c = c
dd = pd.DataFrame(dd)
m = s.merge(dd, on='day').dropna()
print(f"{len(m)} days matched\n")
print('Correlation of yesterday-end positioning with today (Spearman):')
print(f"{'signal':14s} {'gap':>7s} {'open->close':>12s} {'close->close':>13s}")
for c in feat:
    print(f"{c:14s} {m[c].corr(m.gap, method='spearman'):+7.3f} {m[c].corr(m.oc, method='spearman'):+12.3f} {m[c].corr(m.cc, method='spearman'):+13.3f}")
# simple day trades: 9:20 -> 15:15 in the direction a signal says (top / bottom third), cost 4 pts
print('\nDay trade 9:20 -> 15:15, follow FII vs fade retail (Client), top vs bottom third of the signal; first half / second half of the period:')
half = m.day.iloc[len(m) // 2]
for c, sign, label in (('fii_futL', 1, 'follow FII futures long %'), ('d_fii_futL', 1, 'follow change in FII long %'), ('fii_opt', 1, 'follow FII option bias'),
                       ('cli_futL', -1, 'fade Client futures long %'), ('cli_opt', -1, 'fade Client option bias'), ('d_cli_futL', -1, 'fade change in Client long %')):
    lo, hi = m[c].quantile(1 / 3), m[c].quantile(2 / 3)
    side = np.where(m[c] >= hi, sign, np.where(m[c] <= lo, -sign, 0))
    pnl = side * m.day_trade - np.where(side != 0, 4.0, 0)
    a = pnl[(side != 0) & (m.day < half)]; b = pnl[(side != 0) & (m.day >= half)]
    print(f"  {label:32s} trades {int((side!=0).sum())}: first half {a.sum():+7.0f} pts (avg {a.mean():+5.1f}, hit {100*(a>0).mean():.0f}%), second half {b.sum():+7.0f} pts (avg {b.mean():+5.1f}, hit {100*(b>0).mean():.0f}%)")
s.to_pickle('../.cache/sentiment.pkl')
# ML with sentiment added
if len(sys.argv) > 1:
    df = load('nifty', s[['day'] + feat])
    SENT = feat
    for feats, lab in ((BASE, 'price features only'), (BASE + SENT, 'price + FII / retail positioning')):
        r = walk_forward(df, feats, 'f30', 'gbm'); nd = r.day.nunique()
        print(f"\nNifty ML, {lab}: out-of-sample AUC {roc_auc_score(r.y, r.p):.4f}")
        for th in (0.52, 0.55, 0.58): report('nifty', trade(r, 'nifty', th, 'f30', 30), f"prob >= {th}", nd)

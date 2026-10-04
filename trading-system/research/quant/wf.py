import sys, numpy as np, pandas as pd, warnings
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.metrics import roc_auc_score
warnings.filterwarnings('ignore')
COST = {'nifty': 4.0, 'sensex': 12.0}
BASE = ['m', 'fair', 'gap', 'prevret', 'd_pdh', 'd_pdl', 'd_pdc', 'd_orh', 'd_orl', 'swept_pdh', 'swept_pdl', 'swept_orh', 'swept_orl',
        'above_pdh', 'below_pdl', 'r5', 'r15', 'r30', 'r60', 'pos', 'd_hi', 'd_lo', 'dayrng', 'rv30', 'round100', 'dow']
def load(name, extra=None):
    df = pd.read_pickle(f'../.cache/{name}_rows.pkl')
    if extra is not None: df = df.merge(extra, on='day', how='left')
    df['month'] = df.day.str[:7]
    return df
def walk_forward(df, feats, horizon='f30', model='gbm', start='2024-01'):
    df = df.dropna(subset=[horizon]).copy()
    df['y'] = (df[horizon] > 0).astype(int)
    df['p'] = np.nan
    for mo in sorted(df.month.unique()):
        if mo < start: continue
        tr = df[df.month < mo]; te = df.month == mo
        if model == 'gbm':
            clf = HistGradientBoostingClassifier(max_iter=150, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=300, l2_regularization=1.0, random_state=0)
        else:
            clf = make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=500))
        X = tr[feats].fillna(0) if model != 'gbm' else tr[feats]
        clf.fit(X, tr.y)
        Xt = df.loc[te, feats].fillna(0) if model != 'gbm' else df.loc[te, feats]
        df.loc[te, 'p'] = clf.predict_proba(Xt)[:, 1]
    return df[df.p.notna()]
def trade(df, name, th, horizon='f30', hold=30):
    c = COST[name]; out = []
    for day, g in df.groupby('day', sort=True):
        nxt = -1
        for m, p, f in zip(g.m.values, g.p.values, g[horizon].values):
            if m < nxt: continue
            if p >= th or p <= 1 - th:
                d = 1 if p >= th else -1
                out.append((day, m, d, d * f, d * f - c)); nxt = m + hold
    return pd.DataFrame(out, columns=['day', 'm', 'dir', 'gross', 'net'])
def report(name, res, label, ndays):
    if res.empty: print(f'  {label}: no trades'); return
    yr = res.groupby(res.day.str[:4]).net.sum().round(0).to_dict()
    print(f"  {label}: {len(res)} trades ({len(res)/ndays:.1f}/day), hit {100*(res.gross>0).mean():.1f}%, avg gross {res.gross.mean():+.2f} pts, avg net {res.net.mean():+.2f} pts, total net {res.net.sum():+,.0f} pts | by year {yr}")
if __name__ == '__main__':
    for name in sys.argv[1:]:
        df = load(name)
        for model in ('gbm', 'logit'):
            for hz, hold in (('f15', 15), ('f30', 30), ('f60', 60)):
                r = walk_forward(df, BASE, hz, model)
                auc = roc_auc_score(r.y, r.p)
                nd = r.day.nunique()
                print(f"{name} {model} horizon {hz}: out-of-sample AUC {auc:.4f} (0.5 = coin flip), {nd} days")
                for th in (0.52, 0.55, 0.58):
                    report(name, trade(r, name, th, hz, hold), f"prob >= {th}", nd)

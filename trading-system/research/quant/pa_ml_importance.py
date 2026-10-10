"""Which kinds of measurements the price-action model relied on in 2026 (run pa_ml.py for both indices first).

    python pa_ml_importance.py

Trains on 2023-2025 for "+25 before -15" (buys and sells), then scrambles one group of measurements at a time on
2026 and reports how much the model's AUC drops. Bigger drop = the model relied on that group more.
"""
import sys, pandas as pd, numpy as np, warnings
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
warnings.filterwarnings('ignore')
NONFEAT = {'d', 'j', 'c', 'atr', 'mo'}
for name in ('nifty', 'sensex'):
    df = pd.read_pickle(f'../.cache/pa_ml_{name}.pkl')
    feats = sorted(k for k in df.columns if k not in NONFEAT and not k.startswith(('y_', 'g_', 'run_', 'pr_', 'x_', 'xr_')))
    tr, te = df[df.d < '2026-01-01'], df[df.d >= '2026-01-01']
    out = {}
    for y in ('y_fixL', 'y_fixS'):
        clf = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=200, l2_regularization=1.0, random_state=0).fit(tr[feats], tr[y])
        pi = permutation_importance(clf, te[feats], te[y], scoring='roc_auc', n_repeats=3, random_state=0)
        for f, v in zip(feats, pi.importances_mean): out[f] = out.get(f, 0) + v / 2
    top = sorted(out.items(), key=lambda x: -x[1])
    groups = {'candle shape': ('body', 'uw', 'lw', 'clv', 'rng_atr', 'p_body', 'p_clv', 'p_rng_atr', 'engulf', 'pin', 'inside', 'outside', 'doji', 'run', 'hh', 'll'),
              'momentum / trend': ('r1', 'r3', 'r6', 'r12', 'e20', 'e50', 'e20s'),
              'levels': tuple(k for k in feats if k.startswith(('L_', 't_'))),
              'day / time / volatility': ('m', 'pos', 'd_dh', 'd_dl', 'from_open', 'gap', 'day_rng', 'atr_pct'),
              'CPR': ('cpr_w', 'cpr_rank', 'rel', 'cb')}
    print(name, 'AUC lost when each group is scrambled (bigger = model relied on it more):')
    for g, ks in groups.items(): print(f'   {g:24} {sum(out.get(k, 0) for k in ks):+.4f}')
    print('   top 8 single measurements:', ', '.join(f'{k} {v:+.4f}' for k, v in top[:8]))

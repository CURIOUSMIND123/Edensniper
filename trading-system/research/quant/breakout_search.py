import sys, json, itertools, multiprocessing as mp
sys.path.insert(0, '.')
from breakout_retest_test import run, metrics, days5
P = {'last90': ('2026-07-03', '2026-10-01'), 'prev90': ('2026-04-04', '2026-07-02'), 'all': ('2023-01-01', '2026-10-01')}
def nd(name, a, b): return sum(1 for d, *_ in days5(name) if a <= d <= b)
def job(cfg):
    out = {'cfg': cfg}
    for name in ('nifty', 'sensex'):
        tr = run(name, cfg)
        for k, (a, b) in P.items(): out[f'{name}_{k}'] = metrics(name, tr, a, b, nd(name, a, b))
    return out
if __name__ == '__main__':
    days5('nifty'); days5('sensex')
    exits = [('tp', 1.0, 0, 0), ('tp', 2.0, 0, 0), ('tp', 0.5, 0, 0), ('trail', 0, 0.3, 0), ('trail', 0, 0.6, 0), ('trail', 0, 0.6, 0.5), ('eod', 0, 0, 0), ('eod', 0, 0, 0.5)]
    cfgs = []
    for setup, flt, tol, tg, stp, ex in itertools.product(('orb3', 'orb6', 'levels', 'ema'), ('none', 'strong', 'expand'), (0.05, 0.12), ('prevhigh', 'engulf', 'pin'), ('swing', 'fixed'), exits):
        if setup == 'ema' and flt != 'none': continue
        kind, rr, trail, be = ex
        cfgs.append(dict(setup=setup, filter=flt, tol=tol, trig=tg, stop=stp, sl=0.3, exit=kind, rr=rr, trail=trail, be=be, maxn=3))
    print('configs', len(cfgs), flush=True)
    with mp.Pool(4) as p: rows = p.map(job, cfgs, chunksize=8)
    json.dump(rows, open('../.cache/breakout_rows.json', 'w'))
    daily = [r for r in rows if r['nifty_last90']['perday'] >= 0.8]
    good = [r for r in daily if r['nifty_last90']['net'] > 0]
    hw = [r for r in daily if r['nifty_last90']['win'] >= 70]
    print(f"Nifty, trading at least 0.8 times a day in the last 90 days: {len(daily)} versions")
    print(f"  made money in the last 90 days: {len(good)}; of those, also in the 90 days before: {sum(r['nifty_prev90']['net'] > 0 for r in good)}; also over all 3.75 years: {sum(r['nifty_prev90']['net'] > 0 and r['nifty_all']['net'] > 0 for r in good)}; and on Sensex over all years: {sum(r['nifty_prev90']['net'] > 0 and r['nifty_all']['net'] > 0 and r['sensex_all']['net'] > 0 for r in good)}")
    print(f"  won 70%+ in the last 90 days: {len(hw)}; of those made money in the last 90 days: {sum(r['nifty_last90']['net'] > 0 for r in hw)}")
    good.sort(key=lambda r: -r['nifty_last90']['net'])
    print('\nBest in the last 90 days (Nifty), and how the same rules did elsewhere:')
    for r in good[:12]:
        c = r['cfg']; a, b, z, s = r['nifty_last90'], r['nifty_prev90'], r['nifty_all'], r['sensex_all']
        print(f"  {c['setup']:6s} {c['filter']:6s} tol={c['tol']} {c['trig']:8s} stop={c['stop']:5s} exit={c['exit']} rr={c['rr']} trail={c['trail']} be={c['be']} | LAST90 {a['perday']}/day win {a['win']}% net {a['net']:+} (aw {a['aw']} al {a['al']}) | PREV90 net {b['net']:+} | ALL win {z['win']}% net {z['net']:+} | SENSEX all {s['net']:+}")
    surv = [r for r in rows if r['nifty_all']['perday'] >= 0.8 and r['nifty_all']['net'] > 0]
    print(f"\nAny version trading 0.8+/day that made money on Nifty over all 3.75 years: {len(surv)}")
    for r in sorted(surv, key=lambda r: -r['nifty_all']['net'])[:6]:
        c = r['cfg']; z = r['nifty_all']; s = r['sensex_all']
        print(f"  {c} | ALL {z} | SENSEX {s['net']:+}")

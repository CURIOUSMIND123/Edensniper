import sys, json, itertools, multiprocessing as mp
sys.path.insert(0, '.')
from liquidity_trap_test import days5, evaluate
L90 = ('2026-07-03', '2026-10-01'); P90 = ('2026-04-04', '2026-07-02'); ALL = ('2023-01-01', '2026-10-01')
def job(cfg):
    return dict(cfg=cfg, last90=evaluate('nifty', cfg, *L90), prev90=evaluate('nifty', cfg, *P90), all=evaluate('nifty', cfg, *ALL))
if __name__ == '__main__':
    days5('nifty')
    cfgs = []
    for lv, sw, tp, sl, stp, st_, la in itertools.product(('pd', 'pd+or', 'pd+or+sw', 'pd+or+sw+day', 'sw+day'), (0.0, 0.03, 0.08),
                                                     (0.05, 0.08, 0.12, 0.16, 0.25), (0.3, 0.45, 0.6, 0.9), ('fixed', 'bar'), (570, 600), (780, 870)):
        if stp == 'bar' and sl != 0.45: continue
        cfgs.append(dict(setup='trap', levels=lv, sweep=sw, tp=tp, sl=sl, stop=stp, start=st_, last=la))
    for setup, aw, tp, sl, la in itertools.product(('fair', 'trend'), (0.2, 0.4, 0.7, 1.0), (0.05, 0.08, 0.12, 0.16, 0.25), (0.3, 0.45, 0.6, 0.9), (780, 870)):
        cfgs.append(dict(setup=setup, levels='', sweep=0, away=aw, tp=tp, sl=sl, stop='fixed', start=570, last=la))
    print('configs', len(cfgs), flush=True)
    with mp.Pool(4) as p: rows = p.map(job, cfgs, chunksize=16)
    json.dump(rows, open('../.cache/high_win_rows.json', 'w'))
    hi = [r for r in rows if r['last90']['win'] >= 80 and r['last90']['n'] >= 40]
    print('80%+ win rate in the last 90 days (40+ trades):', len(hi), '| of those making money in the last 90 days:', sum(r['last90']['net'] > 0 for r in hi),
          '| also in the 90 days before:', sum(r['last90']['net'] > 0 and r['prev90']['net'] > 0 for r in hi),
          '| also over all 3.75 years:', sum(r['last90']['net'] > 0 and r['prev90']['net'] > 0 and r['all']['net'] > 0 for r in hi))
    hi.sort(key=lambda r: -r['last90']['net'])
    for r in hi[:15]:
        c = r['cfg']; a, b, z = r['last90'], r['prev90'], r['all']
        print(f"{c['setup']:5s} {c['levels']:12s} sw={c['sweep']} away={c.get('away','-')} tp={c['tp']} sl={c['sl']} stop={c['stop']} {c['start']}-{c['last']} | LAST90 n={a['n']} win={a['win']}% net={a['net']:+} aw={a['aw']} al={a['al']} green={a['green']}% | PREV90 win={b['win']}% net={b['net']:+} | ALL n={z['n']} win={z['win']}% net={z['net']:+}")
    allpos = [r for r in rows if r['all']['net'] > 0 and r['all']['n'] >= 100]
    print('\nAny config (any win rate) positive over all 3.75 years with 100+ trades:', len(allpos))
    for r in sorted(allpos, key=lambda r: -r['all']['net'])[:8]:
        c = r['cfg']; a, b, z = r['last90'], r['prev90'], r['all']
        print(f"{c['setup']:5s} {c['levels']:12s} sw={c['sweep']} away={c.get('away','-')} tp={c['tp']} sl={c['sl']} stop={c['stop']} | ALL n={z['n']} win={z['win']}% net={z['net']:+} | LAST90 win={a['win']}% net={a['net']:+} | PREV90 net={b['net']:+}")

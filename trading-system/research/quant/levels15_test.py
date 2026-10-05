"""15-Day Levels reference (tradingview/levels_15d.pine) and its search.

Run from this folder: `python levels15_build.py nifty` (and sensex) first, then
    python levels15_test.py --default      # the indicator's default rules by period, plus a random-direction check
    python levels15_test.py                # the 1,296-version search
"""
import pickle, collections, statistics as st, sys, itertools, json, multiprocessing as mp, random
COST = {'nifty': 4.0, 'sensex': 12.0}
def path(o, h, l, c): return (o, h, l, c) if abs(h - o) < abs(o - l) else (o, l, h, c)
_D = {}
def data(name):
    if name not in _D: _D[name] = pickle.load(open(f'../.cache/{name}_levels.pkl', 'rb'))
    return _D[name]

def day_trades(b5, U, lv, cfg, rng=None):
    smin, tt, sb, rr, mode, tgt_mode = cfg['smin'], cfg['tt'] * U, cfg['sb'] * U, cfg['rr'], cfg['mode'], cfg['tgt']
    L = [(p, s) for p, s, k in lv if s >= smin]
    allp = sorted(p for p, s in L)
    used = set(); out = []; pos = None; ntr = 0
    for i, (m, o, h, l, c) in enumerate(b5):
        if pos:
            sd, e, stp, tg = pos
            for px in path(o, h, l, c):
                if sd * (px - stp) <= 0: out.append((sd, e, stp, 'SL')); pos = None; break
                if sd * (px - tg) >= 0: out.append((sd, e, tg, 'TP')); pos = None; break
            if pos and m >= 915: out.append((sd, e, c, 'time')); pos = None
        if pos or i < 1 or not (570 <= m < 870) or ntr >= cfg['maxn']: continue
        pc = b5[i - 1][4]; po = b5[i - 1][1]; rngb = h - l
        if rngb <= 0: continue
        body = abs(c - o)
        sig = 0; stop = None
        for p, s in sorted(L, key=lambda x: -x[1]):
            if mode in ('reject', 'both'):
                upw = h - max(o, c); dnw = min(o, c) - l
                bear = c < o and (upw >= 0.4 * rngb or (pc > po and c < po and o >= pc))
                bull = c > o and (dnw >= 0.4 * rngb or (pc < po and c > po and o <= pc))
                if (p, -1, 'r') not in used and pc < p and h >= p - tt and c < p and bear:
                    sig, stop = -1, max(h, p) + sb; used.add((p, -1, 'r')); break
                if (p, 1, 'r') not in used and pc > p and l <= p + tt and c > p and bull:
                    sig, stop = 1, min(l, p) - sb; used.add((p, 1, 'r')); break
            if mode in ('break', 'both'):
                strong_up = c > o and body >= 0.6 * rngb and (c - l) >= 0.75 * rngb
                strong_dn = c < o and body >= 0.6 * rngb and (h - c) >= 0.75 * rngb
                if (p, 1, 'b') not in used and pc <= p and c > p + 0.03 * U and strong_up:
                    sig, stop = 1, p - sb; used.add((p, 1, 'b')); break
                if (p, -1, 'b') not in used and pc >= p and c < p - 0.03 * U and strong_dn:
                    sig, stop = -1, p + sb; used.add((p, -1, 'b')); break
        if not sig: continue
        if rng is not None:
            flip = rng.choice((1, -1))
            if flip < 0: sig = -sig; stop = c - (stop - c)
        risk = sig * (c - stop)
        if not (0.05 * U <= risk <= 0.8 * U): continue
        tgt = c + sig * rr * risk
        if tgt_mode == 'level':
            nxt = [q for q in allp if sig * (q - c) >= rr * risk]
            if nxt: tgt = min(nxt) if sig > 0 else max(nxt)
        pos = (sig, c, stop, tgt); ntr += 1
    if pos: out.append((pos[0], pos[1], b5[-1][4], 'end'))
    return out

def run(name, cfg, rng=None):
    D = data(name); res = []
    for dd in D['days']:
        d = dd['d']
        if d not in D['levels']: continue
        lv = D['levels'][d][f"{cfg['lv']}|{cfg['mt']}"]
        for sd, e, x, why in day_trades(dd['b5'], dd['U'], lv, cfg, rng): res.append((d, sd * (x - e) - COST[name], why))
    return res

def metrics(res, a, b, ndays):
    r = [(d, p) for d, p, w in res if a <= d <= b]
    if not r: return dict(n=0, perday=0, win=0, net=0, aw=0, al=0, green=0)
    p = [x for _, x in r]; w = [x for x in p if x > 0]; lo = [x for x in p if x <= 0]
    byd = collections.defaultdict(float)
    for d, x in r: byd[d] += x
    return dict(n=len(p), perday=round(len(p) / ndays, 2), win=round(100 * len(w) / len(p), 1), net=round(sum(p)), aw=round(st.mean(w), 1) if w else 0,
                al=round(st.mean(lo), 1) if lo else 0, green=round(100 * sum(v > 0 for v in byd.values()) / ndays))

P = {'last90': ('2026-07-03', '2026-10-01'), 'prev90': ('2026-04-04', '2026-07-02'), 'all': ('2023-01-01', '2026-10-01')}
def ndays(name, a, b): return sum(1 for d in data(name)['levels'] if a <= d <= b)
def job(cfg):
    out = {'cfg': cfg}
    for name in ('nifty', 'sensex'):
        res = run(name, cfg)
        for k, (a, b) in P.items(): out[f'{name}_{k}'] = metrics(res, a, b, ndays(name, a, b))
    return out
DEFAULT = dict(lv='D', mt=0.1, smin=2, mode='break', tt=0.03, sb=0.12, rr=2.0, tgt='level', maxn=3)

def show_default():
    periods = {'last 90 days': ('2026-07-03', '2026-10-01'), '90 days before': ('2026-04-04', '2026-07-02'), '2023': ('2023-01-01', '2023-12-31'),
               '2024': ('2024-01-01', '2024-12-31'), '2025': ('2025-01-01', '2025-12-31'), '2026': ('2026-01-01', '2026-12-31'), 'all': ('2023-01-01', '2026-12-31')}
    for name in ('nifty', 'sensex'):
        res = run(name, DEFAULT)
        for label, (a, b) in periods.items():
            r = metrics(res, a, b, ndays(name, a, b))
            print(f"{name:6s} {label:15s} {r['n']:4d} trades ({r['perday']}/day) won {r['win']:4.1f}%  avg win {r['aw']:+6.1f}  avg loss {r['al']:+6.1f}  net {r['net']:+6}")
        real = metrics(res, '2023-01-01', '2026-12-31', 1)['net']
        sims = [metrics(run(name, DEFAULT, random.Random(k)), '2023-01-01', '2026-12-31', 1)['net'] for k in range(60)]
        print(f"{name}: random directions did as well in {100 * sum(x >= real for x in sims) / len(sims):.0f}% of 60 runs")

if __name__ == '__main__' and '--default' in sys.argv:
    show_default()
elif __name__ == '__main__':
    data('nifty'); data('sensex')
    cfgs = [dict(lv=lv, mt=mt, smin=sm, mode=mo, tt=tt, sb=sb, rr=rr, tgt=tg, maxn=3)
            for lv, mt, sm, mo, tt, sb, rr, tg in itertools.product(('D', 'DV', 'DVC'), (0.05, 0.1), (1, 2, 3.5), ('reject', 'break', 'both'),
                                                                    (0.03, 0.08), (0.05, 0.12), (0.5, 1.0, 2.0), ('level', 'fixed'))]
    print('configs', len(cfgs), flush=True)
    with mp.Pool(4) as pool: rows = pool.map(job, cfgs, chunksize=8)
    json.dump(rows, open('../.cache/levels15_rows.json', 'w'))
    for idx in ('nifty', 'sensex'):
        daily = [r for r in rows if r[f'{idx}_last90']['perday'] >= 0.8]
        g = [r for r in daily if r[f'{idx}_last90']['net'] > 0]
        print(f"{idx}: {len(daily)} versions trade 0.8+/day in the last 90 days; {len(g)} made money there; {sum(r[f'{idx}_prev90']['net'] > 0 for r in g)} also the 90 days before; "
              f"{sum(r[f'{idx}_prev90']['net'] > 0 and r[f'{idx}_all']['net'] > 0 for r in g)} also all 3.75 years; win 70%+ and money in last 90: {sum(r[f'{idx}_last90']['win'] >= 70 for r in g)}")
    both = [r for r in rows if r['nifty_all']['net'] > 0 and r['sensex_all']['net'] > 0 and r['nifty_all']['perday'] >= 0.5]
    print('positive over all years on BOTH indices with 0.5+ trades a day:', len(both))
    for r in sorted(both, key=lambda r: -r['nifty_all']['net'])[:10]:
        c = r['cfg']; print(f"  {c} | NIFTY all {r['nifty_all']} last90 {r['nifty_last90']['net']:+} prev90 {r['nifty_prev90']['net']:+} | SENSEX all {r['sensex_all']['net']:+} last90 {r['sensex_last90']['net']:+}")
    best90 = sorted([r for r in rows if r['nifty_last90']['perday'] >= 0.8], key=lambda r: -r['nifty_last90']['net'])[:8]
    print('best on Nifty in the last 90 days (0.8+/day):')
    for r in best90:
        c = r['cfg']; print(f"  {c['lv']}|{c['mt']} s>={c['smin']} {c['mode']} tt={c['tt']} sb={c['sb']} rr={c['rr']} {c['tgt']} | LAST90 {r['nifty_last90']} | PREV90 {r['nifty_prev90']['net']:+} | ALL {r['nifty_all']['net']:+} win {r['nifty_all']['win']}% | SENSEX all {r['sensex_all']['net']:+}")

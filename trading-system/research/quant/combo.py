"""TCI x JJ: a liquidity sweep of a TCI level (PDH / PDL / opening-range high / low) that closes back inside,
while price is away from the 9:15 fair price -> trade back toward fair price."""
import sys, itertools, multiprocessing as mp, datetime as dt, statistics as st, collections
sys.path.insert(0, '.')
from search_lib import load, COST, SPLIT
from alt import manage
T = dt.time
def combo(day, prev, ref, sweep_k=0.05, min_away=0.3, stop_mode='sweep', tgt='fair', rr=2.0, last=T(13, 0), max_tr=10, need_fair=True):
    if not prev: return []
    pdh = max(b.h for b in prev); pdl = min(b.l for b in prev)
    fair = day[0].o; orh = max(b.h for b in day[:15]); orl = min(b.l for b in day[:15])
    out = []; i = 15; used = set()
    while i < len(day):
        b = day[i]
        if b.t.time() >= last or len(out) >= max_tr: break
        sig = 0
        for lvl, kind in ((pdh, 'H'), (orh, 'H'), (pdl, 'L'), (orl, 'L')):
            if (lvl, kind) in used: continue
            if kind == 'H' and b.h > lvl + sweep_k * ref and b.c < lvl: sig, ext, key = -1, b.h, (lvl, kind)
            if kind == 'L' and b.l < lvl - sweep_k * ref and b.c > lvl: sig, ext, key = 1, b.l, (lvl, kind)
            if sig: break
        if sig:
            away = (b.c - fair) / ref
            ok = (not need_fair) or (sig == -1 and away >= min_away) or (sig == 1 and away <= -min_away)
            if ok:
                used.add(key); e = b.c
                s = ext - sig * 0.02 * ref if stop_mode == 'sweep' else e - sig * 0.3 * ref
                s = ext + 0.02 * ref * (1 if sig == -1 else -1) if stop_mode == 'sweep' else s
                risk = sig * (e - s)
                if risk > 0.5:
                    t = fair if tgt == 'fair' else e + sig * rr * risk
                    if sig * (t - e) <= 0.5 * risk: i += 1; continue
                    x, why, k = manage(day, i, sig, e, s, t)
                    out.append((sig * (x - e), risk)); i = k + 1; continue
        i += 1
    return out
def ev(args):
    name, kw = args
    days = load(name); c = COST[name]; res = {'train': [], 'test': []}; tr_days = collections.Counter()
    for j, (d, pb, bars, ref) in enumerate(days):
        per = 'train' if d < SPLIT else 'test'
        prev = days[j - 1][2] if j else []
        for pts, risk in combo(bars, prev, ref, **kw):
            res[per].append(((pts - c) / risk, pts - c)); tr_days[per] += 0
    o = dict(name=name, **{k: str(v) for k, v in kw.items()})
    for per, rs in res.items():
        o[per] = (len(rs), round(sum(r for r, _ in rs), 1), round(sum(p for _, p in rs)), round(100 * sum(r > 0 for r, _ in rs) / max(1, len(rs))))
    return o
if __name__ == '__main__':
    load('nifty'); load('sensex')
    jobs = [(n, dict(sweep_k=sk, min_away=ma, stop_mode=sm, tgt=tg, rr=rr, last=la, need_fair=nf))
            for n in ('nifty', 'sensex') for sk in (0.02, 0.08) for ma in (0.2, 0.5) for sm in ('sweep', 'fixed')
            for tg, rr in (('fair', 0), ('rr', 1.5), ('rr', 3.0)) for la in (T(11, 0), T(15, 0)) for nf in (True, False)
            if not (not nf and (ma == 0.5))]
    with mp.Pool(4) as p: rows = p.map(ev, jobs)
    rows.sort(key=lambda r: -r['train'][1])
    print('configs', len(rows), '| positive train', sum(r['train'][1] > 0 for r in rows), '| positive train AND test', sum(r['train'][1] > 0 and r['test'][1] > 0 for r in rows))
    print('(trades, R after costs, points after costs, win%)')
    for r in rows[:12]:
        print(f"  {r['name']:6s} sweep={r['sweep_k']} away={r['min_away']} stop={r['stop_mode']} tgt={r['tgt']} rr={r['rr']} last={r['last'][:5]} needfair={r['need_fair']} | TRAIN {r['train']} | TEST {r['test']}")

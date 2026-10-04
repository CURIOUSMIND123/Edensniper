import sys, json, itertools, multiprocessing as mp, datetime as dt, statistics as st, collections
sys.path.insert(0, '.')
from search_lib import load, COST, SPLIT, bar_path
T = lambda h, m: dt.time(h, m)

def resample(bars, n):
    out = []
    for i in range(0, len(bars), n):
        ch = bars[i:i + n]
        out.append(type(ch[0])(ch[0].t, ch[0].o, max(b.h for b in ch), min(b.l for b in ch), ch[-1].c))
    return out

def manage(bars, i0, side, entry, stop, target, trail=None, exit_t=T(15, 15)):
    """Walk 1-minute bars after index i0. trail(i) -> new stop or None. Returns (exit_px, reason)."""
    for i in range(i0 + 1, len(bars)):
        b = bars[i]
        for px in bar_path(b):
            if side * (px - stop) <= 0: return stop, 'SL', i
            if target is not None and side * (px - target) >= 0: return target, 'TP', i
        if b.t.time() >= exit_t: return b.c, 'time', i
        if trail:
            ns = trail(i)
            if ns is not None and side * (ns - stop) > 0: stop = ns
    return bars[-1].c, 'end', len(bars) - 1

def orb(day, prev, ref, n_min=15, stop='or', rr=2.0, last=T(11, 0), bias='none', k=0.3):
    bars = day; orh = max(b.h for b in bars[:n_min]); orl = min(b.l for b in bars[:n_min])
    gap = bars[0].o - (prev[-1].c if prev else bars[0].o)
    for i in range(n_min, len(bars)):
        b = bars[i]
        if b.t.time() >= last: return []
        side = 1 if b.c > orh else -1 if b.c < orl else 0
        if not side: continue
        if bias == 'gap' and gap * side <= 0: return []
        if bias == 'fade' and gap * side >= 0: return []
        e = b.c
        s = {'or': orl if side > 0 else orh, 'mid': (orh + orl) / 2, 'k': e - side * k * ref}[stop]
        risk = side * (e - s)
        if risk <= 0.5: return []
        tgt = None if rr == 'eod' else e + side * rr * risk
        x, why, _ = manage(bars, i, side, e, s, tgt)
        return [(side * (x - e), risk, why)]
    return []

def supertrend(day, prev, ref, tf=5, atr_n=10, mult=3.0, start=T(9, 30), last=T(14, 30)):
    hist = resample(prev, tf) if prev else []
    cur = resample(day, tf); allb = hist + cur
    trs = []; st_line = None; dirn = 0; trades = []; atr = None
    lines = []
    for j, b in enumerate(allb):
        pc = allb[j - 1].c if j else b.o
        tr = max(b.h - b.l, abs(b.h - pc), abs(b.l - pc)); trs.append(tr)
        atr = st.mean(trs[-atr_n:]) if atr is None or len(trs) <= atr_n else (atr * (atr_n - 1) + tr) / atr_n
        mid = (b.h + b.l) / 2; up = mid - mult * atr; dn = mid + mult * atr
        if st_line is None: dirn, st_line = 1, up
        elif dirn > 0:
            st_line = max(st_line, up)
            if b.c < st_line: dirn, st_line = -1, dn
        else:
            st_line = min(st_line, dn)
            if b.c > st_line: dirn, st_line = 1, up
        lines.append((b.t, dirn, st_line))
    # trade flips inside today's window; stop = supertrend line (trailing), exit on flip or 15:15
    tline = {t: (d, l) for t, d, l in lines}
    idx1 = {b.t: i for i, b in enumerate(day)}
    prevd = None; pos_until = -1
    for j in range(len(hist), len(allb)):
        t, d, l = lines[j]
        if prevd is not None and d != prevd and allb[j].t.time() >= start and allb[j].t.time() < last:
            close_t = allb[j].t + dt.timedelta(minutes=tf - 1)
            i = idx1.get(close_t)
            if i is not None and i > pos_until:
                e = day[i].c; side = d; s = l; risk = side * (e - s)
                if risk > 0.5:
                    def trail(k, side=side):
                        bt = day[k].t
                        if (bt.minute + 1) % tf == 0:
                            st0 = bt - dt.timedelta(minutes=tf - 1)
                            if st0 in tline and tline[st0][0] == side: return tline[st0][1]
                            if st0 in tline and tline[st0][0] != side: return day[k].c + side * 0.01  # flip: exit at close
                        return None
                    x, why, k = manage(day, i, side, e, s, None, trail)
                    trades.append((side * (x - e), risk, why)); pos_until = k
        prevd = d
    return trades

def ema_cross(day, prev, ref, tf=5, fast=9, slow=21, k=0.3, rr=2.0, start=T(9, 45), last=T(14, 30)):
    hist = resample(prev, tf) if prev else []; cur = resample(day, tf); allb = hist + cur
    ef = es = None; trades = []; idx1 = {b.t: i for i, b in enumerate(day)}; pos_until = -1; prevs = None
    af, as_ = 2 / (fast + 1), 2 / (slow + 1)
    for j, b in enumerate(allb):
        ef = b.c if ef is None else ef + af * (b.c - ef); es = b.c if es is None else es + as_ * (b.c - es)
        sgn = 1 if ef > es else -1
        if j >= len(hist) and prevs is not None and sgn != prevs and start <= b.t.time() < last:
            i = idx1.get(b.t + dt.timedelta(minutes=tf - 1))
            if i is not None and i > pos_until:
                e = day[i].c; risk = k * ref
                x, why, kk = manage(day, i, sgn, e, e - sgn * risk, None if rr == 'eod' else e + sgn * rr * risk)
                trades.append((sgn * (x - e), risk, why)); pos_until = kk
        prevs = sgn
    return trades

STRATS = {'orb': orb, 'supertrend': supertrend, 'ema': ema_cross}
def evaluate(args):
    name, strat, kw = args
    days = load(name); c = COST[name]; res = {'train': [], 'test': []}; byd = {'train': collections.defaultdict(float), 'test': collections.defaultdict(float)}
    nd = {'train': 0, 'test': 0}
    for i, (d, prevb, bars, ref) in enumerate(days):
        per = 'train' if d < SPLIT else 'test'; nd[per] += 1
        prev = days[i - 1][2] if i else []
        for pts, risk, why in STRATS[strat](bars, prev, ref, **kw):
            r = (pts - c) / risk; res[per].append(r); byd[per][d] += r
    out = dict(name=name, strat=strat, kw={k: (str(v) if isinstance(v, dt.time) else v) for k, v in kw.items()})
    for per in res:
        rs = res[per]
        if not rs: out[per] = dict(n=0, R=0, avgR=0, win=0, pf=0, green=0); continue
        gp = sum(x for x in rs if x > 0); gl = -sum(x for x in rs if x < 0)
        out[per] = dict(n=len(rs), R=round(sum(rs), 1), avgR=round(st.mean(rs), 3), win=round(100 * sum(x > 0 for x in rs) / len(rs)), pf=round(gp / gl, 2) if gl else 99,
                        green=round(100 * sum(v > 0 for v in byd[per].values()) / nd[per]))
    return out
if __name__ == '__main__':
    load('nifty'); load('sensex')
    jobs = []
    for n in ('nifty', 'sensex'):
        for nm, stp, rr, last, bias in itertools.product((5, 15, 30), ('or', 'mid', 'k'), (1.0, 2.0, 3.0, 'eod'), (T(11, 0), T(13, 0)), ('none', 'gap', 'fade')):
            jobs.append((n, 'orb', dict(n_min=nm, stop=stp, rr=rr, last=last, bias=bias)))
        for tf, an, mu in itertools.product((3, 5, 15), (7, 10), (2.0, 3.0)):
            jobs.append((n, 'supertrend', dict(tf=tf, atr_n=an, mult=mu)))
        for tf, fs, k, rr in itertools.product((5, 15), ((9, 21), (20, 50)), (0.2, 0.4), (2.0, 'eod')):
            jobs.append((n, 'ema', dict(tf=tf, fast=fs[0], slow=fs[1], k=k, rr=rr)))
    with mp.Pool(4) as pool: rows = pool.map(evaluate, jobs, chunksize=2)
    json.dump(rows, open('../.cache/alt.json', 'w'))
    for strat in STRATS:
        rs = [r for r in rows if r['strat'] == strat]
        print(f"== {strat}: {len(rs)} configs; positive train {sum(r['train']['R'] > 0 for r in rs)}, positive train AND test {sum(r['train']['R'] > 0 and r['test']['R'] > 0 for r in rs)}")
        for r in sorted(rs, key=lambda r: -r['train']['R'])[:8]:
            print(f"  {r['name']:6s} {r['kw']} TRAIN n={r['train']['n']} R={r['train']['R']:+.1f} avg={r['train']['avgR']:+.3f} pf={r['train']['pf']} win={r['train']['win']}% | TEST n={r['test']['n']} R={r['test']['R']:+.1f} avg={r['test']['avgR']:+.3f} pf={r['test']['pf']} win={r['test']['win']}%")

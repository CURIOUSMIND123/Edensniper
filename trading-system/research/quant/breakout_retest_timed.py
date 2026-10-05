"""Breakout -> pullback -> reversal candle -> ride, on 5-minute candles (TradingView fill rules)."""
import sys, collections, statistics as st
sys.path.insert(0, '.')
from liquidity_trap_timed import days5, path, COST

def trig(kind, d, b, pb):
    m, o, h, l, c = b; _, po, ph, pl, pc = pb
    body = abs(c - o); rng = h - l
    if kind == 'prevhigh': return c > ph if d > 0 else c < pl
    if kind == 'engulf':
        return (c > o and pc < po and c > po and o <= pc) if d > 0 else (c < o and pc > po and c < po and o >= pc)
    if kind == 'pin':
        if rng <= 0: return False
        if d > 0: w = min(o, c) - l; return w >= 2 * body and w >= 0.5 * rng and c >= (h + l) / 2
        w = h - max(o, c); return w >= 2 * body and w >= 0.5 * rng and c <= (h + l) / 2
    return False

def strong_ok(f, d, b, prevs):
    m, o, h, l, c = b; rng = h - l
    if f == 'none': return True
    if f == 'strong': return rng > 0 and abs(c - o) >= 0.6 * rng and ((c - l) >= 0.75 * rng if d > 0 else (h - c) >= 0.75 * rng)
    if f == 'expand': return len(prevs) >= 6 and rng >= 1.5 * st.mean(x[2] - x[3] for x in prevs[-6:])
    return True

def run(name, cfg):
    """All days; returns list of (day, side, entry, exit, reason)."""
    out = []; e20 = e50 = None; a20, a50 = 2 / 21, 2 / 51
    for d, b5, U, prev in days5(name):
        pdh, pdl = prev[0], prev[1]
        tol, maxn = cfg['tol'] * U, cfg.get('maxn', 3)
        levels = []
        if cfg['setup'] == 'levels': levels += [dict(L=pdh, d=1, st='wait'), dict(L=pdl, d=-1, st='wait')]
        pos = None; ntr = 0
        for i, b in enumerate(b5):
            m, o, h, l, c = b
            # manage
            if pos:
                s, e, stp, tgt, risk, best, m0 = pos
                for px in path(o, h, l, c):
                    if s * (px - stp) <= 0: out.append((d, s, e, stp, 'SL', m0)); pos = None; break
                    if tgt is not None and s * (px - tgt) >= 0: out.append((d, s, e, tgt, 'TP', m0)); pos = None; break
                if pos and m >= 915: out.append((d, s, e, c, 'time', m0)); pos = None
                if pos:
                    best = max(best, s * (c - e))
                    if cfg['exit'] == 'trail':
                        stp = max(stp, e + best - cfg['trail'] * U) if s > 0 else min(stp, e - best + cfg['trail'] * U)
                    if cfg['be'] and best >= cfg['be'] * risk: stp = max(stp, e) if s > 0 else min(stp, e)
                    pos = (s, e, stp, tgt, risk, best, m0)
            # emas (5-minute, carried across days)
            e20 = c if e20 is None else e20 + a20 * (c - e20); e50 = c if e50 is None else e50 + a50 * (c - e50)
            # build levels
            if cfg['setup'] in ('orb3', 'orb6', 'levels'):
                n_or = 6 if cfg['setup'] == 'orb6' else 3
                if i == n_or - 1:
                    levels += [dict(L=max(x[2] for x in b5[:n_or]), d=1, st='wait'), dict(L=min(x[3] for x in b5[:n_or]), d=-1, st='wait')]
                if cfg['setup'] == 'levels' and i >= 4:
                    w = b5[i - 4:i + 1]; mid = w[2]
                    if all(mid[2] > x[2] for k, x in enumerate(w) if k != 2): levels.append(dict(L=mid[2], d=1, st='wait'))
                    if all(mid[3] < x[3] for k, x in enumerate(w) if k != 2): levels.append(dict(L=mid[3], d=-1, st='wait'))
            sig = 0; stop = None
            if i >= 1:
                pb = b5[i - 1]
                if cfg['setup'] == 'ema':
                    for dd in (1, -1):
                        trend = (e20 > e50) if dd > 0 else (e20 < e50)
                        touched = any((x[3] <= e20 + tol) if dd > 0 else (x[2] >= e20 - tol) for x in b5[max(0, i - 2):i + 1])
                        if trend and touched and (c > e50 if dd > 0 else c < e50) and trig(cfg['trig'], dd, b, pb):
                            sig = dd; ext = min(x[3] for x in b5[max(0, i - 3):i + 1]) if dd > 0 else max(x[2] for x in b5[max(0, i - 3):i + 1]); break
                else:
                    for lv in levels:
                        L, dd = lv['L'], lv['d']
                        if lv['st'] == 'wait':
                            if (c > L if dd > 0 else c < L) and (pb[4] <= L if dd > 0 else pb[4] >= L) and strong_ok(cfg['filter'], dd, b, b5[:i]):
                                lv.update(st='broken', ext=None, rt=False)
                            continue
                        if lv['st'] != 'broken': continue
                        if (c < L - 0.1 * U) if dd > 0 else (c > L + 0.1 * U): lv['st'] = 'dead'; continue
                        if lv['ext'] is None: lv['ext'] = l if dd > 0 else h
                        else: lv['ext'] = min(lv['ext'], l) if dd > 0 else max(lv['ext'], h)
                        if (l <= L + tol) if dd > 0 else (h >= L - tol): lv['rt'] = True
                        if lv['rt'] and not sig and (c > L if dd > 0 else c < L) and trig(cfg['trig'], dd, b, pb):
                            sig = dd; ext = lv['ext']; lv['rt'] = False; lv['ext'] = None
            if sig and pos is None and 570 <= m < 870 and ntr < maxn and cfg.get('rand') is not None:
                sig = cfg['rand'].choice((1, -1))
            if sig and pos is None and 570 <= m < 870 and ntr < maxn:
                stop = (ext - sig * 0.03 * U) if cfg['stop'] == 'swing' else c - sig * cfg['sl'] * U
                risk = sig * (c - stop)
                if 0.08 * U <= risk <= 0.8 * U:
                    tgt = c + sig * cfg['rr'] * risk if cfg['exit'] == 'tp' else None
                    pos = (sig, c, stop, tgt, risk, 0.0, m); ntr += 1
        if pos: out.append((d, pos[0], pos[1], b5[-1][4], 'end', pos[6]))
    return out

def metrics(name, trades, d0, d1, ndays):
    c = COST[name]; rs = [(d, s * (x - e) - c) for d, s, e, x, why in trades if d0 <= d <= d1]
    if not rs: return dict(n=0, perday=0, win=0, net=0, aw=0, al=0, green=0)
    p = [x for _, x in rs]; w = [x for x in p if x > 0]; lo = [x for x in p if x <= 0]
    byd = collections.defaultdict(float)
    for d, x in rs: byd[d] += x
    return dict(n=len(p), perday=round(len(p) / ndays, 2), win=round(100 * len(w) / len(p), 1), net=round(sum(p)),
                aw=round(st.mean(w), 1) if w else 0, al=round(st.mean(lo), 1) if lo else 0, green=round(100 * sum(v > 0 for v in byd.values()) / ndays))

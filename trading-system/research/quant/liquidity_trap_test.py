"""Liquidity Trap reference (tradingview/liquidity_trap.pine) and the 5-minute high-win-rate search.

Fills follow TradingView's broker emulator: entry at the signal bar's close, exits from the next bar using
its path rule (open -> nearer extreme -> farther extreme -> close). Run from this folder after
`python ../fair_price_backtest.py` has filled ../.cache:

    python liquidity_trap_test.py            # the indicator's default rules, Nifty and Sensex, by period
"""
import json, collections, statistics as st, datetime as dt
COST = {'nifty': 4.0, 'sensex': 12.0}
_C = {}
def days5(name):
    if name in _C: return _C[name]
    raw = json.load(open(f'../.cache/{name}_1m.json'))
    by = collections.defaultdict(list)
    for k in sorted(raw):
        hm = k[11:16]
        if '09:15' <= hm < '15:30': by[k[:10]].append((int(hm[:2]) * 60 + int(hm[3:]), *raw[k]))
    out = []; ranges = []; prev = None
    for d in sorted(by):
        b1 = by[d]
        if len(b1) < 300: continue
        b5 = []
        for i in range(0, len(b1), 5):
            ch = b1[i:i + 5]
            b5.append((ch[0][0], ch[0][1], max(x[2] for x in ch), min(x[3] for x in ch), ch[-1][4]))
        am = [x for x in b1 if x[0] < 645]
        rng = max(x[2] for x in am) - min(x[3] for x in am)
        U = st.median(ranges[-20:]) if len(ranges) >= 10 else None
        if U and prev: out.append((d, b5, U, prev))
        ranges.append(rng); prev = (max(x[2] for x in b1), min(x[3] for x in b1), b1[-1][4], b1[0][1])
    _C[name] = out
    return out

def path(o, h, l, c):
    return (o, h, l, c) if abs(h - o) < abs(o - l) else (o, l, h, c)

def run_day(b5, U, prev, cfg):
    """Return list of (side, entry, exit, reason, minute)."""
    pdh, pdl, pdc, pdo = prev
    tp, sl = cfg['tp'] * U, cfg['sl'] * U
    sweep = cfg['sweep'] * U
    lv_set = cfg['levels']; setup = cfg['setup']
    start, last = cfg.get('start', 570), cfg.get('last', 870)
    fair = b5[0][1]
    levels = []                                     # [price, kind(+1 high/-1 low), used]
    if 'pd' in lv_set: levels += [[pdh, 1, False], [pdl, -1, False]]
    trades = []; pos = None; dayhi = b5[0][2]; daylo = b5[0][3]; swH = None; swL = None
    for i, (m, o, h, l, c) in enumerate(b5):
        if pos:                                     # manage open trade on this bar
            side, e, s_, t_ = pos
            for px in path(o, h, l, c):
                if side * (px - s_) <= 0: trades.append((side, e, s_, 'SL', m)); pos = None; break
                if side * (px - t_) >= 0: trades.append((side, e, t_, 'TP', m)); pos = None; break
            if pos and m >= 915: trades.append((side, e, c, 'time', m)); pos = None
        if i == 2 and 'or' in lv_set:
            levels += [[max(x[2] for x in b5[:3]), 1, False], [min(x[3] for x in b5[:3]), -1, False]]
        if 'sw' in lv_set and i >= 4:
            a = b5[i - 4:i + 1]; mid = a[2]
            if all(mid[2] > x[2] for k, x in enumerate(a) if k != 2): levels.append([mid[2], 1, False])
            if all(mid[3] < x[3] for k, x in enumerate(a) if k != 2): levels.append([mid[3], -1, False])
        sig = 0
        if pos is None and start <= m < last and i >= 3:
            if setup == 'trap':
                for L in levels:
                    if L[2]: continue
                    if L[1] == 1 and h > L[0] + sweep and c < L[0] and b5[i - 1][4] <= L[0]: sig = -1; L[2] = True; break
                    if L[1] == -1 and l < L[0] - sweep and c > L[0] and b5[i - 1][4] >= L[0]: sig = 1; L[2] = True; break
                if not sig and 'day' in lv_set:
                    if h > dayhi + sweep and c < dayhi: sig = -1
                    elif l < daylo - sweep and c > daylo: sig = 1
            elif setup == 'fair':
                k = cfg['away'] * U
                if c - fair >= k and swL is not None and c < swL <= b5[i - 1][4]: sig = -1
                elif fair - c >= k and swH is not None and c > swH >= b5[i - 1][4]: sig = 1
            elif setup == 'trend':                  # pullback in the direction away from the open after a strong first hour
                k = cfg['away'] * U
                if c - fair >= k and swH is not None and c > swH >= b5[i - 1][4]: sig = 1
                elif fair - c >= k and swL is not None and c < swL <= b5[i - 1][4]: sig = -1
        if sig:
            stop = c - sig * sl
            if cfg.get('stop') == 'bar': stop = (h if sig < 0 else l) - sig * 0.05 * U
            if sig * (c - stop) > 0.5:
                pos = (sig, c, stop, c + sig * tp)
        if i >= 4:                                  # 2-bar swings for fair / trend setups
            a = b5[i - 4:i + 1]; mid = a[2]
            if all(mid[2] > x[2] for kk, x in enumerate(a) if kk != 2): swH = mid[2]
            if all(mid[3] < x[3] for kk, x in enumerate(a) if kk != 2): swL = mid[3]
        dayhi, daylo = max(dayhi, h), min(daylo, l)
    if pos: trades.append((pos[0], pos[1], b5[-1][4], 'end', b5[-1][0]))
    return trades

def evaluate(name, cfg, d0, d1):
    c = COST[name]; res = []; byd = collections.defaultdict(float); nd = 0
    for d, b5, U, prev in days5(name):
        if not (d0 <= d <= d1): continue
        nd += 1
        for side, e, x, why, m in run_day(b5, U, prev, cfg):
            p = side * (x - e) - c; res.append(p); byd[d] += p
    if not res: return dict(n=0, win=0, net=0, aw=0, al=0, days=nd, green=0, worst=0)
    w = [p for p in res if p > 0]; lo = [p for p in res if p <= 0]
    return dict(n=len(res), win=round(100 * len(w) / len(res), 1), net=round(sum(res)), aw=round(st.mean(w), 1) if w else 0,
                al=round(st.mean(lo), 1) if lo else 0, days=nd, green=round(100 * sum(v > 0 for v in byd.values()) / nd),
                worst=round(min(byd.values()), 0))


DEFAULT = dict(setup='trap', levels='pd', sweep=0.08, tp=0.25, sl=0.6, stop='fixed', start=570, last=870)

if __name__ == '__main__':
    periods = {'last 90 days': ('2026-07-03', '2026-10-01'), '90 days before': ('2026-04-04', '2026-07-02'),
               '2023': ('2023-01-01', '2023-12-31'), '2024': ('2024-01-01', '2024-12-31'), '2025': ('2025-01-01', '2025-12-31'),
               '2026': ('2026-01-01', '2026-12-31'), 'all': ('2023-01-01', '2026-12-31')}
    for name in ('nifty', 'sensex'):
        for label, (a, b) in periods.items():
            r = evaluate(name, DEFAULT, a, b)
            print(f"{name:6s} {label:15s} trades {r['n']:4d}  won {r['win']:5.1f}%  avg win {r['aw']:+6.1f}  avg loss {r['al']:+6.1f}  net {r['net']:+6} pts")

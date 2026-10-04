import sys, json, datetime as dt, statistics as st, collections, random, time as _t
sys.path.insert(0, '../..')
from tci.rules import Bar, bar_path
from tci.fairprice import FPParams, run_day
COST = {'nifty': 4.0, 'sensex': 12.0}
SPLIT = '2025-07-01'
_DAYS = {}
def load(name):
    if name in _DAYS: return _DAYS[name]
    raw = json.load(open(f'../.cache/{name}_1m.json'))
    by = collections.defaultdict(list)
    for k in sorted(raw):
        t = dt.datetime.strptime(k, '%Y-%m-%d %H:%M')
        if dt.time(9, 15) <= t.time() < dt.time(15, 30):
            by[k[:10]].append(Bar(t, *raw[k]))
    days = [d for d in sorted(by) if len(by[d]) >= 300]
    out = []; ranges = []
    for i, d in enumerate(days):
        bars = by[d]
        am = [b for b in bars if b.t.time() < dt.time(10, 45)]
        rng = max(b.h for b in am) - min(b.l for b in am)
        ref = st.median(ranges[-20:]) if len(ranges) >= 10 else None
        prev = [by[days[i - 1]][0]] if i else []
        if ref: out.append((d, prev, bars, ref))
        ranges.append(rng)
    _DAYS[name] = out
    return out

def run_cfg(name, cfg, period='all'):
    """cfg: dict with k_sl, rr (or 'fair'), plus FPParams fields. Returns list of (day, setup, side, opened, points, risk0, reason)."""
    days = load(name); res = []
    cfg = dict(cfg); k_sl = cfg.pop('k_sl'); rr = cfg.pop('rr'); fixed = cfg.pop('fixed_sl', None)
    for d, prev, bars, ref in days:
        if period == 'train' and d >= SPLIT: continue
        if period == 'test' and d < SPLIT: continue
        sl = fixed if fixed else k_sl * ref
        p = FPParams(sl=sl, tp=(rr * sl if rr != 'fair' else 1.5 * sl), big_open=sl, target='fair' if rr == 'fair' else 'static', **cfg)
        s = run_day(prev, bars, p)
        for t in s.trades:
            res.append((d, t.setup, t.side, t.opened, t.points, t.risk0, t.reason, t.entry, t.tp))
    return res

def metrics(name, trades, ndays):
    c = COST[name]
    if not trades: return dict(n=0, R=0, avgR=0, win=0, pf=0, dd=0, green=0, perday=0)
    rs = [(p - c) / r for (_, _, _, _, p, r, *_ ) in trades]
    byd = collections.defaultdict(float)
    for t, x in zip(trades, rs): byd[t[0]] += x
    cum = peak = dd = 0
    for d in sorted(byd): cum += byd[d]; peak = max(peak, cum); dd = min(dd, cum - peak)
    gp = sum(x for x in rs if x > 0); gl = -sum(x for x in rs if x < 0)
    return dict(n=len(rs), R=sum(rs), avgR=st.mean(rs), win=100 * sum(p > 0 for (_, _, _, _, p, *_ ) in trades) / len(rs), pf=gp / gl if gl else 99,
                dd=dd, green=100 * sum(v > 0 for v in byd.values()) / ndays, red=100 * sum(v < 0 for v in byd.values()) / ndays, perday=sum(rs) / ndays)

def ndays(name, period):
    return sum(1 for d, *_ in load(name) if (period == 'all' or (period == 'train') == (d < SPLIT)))

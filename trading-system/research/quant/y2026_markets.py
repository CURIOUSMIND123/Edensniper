"""The last 3 months (9 July - 9 October 2026): the indicator's strategy (original rules + the volume check, as the
alert program trades it) on gold, crude oil and currency pairs, compared with Nifty and Sensex.

    python y2026_markets.py            (needs fetch_fx.py first)

These markets trade almost around the clock, so a 'session' of the same length as the NSE one (6 h 15 min) is cut out
of each day, starting at 9:00 in India (when MCX opens), 8:00 in London or 8:00 in New York; the strategy runs on it
unchanged: the CPR from the previous session's high, low and close, the CPR Magnet in the first minute, the breakout
of the first 15 minutes until 45 minutes in, the 3-day volume lines until an hour before the end, out 15 minutes
before the end, the 30-day volume profile and the volume check on the market's own (tick) volume.
Costs a trade: gold $0.40, crude $0.03, EUR/USD and GBP/USD 1.0-1.2 pips, USD/JPY 1.2 pips (about the spread plus
commission). Results in % of the price (the sum of each trade's move after costs), so markets compare; Nifty and
Sensex the same way, over the same 3 months; by month.
"""
import collections, datetime as dt, json, sys, zoneinfo
import numpy as np
sys.path.insert(0, '../../alerts')
import cprb_alerts as A

SPECS = {'XAUUSD': ('gold', 0.8, 0.40), 'LIGHTCMDUSD': ('WTI crude', 0.015, 0.03), 'EURUSD': ('EUR/USD', 0.00025, 0.00010),
         'GBPUSD': ('GBP/USD', 0.0003, 0.00012), 'USDJPY': ('USD/JPY', 0.03, 0.012)}
SESSIONS = {'India 9:00': ('Asia/Kolkata', 9), 'London 8:00': ('Europe/London', 8), 'New York 8:00': ('America/New_York', 8)}
FIRST, LAST = dt.date(2026, 5, 15), dt.date(2026, 10, 9)
START = '2026-07-09'

def sessions(sym, tz, hour):
    z = np.load(f'../.cache/fx_{sym}.npz'); t = z['t']
    sess, vol = {}, {}
    d = FIRST
    while d <= LAST:
        if d.weekday() < 5:
            s0 = int(dt.datetime(d.year, d.month, d.day, hour, tzinfo=zoneinfo.ZoneInfo(tz)).timestamp()) // 60
            a, b = np.searchsorted(t, s0), np.searchsorted(t, s0 + 375)
            if b - a >= 300:
                k = (t[a:b] - s0).astype(int) + A.OPEN
                ds = str(d)
                sess[ds] = [(int(m), float(o), float(h), float(l), float(c)) for m, o, h, l, c in zip(k, z['o'][a:b], z['h'][a:b], z['l'][a:b], z['c'][a:b])]
                vol[ds] = {int(m): float(v) for m, v in zip(k, z['v'][a:b])}
        d += dt.timedelta(days=1)
    return sess, vol

def run(sym, sess, vol, vcheck):
    name, binw, cost = SPECS[sym]
    spec = dict(name=sym, key=sym, bin=binw, cost=cost, lot=1, step=binw * 10, cap=0)
    A.RULES, A.SWEEP, A.VOLCHECK = 'classic', False, vcheck
    out = []
    for d in sorted(sess):
        if d < START: continue
        try: cx = A.context(spec, sess, vol, d)
        except SystemExit: continue
        cx['tvol'] = vol.get(d, {})
        for t in A.day_trades(cx, sess[d], 929, True, False, 'classic'):
            if t['taken']: out.append(dict(d=d, pct=100 * t['exit']['pnl'] / t['e'], src=t['src']))
    return out

def stats(ts):
    ts = [t for t in ts if t['d'] >= START]
    p = [t['pct'] for t in ts]
    mo = collections.defaultdict(float)
    for t in ts: mo[t['d'][5:7]] += t['pct']
    eq = pk = dd = 0
    for v in p: eq += v; pk = max(pk, eq); dd = min(dd, eq - pk)
    return dict(n=len(p), w=sum(v > 0 for v in p), net=sum(p), dd=dd, mo=dict(mo))

def line(label, s):
    return (f"  {label:30} {s['n']:3} trades ({s['n'] / 3:4.1f}/month), {100 * s['w'] / max(1, s['n']):3.0f}% won | net {s['net']:+6.2f}% of price, "
            f"worst fall {s['dd']:5.2f}%, per trade {s['net'] / max(1, s['n']):+.3f}% | by month " +
            ', '.join(f"{k}: {v:+.2f}%" for k, v in sorted(s['mo'].items())))

def index_line():
    out = []
    for nm in ('nifty', 'sensex'):
        R = json.load(open(f'../.cache/report_{nm}.json'))['trades']['default (original + volume check)']
        daily = json.load(open(f'../.cache/{nm}_daily.json'))
        close = {d: (v[4] if isinstance(v, list) else v['close']) for d, v in daily.items()}
        out.append((nm.capitalize(), [dict(d=t['d'], pct=100 * t['pnl'] / close[t['d']]) for t in R]))
    return out

if __name__ == '__main__':
    print("9 July - 9 October 2026, original rules + volume check, in % of the price after costs")
    for nm, ts in index_line(): print(line(f"{nm} (NSE / BSE session)", stats(ts)))
    res = {}
    for sym, (name, _, _) in SPECS.items():
        try: np.load(f'../.cache/fx_{sym}.npz')
        except FileNotFoundError: print(f"\n{name}: no data"); continue
        print(f"\n{name} ({sym})")
        for sl, (tz, hour) in SESSIONS.items():
            sess, vol = sessions(sym, tz, hour)
            for vc in (True, False):
                s = stats(run(sym, sess, vol, vc)); res[(sym, sl, vc)] = s
                print(line(f"{sl}{'' if vc else ', no volume check'}", s))
    json.dump({f"{k[0]}|{k[1]}|{k[2]}": v for k, v in res.items()}, open('../.cache/markets_2026.json', 'w'))

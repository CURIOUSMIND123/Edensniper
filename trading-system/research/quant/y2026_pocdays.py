"""2026 only: the volume POC from the last 1 / 2 / 3 / 7 / 15 / 30 sessions, or no POC filter at all, on the
indicator's default (original rules + the volume check) and without the volume check.

    python y2026_pocdays.py nifty        (or sensex)

The POC (the price where the most NIFTYBEES volume traded over those sessions) is the filter on the CPR Magnet and
the 9:30 breakout and its reversal: buys only above it, sells only below. Everything else as the alert program
trades it. January-June and July-October separately. Result: the alert program and the indicator now use 15 sessions
on Nifty and no POC filter on Sensex (POC_DAYS in alerts/cprb_alerts.py).
"""
import collections, sys
import y2026 as Y
sys.path.insert(0, '../../alerts')
import cprb_alerts as A

NM, D26, H1 = Y.B.name, Y.D26, Y.H1
spec = A.SPEC[NM]; sess = {d: Y.one[d] for d in Y.days}
vol = collections.defaultdict(dict)
for k, v in Y.bees.items(): vol[k[:10]][int(k[11:13]) * 60 + int(k[14:16])] = v[4]
daily = {d: Y.DAY[d] for d in Y.days}
CX = {d: A.context(spec, sess, vol, d, daily) for d in D26}
for d in D26: CX[d]['tvol'] = vol.get(d, {})
HIST = {}
def hist(d):
    if d not in HIST: HIST[d] = A.day_hist(sess[d], vol.get(d, {}), spec['bin'])
    return HIST[d]
DAYS = [d for d in Y.days if len(sess[d]) >= 300]

def poc(d, n):
    prev = [x for x in DAYS if x < d][-n:]
    return A.poc_va(*A.combine([hist(x) for x in prev]), spec['bin'])[0]

def trades(n, vcheck):
    """The taken trades with the POC of the last n sessions (0: no POC filter)."""
    A.RULES, A.SWEEP, A.VOLCHECK = 'classic', False, vcheck
    ts = []
    for d in D26:
        cx = CX[d]; keep = cx['poc']
        cx['poc'] = None if n == 0 else poc(d, n)
        ts += [dict(d=d, m=t['m'], pnl=t['exit']['pnl'], src=t['src']) for t in A.day_trades(cx, Y.one[d], 929, True, False, 'classic') if t['taken']]
        cx['poc'] = keep
    return ts

def run(n, vcheck):
    ts = trades(n, vcheck)
    p = [t['pnl'] for t in ts]; a = sum(t['pnl'] for t in ts if t['d'] in H1)
    eq = pk = dd = 0
    for v in p: eq += v; pk = max(pk, eq); dd = min(dd, eq - pk)
    plan = [t for t in ts if t['src'] != 'VOLUME LINE']
    return dict(n=len(p), w=sum(v > 0 for v in p), net=sum(p), a=a, b=sum(p) - a, dd=dd, np=len(plan), plan=sum(t['pnl'] for t in plan))

if __name__ == '__main__':
    rs = {'nifty': 32.5, 'sensex': 10.0}[NM] * 5
    for vc in (True, False):
        print(f"\n{NM.upper()} 2026, original rules {'+ volume check (default)' if vc else 'without the volume check'}")
        base = None
        for n in (30, 15, 7, 3, 2, 1, 0):
            r = run(n, vc)
            if base is None: base = r
            tag = '' if n == 30 else ('  <- better in both halves' if r['a'] > base['a'] and r['b'] > base['b'] else '')
            print(f"  {('POC of the last ' + str(n) + ' sessions') if n else 'no POC filter':30} {r['n']:3} trades, {100 * r['w'] / r['n']:3.0f}% won | "
                  f"net {r['net']:+7,.0f} (Jan-Jun {r['a']:+6,.0f}, Jul-Oct {r['b']:+6,.0f}) worst fall {r['dd']:6,.0f} | "
                  f"Magnet / breakout {r['np']:3} trades {r['plan']:+6,.0f} | 5 lots Rs {r['net'] * rs:+,.0f}{tag}")

"""2026 only: the indicator's default (original rules + the volume check) with every stop held to at most 20 / 30 / 45
Nifty points (60 / 100 / 150 Sensex), on the same signals. The alert program's own trade logic (STOP_MAX, STOP_MODE).

    python y2026_stopcap.py nifty        (or sensex)

pull  a wider stop is moved in to the limit; book half (0.25x) and the trailing distance (1x) scale to the new stop
stop  a wider stop is moved in; book half and trailing as before (from the setup's own stop)
skip  trades whose own stop is wider are not taken
Also without the volume check. Trades, won, average win / loss, net points, January-June / July-October, worst fall,
how many hit the stop, and rupees at 5 lots (delta 0.5; Nifty Rs 32.5, Sensex Rs 10 a point a lot).
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
CAPS = {'nifty': (20, 30, 45), 'sensex': (60, 100, 150)}[NM]
RS = {'nifty': 32.5, 'sensex': 10.0}[NM] * 5

def run(cap, mode, vc):
    A.RULES, A.SWEEP, A.VOLCHECK, A.STOP_MAX, A.STOP_MODE = 'classic', False, vc, {NM: cap}, mode
    ts = [dict(d=d, src=t['src'], pnl=t['exit']['pnl'], why=t['exit']['why'], risk=t['side'] * (t['e'] - t['stp0']))
          for d in D26 for t in A.day_trades(CX[d], Y.one[d], 929, True, False, 'classic') if t['taken']]
    p = [t['pnl'] for t in ts]; w = [v for v in p if v > 0]; l = [v for v in p if v <= 0]
    eq = pk = dd = 0
    for v in p: eq += v; pk = max(pk, eq); dd = min(dd, eq - pk)
    a = sum(t['pnl'] for t in ts if t['d'] in H1)
    return dict(n=len(p), w=len(w), avg_w=sum(w) / max(1, len(w)), avg_l=sum(l) / max(1, len(l)), net=sum(p), a=a, b=sum(p) - a,
                dd=dd, worst=min(p, default=0), stops=sum(t['why'] == 'stop' for t in ts), risk=sum(t['risk'] for t in ts) / max(1, len(ts)))

def show(label, r, base=None):
    tag = '' if base is None else ('  <- better in both halves' if r['a'] > base['a'] and r['b'] > base['b'] else '')
    print(f"  {label:34} {r['n']:4} tr {100 * r['w'] / max(1, r['n']):3.0f}% won | stop avg {r['risk']:4.0f}, hit {r['stops']:3} | "
          f"avg win {r['avg_w']:+5.0f} loss {r['avg_l']:+5.0f} worst {r['worst']:+5.0f} | net {r['net']:+7,.0f} (Jan-Jun {r['a']:+6,.0f}, "
          f"Jul-Oct {r['b']:+6,.0f}) fall {r['dd']:6,.0f} | 5 lots Rs {r['net'] * RS:+,.0f}{tag}")

if __name__ == '__main__':
    for vc in (True, False):
        base = run(0, 'pull', vc)
        print(f"\n{NM.upper()} 2026, original rules {'WITH' if vc else 'WITHOUT'} the volume check")
        show("each setup's own stop (now)", base)
        for cap in CAPS:
            for mode, txt in (('pull', 'moved in, half/trail scaled'), ('stop', 'moved in, half/trail as before'), ('skip', 'wider: skipped')):
                show(f"stop <= {cap}: {txt}", run(cap, mode, vc), base)

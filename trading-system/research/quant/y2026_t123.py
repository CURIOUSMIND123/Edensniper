"""2026 only: the same calls with targets T1 / T2 / T3 at the next price levels and a smaller stop, instead of
'book half at 0.25R, stop to entry, trail'.

    python y2026_t123.py nifty        (or sensex)

Entries are the alert program's (default settings, one trade at a time); only the exits change, and with them which
later signals are free to be taken.
Targets: the price levels beyond the entry in the trade's direction, nearest first: the CPR (top, pivot, bottom),
the floor pivots R1-R3 / S1-S3, yesterday's high / low, the 15-minute high / low (for entries after 9:30), the 3-day
volume lines and the volume POC. Levels less than 0.05% from the entry or from the previous target are skipped.
T1 / T2 / T3 = the first three (missing ones: one more step of the same size). A third of the position is booked at
each; out by 3:15.
Stops:
  setup     as now (0.3% Magnet, the 15-minute range, the previous volume line)
  halfT2    half the distance to T2
  user      the distance to T1, or half the distance to T2 when T2 is more than twice as far as T1
  swing     beyond the lowest low (BUY) / highest high (SELL) of the 15 one-minute candles before the entry, plus
            0.03% (so a liquidity sweep of that low doesn't take it out)
  user+sw   'user', moved beyond that swing (plus 0.03%) when the swing lies at most 50% further away
  early     as now (stop and T1 = 0.25 x the stop, where half is booked now), then T2 / T3 at the next two levels
            beyond T1 instead of trailing
After the targets:
  A         after T1 the stop goes to the entry, after T2 to T1
  B         after T2 the stop goes to the entry (none after T1)
  C         the stop never moves
Costs: 4 Nifty / 12 Sensex points a trade.
"""
import collections, json, sys
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
CUR = {}
GAP = 0.0005

def levels(cx, c1, start):
    lv, P, yh, yl = cx['lv'], cx['lv']['p'], cx['yh'], cx['yl']
    out = [lv['top'], P, lv['bot'], yh, yl, 2 * P - yl, 2 * P - yh, P + (yh - yl), P - (yh - yl),
           yh + 2 * (P - yl), yl - 2 * (yh - P)] + list(cx['lines'])
    if cx.get('poc') is not None: out.append(cx['poc'])
    if start >= A.RANGE_END:
        first = [x for x in c1 if x[0] < A.RANGE_END]
        out += [max(x[2] for x in first), min(x[3] for x in first)]
    return out

def targets(cx, c1, side, e, start, R0):
    t = []
    for L in sorted((L for L in levels(cx, c1, start) if side * (L - e) >= GAP * e), key=lambda L: side * (L - e)):
        if not t or side * (L - t[-1]) >= GAP * e:
            t.append(L)
        if len(t) == 3: break
    if not t: t = [e + side * R0]
    while len(t) < 3:
        step = (t[-1] - (t[-2] if len(t) > 1 else e))
        t.append(t[-1] + step)
    return t

def swing(c1, side, e, start):
    before = [x for x in c1 if start - 16 <= x[0] < start]
    if not before: return None
    ext = min(x[3] for x in before) if side > 0 else max(x[2] for x in before)
    s = ext - side * 0.0003 * e
    return s if side * (e - s) >= GAP * e else None

def stop_for(kind, side, e, T, setup_stp, sw):
    d1, d2 = side * (T[0] - e), side * (T[1] - e)
    if kind == 'setup': return setup_stp
    if kind == 'halfT2': return e - side * 0.5 * d2
    user = e - side * (0.5 * d2 if d2 > 2 * d1 else d1)
    if kind == 'user': return user
    if kind == 'swing': return sw if sw is not None else user
    if kind == 'user+sw':
        du = side * (e - user)
        if sw is not None and du < side * (e - sw) <= 1.5 * du: return sw
        return user
    raise ValueError(kind)

def walk(c1, side, e, start, stp, T, mode, cost):
    got, ev, w = [], [], 1 / 3
    for m, o, h, l, c in c1:
        if m < start: continue
        for px in A.path(o, h, l, c):
            if side * (px - stp) <= 0:
                pnl = sum(got) * w + (3 - len(got)) * w * side * (stp - e)
                return dict(ev=ev, stp=stp, exit=A.done(m, stp, 'stop' if not got else 'stop after T%d' % len(got), pnl - cost))
            while len(got) < 3 and side * (px - T[len(got)]) >= 0:
                got.append(side * (T[len(got)] - e))
                ev.append(dict(m=m, kind='t%d' % len(got), px=T[len(got) - 1], pts=got[-1], stp=stp))
                if len(got) == 3:
                    return dict(ev=ev, stp=stp, exit=A.done(m, T[2], 'T3', sum(got) * w - cost))
                if mode == 'A': stp = e if len(got) == 1 else T[0]
                elif mode == 'B' and len(got) == 2: stp = e
        if m >= A.OUT:
            pnl = sum(got) * w + (3 - len(got)) * w * side * (c - e)
            return dict(ev=ev, stp=stp, exit=A.done(m, c, '3:15 time exit', pnl - cost))
    pnl = sum(got) * w + (3 - len(got)) * w * side * (c1[-1][4] - e)
    return dict(ev=ev, stp=stp, exit=A.done(c1[-1][0], c1[-1][4], 'close', pnl - cost))

def make(kind, mode):
    def generic(c1, side, e, start, setup_stp, cost):
        cx = CUR['cx']; R0 = side * (e - setup_stp)
        if kind == 'early':
            t1 = e + side * 0.25 * R0
            T = [t1] + targets(cx, c1, side, t1, start, R0)[:2]
            stp = setup_stp
        else:
            T = targets(cx, c1, side, e, start, R0)
            stp = stop_for(kind, side, e, T, setup_stp, swing(c1, side, e, start))
        r = walk(c1, side, e, start, stp, T, mode, cost)
        r['T'], r['stp0x'] = T, stp
        return r
    mag = lambda c1, side, e, edge, over, cost, risk=None, R=None, start=556: generic(c1, side, e, start, e - side * 0.003 * e, cost)
    bo = lambda c1, side, e, start, stp, over, cost, R=None: generic(c1, side, e, start, stp, cost)
    vl = lambda c1, side, e, start, stp, tgt, x, tgt2, over, cost: generic(c1, side, e, start, stp, cost)
    return mag, bo, vl

def run(kind=None, mode=None):
    A.RULES, A.SWEEP, A.VOLCHECK = 'classic', False, {'nifty': False, 'sensex': True}
    orig = A.run_magnet, A.run_breakout, A.run_vol
    if kind: A.run_magnet, A.run_breakout, A.run_vol = make(kind, mode)
    out = []
    try:
        for d in D26:
            CUR['cx'] = CX[d]
            for t in A.day_trades(CX[d], Y.one[d], 929, True, False, 'classic'):
                if t['taken'] and t['exit']:
                    hit = sum(1 for e_ in t['ev'] if e_['kind'] in ('t1', 't2', 't3'))
                    risk = abs(t['e'] - t.get('stp0x', t['stp0']))
                    out.append(dict(d=d, pnl=t['exit']['pnl'], hit=hit, risk=risk, src=t['src'], m=t['m'], x=t['exit']['m']))
    finally:
        A.run_magnet, A.run_breakout, A.run_vol = orig
    return out

def stats(ts):
    p = [t['pnl'] for t in ts]; a = sum(t['pnl'] for t in ts if t['d'] in H1)
    eq = pk = dd = 0
    for v in p: eq += v; pk = max(pk, eq); dd = min(dd, eq - pk)
    return dict(n=len(p), w=sum(v > 0 for v in p), net=sum(p), a=a, b=sum(p) - a, dd=dd, worst=min(p, default=0),
                risk=sum(t['risk'] for t in ts) / max(1, len(ts)), t1=sum(t['hit'] >= 1 for t in ts), t2=sum(t['hit'] >= 2 for t in ts),
                t3=sum(t['hit'] >= 3 for t in ts), held=sum(t['x'] - t['m'] for t in ts) / max(1, len(ts)))

def line(label, s, base=None):
    tag = ''
    if base: tag = '  <- better in both halves' if s['a'] > base['a'] and s['b'] > base['b'] else ''
    hits = f" | T1 {s['t1']} T2 {s['t2']} T3 {s['t3']}" if s['t1'] else ''
    print(f"  {label:24} {s['n']:3} trades, {100 * s['w'] / max(1, s['n']):3.0f}% won | net {s['net']:+7,.0f} (Jan-Jun {s['a']:+6,.0f}, Jul-Oct {s['b']:+6,.0f}) "
          f"| worst trade {s['worst']:+5.0f}, worst fall {s['dd']:6,.0f} | stop avg {s['risk']:4.0f} | held {s['held']:3.0f} min{hits}{tag}")

if __name__ == '__main__':
    print(f"{NM.upper()} 2026, default entries; exits: now vs T1 / T2 / T3 at the next levels (thirds), costs in")
    base = stats(run())
    line('now (half, entry, trail)', base)
    res = {}
    for kind in ('early', 'setup', 'halfT2', 'user', 'swing', 'user+sw'):
        for mode in (('A',) if kind == 'early' else ('A', 'B', 'C')):
            s = stats(run(kind, mode)); res[f'{kind}|{mode}'] = s
            line(f'stop {kind}, {mode}', s, base)
    json.dump(dict(base=base, res=res), open(f'../.cache/t123_{NM}.json', 'w'))

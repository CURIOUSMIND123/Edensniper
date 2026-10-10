"""2026 only: scalps taken AT volume zones and Fibonacci levels (instead of using them as filters).

    python y2026_levels.py nifty        (or sensex)

Levels for each day (from y2026.py, all known before the open):
  vol30 / vol15  point of control, value-area high / low and high-volume nodes of the last 30 / 15 sessions
                 (NIFTYBEES real volume)
  fib            the last 30 sessions' Fibonacci retracements (23.6-78.6%) plus that high and low
Every time a 1-minute candle crosses a level: trade the break or the bounce, target 15-30 points, stop 10-20
(Nifty-sized, scaled for Sensex), out after 10 or 30 minutes or at 15:15, at most 5 trades a day, entries
9:20-14:30. Optional filter: only in the direction of price vs the 30-day volume POC. Costs: 4 Nifty / 12 Sensex.
Each version is shown for January-June and July-9 October 2026 separately.
"""
import collections, itertools, json, sys
import y2026 as Y

B, one, LV, COST = Y.B, Y.one, Y.LV, Y.COST
REF = 22500.0

def path(o, h, l, c): return (o, l, h, c) if c >= o else (o, h, l, c)

def levels_for(d, kind):
    if kind == 'fib': return Y.FIB[d]['levels']
    p = Y.PROF30[d] if kind == 'vol30' else Y.PROF15[d]
    return [p['poc'], p['vah'], p['val']] + p['hvn']

def day(d, P):
    kind, mode, T, S, H, flt = P
    lvls = levels_for(d, kind); poc = Y.PROF30[d]['poc']
    out, pos, prev = [], None, one[d][0][4]
    for m, o, h, l, c in one[d]:
        if m < 560: prev = c; continue
        pts = (prev,) + path(o, h, l, c); prev = c; k = 0
        while k < len(pts) - 1:
            a, b = pts[k], pts[k + 1]
            if pos is None:
                if len(out) >= 5 or m >= 870: break
                hit = None
                for L in lvls:
                    if a < L <= b or a > L >= b:
                        if hit is None or abs(L - a) < hit[1]: hit = (L, abs(L - a), 1 if b > a else -1)
                if hit is None: k += 1; continue
                L, _, cross = hit
                side = cross if mode == 'break' else -cross
                e = L if k > 0 else b
                if flt == 'poc' and side * (e - poc) <= 0: k += 1; continue
                sc = e / REF
                pos = dict(side=side, e=e, stp=e - side * S * sc, tgt=e + side * T * sc, m0=m)
                if k == 0: k += 1
                else: pts = pts[:k] + (L,) + pts[k + 1:]
                continue
            sd, e = pos['side'], pos['e']
            if sd * (b - pos['stp']) <= 0: out.append((d, sd * (pos['stp'] - e) - COST)); pos = None
            elif sd * (b - pos['tgt']) >= 0: out.append((d, sd * (pos['tgt'] - e) - COST)); pos = None
            k += 1
        if pos is not None and ((H and m >= pos['m0'] + H) or m >= 915):
            out.append((d, pos['side'] * (c - pos['e']) - COST)); pos = None
        if m >= 915: break
    return out

GRID = list(itertools.product(('vol30', 'vol15', 'fib'), ('break', 'bounce'), (15, 20, 25, 30), (10, 15, 20), (10, 30, 0), ('none', 'poc')))

def evaluate(P):
    ts = [t for d in Y.D26 for t in day(d, P)]
    h1 = [p for d, p in ts if d in Y.H1]; h2 = [p for d, p in ts if d not in Y.H1]
    return dict(P=list(P), n1=len(h1), w1=sum(p > 0 for p in h1), net1=sum(h1), n2=len(h2), w2=sum(p > 0 for p in h2), net2=sum(h2))

if __name__ == '__main__':
    res = [evaluate(P) for P in GRID]
    json.dump(res, open(f'../.cache/y2026_levels_{B.name}.json', 'w'))
    print(f"{B.name.upper()} 2026: {len(res)} level-scalp versions")
    both = [r for r in res if r['net1'] > 0 and r['net2'] > 0 and r['n1'] >= 20 and r['n2'] >= 15]
    print(f"  made money in Jan-Jun AND Jul-Oct (20+ / 15+ trades): {len(both)}")
    for r in sorted(both, key=lambda r: -(r['net1'] + r['net2']))[:10]:
        n = r['n1'] + r['n2']; w = r['w1'] + r['w2']
        print(f"    {str(r['P']):42} {n} tr {w}W/{n-w}L ({100*w/n:.0f}%) net {r['net1'] + r['net2']:+,.0f} (Jan-Jun {r['net1']:+,.0f}, Jul-Oct {r['net2']:+,.0f})")
    hi = [r for r in res if r['n1'] + r['n2'] >= 30 and (r['w1'] + r['w2']) / (r['n1'] + r['n2']) >= 0.8]
    print(f"  won 80%+ in 2026 (30+ trades): {len(hi)}; of those made money: {sum(r['net1'] + r['net2'] > 0 for r in hi)}")

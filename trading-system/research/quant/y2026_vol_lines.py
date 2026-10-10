"""2026 only: volume-line breakouts on Nifty / Sensex (break a high-volume line, ride to the next one).

    python y2026_vol_lines.py nifty        (or sensex)

Volume lines rebuilt every morning from the last 3 / 7 / 15 sessions (NIFTYBEES 1-minute volume spread over the
index's 1-minute range, as in y2026.py): the point of control plus every high-volume peak (local top of the smoothed
profile in its top 30%), lines closer than 0.15% merged. Entry: a 5-minute close through a line (the previous close
was on the other side), 9:30-14:30, at that close. Target: the next line. Stop: 0.5 or 1 x the 5-minute ATR behind
the broken line, or at the previous line. Skip when the target is less than 1 / 1.5 / 2 x the stop away. One trade
at a time, out by 15:15. Costs 4 Nifty / 12 Sensex points. January-June and July-9 October shown separately.
"""
import itertools
import numpy as np
import y2026 as Y

B, one, five, COST, D26, H1 = Y.B, Y.one, Y.five, Y.COST, Y.D26, Y.H1

def lines(d, n):
    ds = Y.days[Y.IDX[d] - n:Y.IDX[d]]
    base = min(Y.VH[x][0] for x in ds); top = max(Y.VH[x][0] + len(Y.VH[x][1]) for x in ds)
    p = np.zeros(top - base)
    for x in ds: b0, h = Y.VH[x]; p[b0 - base:b0 - base + len(h)] += h
    sm = np.convolve(p, np.ones(3) / 3, 'same'); thr = np.percentile(sm[sm > 0], 70)
    pk = {i for i in range(1, len(sm) - 1) if sm[i] >= thr and sm[i] >= sm[i - 1] and sm[i] >= sm[i + 1]} | {int(np.argmax(p))}
    out = []
    for x in sorted((base + i + 0.5) * Y.BIN for i in pk):
        if out and x - out[-1] <= 0.0015 * x: out[-1] = (out[-1] + x) / 2
        else: out.append(x)
    return out
LINES = {(d, n): lines(d, n) for d in D26 for n in (3, 7, 15)}

def path(o, h, l, c): return (o, l, h, c) if c >= o else (o, h, l, c)

def day(d, n, stop_kind, rr, times=False, detail=False):
    lv = LINES[(d, n)]; b5 = five[d]; out = []; free = 0
    for j in range(1, len(b5)):
        m0, o, h, l, c = b5[j]; pc = b5[j - 1][4]
        if m0 < 570 or m0 + 5 > 870 or m0 < free: continue
        for x in lv:
            side = 1 if pc < x <= c else -1 if pc > x >= c else 0
            if not side: continue
            nxt = [y for y in lv if side * (y - x) > 0]
            if not nxt: break
            tgt = min(nxt, key=lambda y: abs(y - x))
            if stop_kind == 'prev':
                prv = [y for y in lv if side * (x - y) > 0]
                if not prv: break
                stp = max(prv) if side > 0 else min(prv)
            else:
                stp = x - side * (0.5 if stop_kind == 'atr0.5' else 1.0) * Y.PA.ATR[(d, j)]
            e = c; risk, reward = side * (e - stp), side * (tgt - e)
            if risk <= 0 or reward < rr * risk: break
            pnl, mx = None, None
            for m, op, hh, ll, cc in one[d]:
                if m < m0 + 5: continue
                for px in path(op, hh, ll, cc):
                    if side * (px - stp) <= 0: pnl, mx = side * (stp - e), m; break
                    if side * (px - tgt) >= 0: pnl, mx = side * (tgt - e), m; break
                if pnl is None and m >= 915: pnl, mx = side * (cc - e), m
                if pnl is not None: break
            if pnl is None: pnl, mx = side * (one[d][-1][4] - e), one[d][-1][0]
            if detail: out.append(dict(d=d, src='VOL', side=side, m=m0 + 5, e=e, stp=stp, tgt=tgt, mx=mx, pnl=pnl - COST,
                                       why='target' if abs(side * (tgt - e) - pnl) < 1e-6 else 'stop' if abs(side * (stp - e) - pnl) < 1e-6 else '3:15'))
            else: out.append((d, pnl - COST, m0 + 5, mx) if times else (d, pnl - COST))
            free = mx + 1
            break
    return out

if __name__ == '__main__':
    print(f"{B.name.upper()} 2026 volume-line breakouts ({D26[0]} to {D26[-1]})")
    pos_both = 0; n_all = 0
    for n, sk, rr in itertools.product((3, 7, 15), ('atr0.5', 'atr1', 'prev'), (1.0, 1.5, 2.0)):
        ts = [t for d in D26 for t in day(d, n, sk, rr)]
        a = sum(p for d, p in ts if d in H1); b = sum(p for d, p in ts if d not in H1); w = sum(p > 0 for _, p in ts)
        n_all += 1; pos_both += a > 0 and b > 0
        print(f"  {n:2}-session lines, stop {sk:6}, target >= {rr}x stop: {len(ts):4} trades, {w} won / {len(ts)-w} lost, "
              f"net {a + b:+8,.0f} (Jan-Jun {a:+7,.0f}, Jul-Oct {b:+7,.0f})" + ('   <- both halves +' if a > 0 and b > 0 else ''))
    print(f"  {pos_both} of {n_all} versions made money in both halves of 2026")

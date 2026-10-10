"""2026 only: trading the pivot levels (S3-S1, BC / P / TC, R1-R3), and what the indicator's filters cost on big days.

    python y2026_pivots.py nifty        (or sensex)

1. The last 7 sessions: what the indicator did, and which rule blocked each day.
2. The CPR Breakout part with its filters switched off one by one (opening-gap direction, today's CPR vs
   yesterday's, the 30-day POC side): every 2026 day, and the big days only (range in the top third).
3. Pivot-level trades: a 5-minute close through a pivot level -> trade that way.
     levels   core (S2, S1, BC, P, TC, R1, R2) / full (S3 ... R3) / full + the 3-day volume lines
     start    9:20 or 9:30; last entry 14:30; out by 15:15
     stop     the previous level / halfway back to it / 0.5 x the 5-minute ATR behind the broken level
     target   the next level / the level after it / ladder (half at the next, stop to the broken level, rest to
              the one after) / trail (stop 1R behind the best price after +1R, else out at 15:15)
     filter   none / with the day (above the CPR: buys only, below: sells only) / with the open (above the
              day's open: buys only) / with today's CPR vs yesterday's
     reward   skip when the first target is less than 0 / 1 / 1.5 x the stop away
   Levels closer than 0.05% of price are merged. One trade at a time. Costs 4 Nifty / 12 Sensex points.
4. The best pivot versions added to the indicator (one book), January-June and July-9 October 2026.
"""
import collections, itertools, json, sys
import y2026 as Y, y2026_vol_lines as V, y2026_improve as I, cpr_orb as C, cpr_orb_winrate as W

one, five, LV, DAY, COST = Y.one, Y.five, Y.LV, Y.DAY, Y.COST
D26, H1 = Y.D26, Y.H1
path = I.path

# ---------------- 2. the breakout with filters off ----------------
def breakout(d, gap=True, rel=True, poc=True):
    lv = LV[d]; first = [x for x in one[d] if x[0] < 570]; orh, orl = max(x[2] for x in first), min(x[3] for x in first)
    f = W.FEAT[d]; pc = Y.PROF30[d]['poc']
    ok = lambda s, e: not poc or s * (e - pc) > 0
    for side, e, start, m in C.candidates(d, 'touch', orh, orl, 570):
        if m >= 600: break
        if (rel and side == -C.REL[d]) or (gap and f['gap'] != side) or not ok(side, e): continue
        stp = orl if side > 0 else orh; R = side * (e - stp)
        if R <= 0: continue
        pnl, mx = I.walk(d, side, e, start, stp, e + side * 0.25 * R, None, 1.0)
        out = [dict(d=d, src='BO', side=side, m=m, mx=mx, pnl=pnl)]
        if pnl <= 0:
            for s2, e2, st2, m2 in C.candidates(d, 'touch', orh, orl, mx + 1):
                if m2 >= 600: break
                if s2 != -side or not ok(s2, e2): continue
                stp2 = orl if s2 > 0 else orh; R2 = s2 * (e2 - stp2)
                if R2 <= 0: break
                p2, mx2 = I.walk(d, s2, e2, st2, stp2, e2 + s2 * 0.25 * R2, None, 1.0)
                out.append(dict(d=d, src='BO', side=s2, m=m2, mx=mx2, pnl=p2)); break
        return out
    return []

def plan(d, **kw):
    if LV[d]['rank'] < 1 / 3: return breakout(d, **kw)
    return I.magnet(d, 'edge') or breakout(d, **kw)

# ---------------- 3. pivot-level trades ----------------
def levels(d, kind):
    lv = LV[d]
    keys = ('s2', 's1', 'bot', 'p', 'top', 'r1', 'r2') if kind == 'core' else ('s3', 's2', 's1', 'bot', 'p', 'top', 'r1', 'r2', 'r3')
    xs = sorted([lv[k] for k in keys] + (V.LINES[(d, 3)] if kind == 'full+vol' else []))
    out = []
    for x in xs:
        if out and x - out[-1] <= 0.0005 * x: out[-1] = (out[-1] + x) / 2
        else: out.append(x)
    return out

LEV = {(d, k): levels(d, k) for d in D26 for k in ('core', 'full', 'full+vol')}

def follow(d, side, e, start, stp, tgt, tgt2, x, kind):
    """Exit on 1-minute candles. kind: next / next2 (single target) / ladder / trail."""
    half, best, R = None, e, side * (e - stp)
    for m, o, h, l, c in one[d]:
        if m < start: continue
        for px in path(o, h, l, c):
            if side * (px - stp) <= 0:
                rest = side * (stp - e); return (rest if half is None else (half + rest) / 2) - COST, m
            if kind in ('next', 'next2') and side * (px - tgt) >= 0: return side * (tgt - e) - COST, m
            if kind == 'ladder':
                if half is None and side * (px - tgt) >= 0:
                    if tgt2 is None: return side * (tgt - e) - COST, m
                    half = side * (tgt - e); stp = x
                if half is not None and side * (px - tgt2) >= 0: return (half + side * (tgt2 - e)) / 2 - COST, m
        best = max(best, h) if side > 0 else min(best, l)
        if kind == 'trail' and side * (best - e) >= R:
            ns = best - side * R
            if side * (ns - stp) > 0: stp = ns
        if m >= 915:
            rest = side * (c - e); return (rest if half is None else (half + rest) / 2) - COST, m
    rest = side * (one[d][-1][4] - e)
    return (rest if half is None else (half + rest) / 2) - COST, one[d][-1][0]

def piv_day(d, P):
    kind, t0, stop, tk, filt, rr = P
    lv = LEV[(d, kind)]; b5 = five[d]; out = []; free = 0; o_day = one[d][0][1]; L = LV[d]
    for j in range(1, len(b5)):
        m0, o, h, l, c = b5[j]; pc = b5[j - 1][4]
        if m0 < t0 or m0 + 5 > 870 or m0 < free: continue
        for x in lv:
            side = 1 if pc < x <= c else -1 if pc > x >= c else 0
            if not side: continue
            if filt == 'day' and not (side > 0 and c > L['top'] or side < 0 and c < L['bot']): break
            if filt == 'open' and side * (c - o_day) <= 0: break
            if filt == 'rel' and side == -C.REL[d]: break
            nxt = sorted((y for y in lv if side * (y - x) > 0), key=lambda y: abs(y - x))
            prv = sorted((y for y in lv if side * (x - y) > 0), key=lambda y: abs(y - x))
            if not nxt or (stop != 'atr' and not prv): break
            e = c
            stp = prv[0] if stop == 'prev' else (x + prv[0]) / 2 if stop == 'half' else x - side * 0.5 * Y.PA.ATR[(d, j)]
            tgt = nxt[1] if tk == 'next2' and len(nxt) > 1 else nxt[0]
            if tk == 'next2' and len(nxt) < 2: break
            tgt2 = nxt[1] if tk == 'ladder' and len(nxt) > 1 else None
            risk = side * (e - stp)
            if risk <= 0 or side * (nxt[0] - e) < rr * risk: break
            pnl, mx = follow(d, side, e, m0 + 5, stp, tgt, tgt2, x, tk)
            out.append(dict(d=d, src='PIV', side=side, m=m0 + 5, mx=mx, pnl=pnl)); free = mx + 1
            break
    return out

GRID = list(itertools.product(('core', 'full', 'full+vol'), (560, 570), ('prev', 'half', 'atr'), ('next', 'next2', 'ladder', 'trail'),
                              ('none', 'day', 'open', 'rel'), (0, 1.0, 1.5)))

def evaluate(P):
    ts = [t for d in D26 for t in piv_day(d, P)]
    a = sum(t['pnl'] for t in ts if t['d'] in H1); b = sum(t['pnl'] for t in ts) - a
    return dict(P=list(P), n=len(ts), w=sum(t['pnl'] > 0 for t in ts), a=a, b=b)

def show(label, ts):
    p = [t['pnl'] for t in ts]; w = [v for v in p if v > 0]; l = [v for v in p if v <= 0]
    a = sum(t['pnl'] for t in ts if t['d'] in H1)
    print(f"  {label:58} {len(p):4} tr {len(w):3}W/{len(l):<3}L won {sum(w):+8,.0f} lost {sum(l):+8,.0f} net {sum(p):+8,.0f} "
          f"(Jan-Jun {a:+7,.0f}, Jul-Oct {sum(p) - a:+7,.0f})")

if __name__ == '__main__':
    nm = Y.B.name.upper()
    VOL = {d: I.vol(d, 'fixed') for d in D26}
    print(f"{nm}: 1. the last 7 sessions")
    for d in D26[-7:]:
        o, h, l, c = DAY[d]; got = I.one_book(plan(d) + VOL[d])
        print(f"  {d} range {h - l:6,.0f}, open to close {c - o:+7,.0f}: indicator {len(got)} trades {sum(t['pnl'] for t in got):+6,.0f}"
              f" | breakout with no filters: {sum(t['pnl'] for t in breakout(d, False, False, False)):+6,.0f}")
    big = {d for d in D26 if (DAY[d][1] - DAY[d][2]) / DAY[d][3] >= sorted((DAY[x][1] - DAY[x][2]) / DAY[x][3] for x in D26)[len(D26) * 2 // 3]}
    print(f"\n{nm}: 2. the breakout part with filters off (whole plan, magnet unchanged); big days = {len(big)} widest-range days")
    for label, kw in (('as now (gap, CPR vs yesterday, POC)', {}), ('no POC filter', dict(poc=False)), ('no CPR-vs-yesterday filter', dict(rel=False)),
                      ('no gap filter', dict(gap=False)), ('no POC and no CPR-vs-yesterday', dict(poc=False, rel=False)),
                      ('no filters at all', dict(poc=False, rel=False, gap=False))):
        ts = [t for d in D26 for t in plan(d, **kw)]
        show(label, ts); show('   big days only', [t for t in ts if t['d'] in big])
    import multiprocessing as mp
    with mp.Pool() as pool: res = pool.map(evaluate, GRID, chunksize=8)
    json.dump(res, open(f'../.cache/pivots_{Y.B.name}.json', 'w'))
    print(f"\n{nm}: 3. pivot-level trades, {len(res)} versions")
    print(f"  made money in 2026: {sum(r['a'] + r['b'] > 0 for r in res)}; in both halves: {sum(r['a'] > 0 and r['b'] > 0 for r in res)}")
    for k, i in (('levels', 0), ('start', 1), ('stop', 2), ('target', 3), ('filter', 4), ('reward', 5)):
        g = collections.defaultdict(list)
        for r in res: g[r['P'][i]].append(r)
        print(f"  by {k:7}: " + ' | '.join(f"{v}: {sum(r['a'] > 0 and r['b'] > 0 for r in rs)}/{len(rs)} both halves +, avg net {sum(r['a'] + r['b'] for r in rs) / len(rs):+,.0f}"
                                         for v, rs in g.items()))
    print("  best 12 by net (positive in both halves):")
    for r in sorted([r for r in res if r['a'] > 0 and r['b'] > 0], key=lambda r: -(r['a'] + r['b']))[:12]:
        print(f"    {str(r['P']):52} {r['n']:4} tr {100 * r['w'] / max(1, r['n']):3.0f}% won, net {r['a'] + r['b']:+7,.0f} (Jan-Jun {r['a']:+6,.0f}, Jul-Oct {r['b']:+6,.0f})")

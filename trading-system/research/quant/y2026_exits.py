"""2026 only: the indicator's default (original rules + the volume check). The breakout and CPR Magnet trades book half
at 0.25x the risk and move the stop to entry; the breakout then trails the stop 1R behind the best price after +1R
(the Magnet rides to the CPR edge). What if we had booked the profit instead, or booked it and then traded again
from the stop?

    python y2026_exits.py nifty        (or sensex)

A. Booking the profit (breakout and Magnet trades; volume-line trades already go to a fixed target):
   all at 0.25R       the whole trade at the book-half level
   rest at 1R / 2R / 3R   book half at 0.25R, stop to entry, the rest at 1x / 2x / 3x the risk instead of trailing
                      (Magnet: the rest at the CPR edge, as now)
   rest to 3:15       book half, stop to entry, no trailing, the rest out at 3:15
   keep the stop      book half but leave the stop where it was (no stop to entry), the rest as now
   all at 1R / 2R     no booking half: the whole trade at 1x / 2x the risk, the original stop
B. Trading again when the stop at entry or the trailing stop closes a trade (before 2:30):
   reverse            the other way at that stop, stop just beyond the trade's best price, target 2x the stop
   enter again        the same way if price comes back 0.05% beyond the stop level, stop just beyond the lowest
                      (highest) price since the exit, managed like a breakout (half at 0.25R, stop to entry, trail)
   A new trade is skipped if it would still be open when the indicator's next trade starts.
C. The whole indicator re-run with the breakout / Magnet exit replaced (so the trades after it change too): the whole
   trade at 1R / 1.5R / 2R / 3R with the original stop, book half and keep the stop, book half and hold to 3:15.
   Trades, won, net, worst fall from a high, longest losing run, worst trade.
D. No booking half, the whole trade, re-run as in C: all at the book-half level (0.25R); or the stop to breakeven
   (entry) at 0.25R (or at 1R) and then everything at the target (breakout 1R / 2R / 3R, Magnet the CPR edge) or at
   the trailing stop as now; for comparison the whole trade at 3R with the original stop.
Costs 4 Nifty / 12 Sensex points. A and B: each trade replayed on its own; January-June and July-October separately.
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
COST, OUT, LAST, path = spec['cost'], A.OUT, A.VOL_END, A.path
RS = {'nifty': 32.5, 'sensex': 10.0}[NM] * 5

def walk(c1, side, e, start, stp, half_at=None, tgt=None, to_entry=True, trail=None):
    """Stop, book half at half_at (then the stop to entry if to_entry), the rest (or all) at tgt, trail `trail` behind
    the best price once it is `trail` in profit, out at 3:15. -> (points after costs, exit minute, exit price, why)"""
    half, best = None, e
    for m, o, h, l, c in c1:
        if m < start: continue
        for px in path(o, h, l, c):
            if side * (px - stp) <= 0:
                rest = side * (stp - e)
                why = 'stop' if half is None else 'trailing stop' if side * (stp - e) > 0 else 'stop at entry' if stp == e else 'stop'
                return (rest if half is None else (half + rest) / 2) - COST, m, stp, why
            if half_at is not None and half is None and side * (px - half_at) >= 0:
                half = side * (half_at - e)
                if to_entry and side * (e - stp) > 0: stp = e
            if tgt is not None and (half_at is None or half is not None) and side * (px - tgt) >= 0:
                return (side * (tgt - e) if half is None else (half + side * (tgt - e)) / 2) - COST, m, tgt, 'target'
        best = max(best, h) if side > 0 else min(best, l)
        if trail and side * (best - e) >= trail:
            ns = best - side * trail
            if side * (ns - stp) > 0: stp = ns
        if m >= OUT:
            rest = side * (c - e)
            return (rest if half is None else (half + rest) / 2) - COST, m, c, '3:15'
    m, o, h, l, c = c1[-1]
    rest = side * (c - e)
    return (rest if half is None else (half + rest) / 2) - COST, m, c, '3:15'

def walk_be(c1, side, e, start, stp, be_at=None, tgt=None, trail=None):
    """The whole trade: the stop to entry (breakeven) once price reaches be_at, everything at tgt, trail `trail` behind
    the best price once it is `trail` in profit, out at 3:15."""
    best = e
    for m, o, h, l, c in c1:
        if m < start: continue
        for px in path(o, h, l, c):
            if side * (px - stp) <= 0:
                why = 'breakeven' if stp == e else 'trailing stop' if side * (stp - e) > 0 else 'stop'
                return side * (stp - e) - COST, m, stp, why
            if be_at is not None and side * (px - be_at) >= 0 and side * (e - stp) > 0: stp = e
            if tgt is not None and side * (px - tgt) >= 0:
                return side * (tgt - e) - COST, m, tgt, 'target'
        best = max(best, h) if side > 0 else min(best, l)
        if trail and side * (best - e) >= trail:
            ns = best - side * trail
            if side * (ns - stp) > 0: stp = ns
        if m >= OUT:
            return side * (c - e) - COST, m, c, '3:15'
    m, o, h, l, c = c1[-1]
    return side * (c - e) - COST, m, c, '3:15'

def plan_alts(t, c1):
    """Points of each 'booking the profit' version for one breakout / Magnet trade."""
    side, e, stp = t['side'], t['e'], t['stp0']
    if t['src'] == 'MAGNET':
        R, start, edge = side * (e - stp), 556, t['edge']
        h = e + side * 0.25 * R
        return {'now': walk(c1, side, e, start, stp, h, edge),
                'all at 0.25R': walk(c1, side, e, start, stp, None, h),
                'rest at 1R': walk(c1, side, e, start, stp, h, edge), 'rest at 2R': walk(c1, side, e, start, stp, h, edge),
                'rest at 3R': walk(c1, side, e, start, stp, h, edge),
                'rest to 3:15': walk(c1, side, e, start, stp, h, None),
                'keep the stop': walk(c1, side, e, start, stp, h, edge, to_entry=False),
                'all at 1R': walk(c1, side, e, start, stp, None, e + side * R), 'all at 2R': walk(c1, side, e, start, stp, None, e + side * 2 * R)}
    R, start = t['R'], t['known']
    h = e + side * 0.25 * R
    return {'now': walk(c1, side, e, start, stp, h, None, True, R),
            'all at 0.25R': walk(c1, side, e, start, stp, None, h),
            'rest at 1R': walk(c1, side, e, start, stp, h, e + side * R), 'rest at 2R': walk(c1, side, e, start, stp, h, e + side * 2 * R),
            'rest at 3R': walk(c1, side, e, start, stp, h, e + side * 3 * R),
            'rest to 3:15': walk(c1, side, e, start, stp, h, None),
            'keep the stop': walk(c1, side, e, start, stp, h, None, False, R),
            'all at 1R': walk(c1, side, e, start, stp, None, e + side * R), 'all at 2R': walk(c1, side, e, start, stp, None, e + side * 2 * R)}

def again(t, c1, mode, next_start):
    """A new trade when the stop at entry / trailing stop closed t: 'reverse' or 'enter again'. None if no trade."""
    side, e, x = t['side'], t['e'], t['exit']
    mx, px = x['m'], x['px']
    if mx + 1 > LAST: return None
    start = t['known'] if t['src'] != 'MAGNET' else 556
    seg = [r for r in c1 if start <= r[0] <= mx]
    best = max(r[2] for r in seg) if side > 0 else min(r[3] for r in seg)
    if mode == 'reverse':
        s2 = -side; stp = best + side * 0.0002 * px; risk = s2 * (px - stp)
        if risk <= 0: return None
        pnl, m2, _, why = walk(c1, s2, px, mx + 1, stp, None, px + s2 * 2 * risk)
        if m2 >= next_start: return 'clash'
        return dict(m=mx, mx=m2, pnl=pnl, why=why, side=s2, e=px)
    low = px
    for m, o, h, l, c in c1:
        if m <= mx: continue
        if m > LAST: return None
        lvl = px + side * 0.0005 * px
        if (h >= lvl) if side > 0 else (l <= lvl):
            e2 = max(o, lvl) if side > 0 else min(o, lvl)
            stp = low - side * 0.0002 * e2; R2 = side * (e2 - stp)
            if R2 <= 0: return None
            if m >= next_start: return 'clash'
            pnl, m2, _, why = walk(c1, side, e2, m + 1, stp, e2 + side * 0.25 * R2, None, True, R2)
            if m2 >= next_start: return 'clash'
            return dict(m=m, mx=m2, pnl=pnl, why=why, side=side, e=e2)
        low = min(low, l) if side > 0 else max(low, h)
    return None

def stats(xs):
    p = [x['pnl'] for x in xs]; a = sum(x['pnl'] for x in xs if x['d'] in H1)
    return len(p), sum(v > 0 for v in p), sum(p), a, sum(p) - a

if __name__ == '__main__':
    A.RULES, A.SWEEP, A.VOLCHECK = 'classic', False, True
    taken = {d: [t for t in A.day_trades(CX[d], Y.one[d], 929, True, False, 'classic') if t['taken']] for d in D26}
    allt = [dict(d=d, **t) for d in D26 for t in taken[d]]
    base = sum(t['exit']['pnl'] for t in allt); a0 = sum(t['exit']['pnl'] for t in allt if t['d'] in H1)
    plan = [t for t in allt if t['src'] in ('MAGNET', 'BREAKOUT', 'REVERSAL')]
    print(f"{NM.upper()} 2026, default: {len(allt)} trades, net {base:+,.0f} (Jan-Jun {a0:+,.0f}, Jul-Oct {base - a0:+,.0f}). "
          f"Breakout / Magnet trades: {len(plan)}, exits: " + ', '.join(f"{k} {v}" for k, v in collections.Counter(t['exit']['why'] for t in plan).most_common()))
    alts = {id(t): plan_alts(t, Y.one[t['d']]) for t in plan}
    bad = sum(abs(alts[id(t)]['now'][0] - t['exit']['pnl']) > 1e-6 for t in plan)
    print(f"  (replay check: {bad} of {len(plan)} breakout / Magnet trades differ from the indicator's own result)")
    print("\nA. BOOKING THE PROFIT, every breakout / Magnet trade (the volume-line trades stay as they are):")
    for v in list(alts[id(plan[0])]):
        net = base + sum(alts[id(t)][v][0] - t['exit']['pnl'] for t in plan)
        a = a0 + sum(alts[id(t)][v][0] - t['exit']['pnl'] for t in plan if t['d'] in H1)
        won = sum(alts[id(t)][v][0] > 0 for t in plan)
        print(f"   {v:14} breakout / Magnet trades won {won:3} of {len(plan)} | whole indicator net {net:+7,.0f} ({net - base:+6,.0f}; "
              f"Jan-Jun {a:+6,.0f}, Jul-Oct {net - a:+6,.0f}) | 5 lots Rs {net * RS:+,.0f}")
    sub = [t for t in plan if t['exit']['why'] in ('stop at entry', 'trailing stop')]
    print(f"\n   the {len(sub)} trades that ended at the stop at entry / trailing stop, one by one (points):")
    print("   " + ' '.join(f"{v:>9}" for v in ('date', 'setup', 'now', 'all@.25R', 'rest@1R', 'rest@2R', 'rest@3R', 'rest3:15')))
    for t in sub:
        al = alts[id(t)]
        print(f"   {t['d'][5:]:>9} {t['src'][:9].lower():>9} " + ' '.join(f"{al[v][0]:+9.0f}" for v in ('now', 'all at 0.25R', 'rest at 1R', 'rest at 2R', 'rest at 3R', 'rest to 3:15')))
    print("\nB. TRADING AGAIN FROM THE STOP (after a stop at entry or trailing stop, before 2:30):")
    for mode in ('reverse', 'enter again'):
        new, clash = [], 0
        for d in D26:
            ts = taken[d]
            for i, t in enumerate(ts):
                if t['src'] not in ('MAGNET', 'BREAKOUT', 'REVERSAL') or t['exit']['why'] not in ('stop at entry', 'trailing stop'): continue
                nxt = min([u['m'] for u in ts[i + 1:]] or [10 ** 9])
                r = again(t, Y.one[d], mode, nxt)
                if r == 'clash': clash += 1
                elif r: new.append(dict(d=d, **r))
        n, w, net, a, b = stats(new)
        print(f"   {mode:12} {n:3} new trades, {w} won, net {net:+6,.0f} (Jan-Jun {a:+5,.0f}, Jul-Oct {b:+5,.0f}); skipped (the next "
              f"trade came first) {clash} | whole indicator net {base + net:+7,.0f} | 5 lots Rs {(base + net) * RS:+,.0f}")
        for x in new[:40]:
            print(f"      {x['d'][5:]} {A.hhmm(x['m'])} {'BUY ' if x['side'] > 0 else 'SELL'} at {x['e']:,.2f} -> {x['why']:13} {x['pnl']:+6.0f}")

    print("\nC. THE WHOLE INDICATOR RE-RUN WITH ANOTHER BREAKOUT / MAGNET EXIT (one trade at a time, as live):")
    orig_b, orig_m = A.run_breakout, A.run_magnet
    def make(kind):
        def rb(c1, side, e, start, stp, over, cost, R=None):
            R = side * (e - stp) if R is None else R; h = e + side * 0.25 * R
            if kind == 'now': r = walk(c1, side, e, start, stp, h, None, True, R)
            elif kind == 'keep the stop': r = walk(c1, side, e, start, stp, h, None, False, R)
            elif kind == 'rest to 3:15': r = walk(c1, side, e, start, stp, h, None)
            else: r = walk(c1, side, e, start, stp, None, e + side * float(kind[4:-1]) * R)
            return dict(ev=[], stp=stp, exit=A.done(r[1], r[2], r[3], r[0]))
        def rm(c1, side, e, edge, over, cost, risk=None, R=None, start=556):
            R0 = 0.3 / 100 * e; stp = e - side * R0; h = e + side * 0.25 * R0
            if kind == 'now': r = walk(c1, side, e, start, stp, h, edge)
            elif kind == 'keep the stop': r = walk(c1, side, e, start, stp, h, edge, False)
            elif kind == 'rest to 3:15': r = walk(c1, side, e, start, stp, h, None)
            else: r = walk(c1, side, e, start, stp, None, e + side * float(kind[4:-1]) * R0)
            return dict(ev=[], stp=stp, exit=A.done(r[1], r[2], r[3], r[0]))
        return rb, rm
    for kind in ('now', 'all 1R', 'all 1.5R', 'all 2R', 'all 2.5R', 'all 3R', 'keep the stop', 'rest to 3:15'):
        A.run_breakout, A.run_magnet = make(kind)
        ts = [dict(d=d, pnl=t['exit']['pnl']) for d in D26 for t in A.day_trades(CX[d], Y.one[d], 929, True, False, 'classic') if t['taken']]
        p = [t['pnl'] for t in ts]; a = sum(t['pnl'] for t in ts if t['d'] in H1)
        eq = pk = dd = 0; run = worst_run = 0
        for v in p:
            eq += v; pk = max(pk, eq); dd = min(dd, eq - pk); run = run + 1 if v <= 0 else 0; worst_run = max(worst_run, run)
        print(f"   {kind:14} {len(p):3} trades, {100 * sum(v > 0 for v in p) / len(p):3.0f}% won, net {sum(p):+7,.0f} (Jan-Jun {a:+6,.0f}, "
              f"Jul-Oct {sum(p) - a:+6,.0f}), worst fall {dd:6,.0f}, longest losing run {worst_run}, worst trade {min(p):+.0f} | 5 lots Rs {sum(p) * RS:+,.0f}")
    A.run_breakout, A.run_magnet = orig_b, orig_m

    print("\nD. NO BOOKING HALF, THE WHOLE TRADE (re-run, one trade at a time):")
    def make_d(kind):
        def run(c1, side, e, start, stp, R, edge):
            q = e + side * 0.25 * R
            if kind == 'all at 0.25R': r = walk_be(c1, side, e, start, stp, None, q)
            elif kind == 'BE at 0.25R, trail': r = walk_be(c1, side, e, start, stp, q, edge, None if edge else R)
            elif kind.startswith('BE at 0.25R, all at'): r = walk_be(c1, side, e, start, stp, q, edge or e + side * float(kind[-2]) * R)
            elif kind == 'BE at 1R, all at 3R': r = walk_be(c1, side, e, start, stp, e + side * R, edge or e + side * 3 * R)
            else: r = walk_be(c1, side, e, start, stp, None, e + side * 3 * R)
            return dict(ev=[], stp=stp, exit=A.done(r[1], r[2], r[3], r[0]))
        def rb(c1, side, e, start, stp, over, cost, R=None):
            return run(c1, side, e, start, stp, side * (e - stp) if R is None else R, None)
        def rm(c1, side, e, edge, over, cost, risk=None, R=None, start=556):
            R0 = 0.3 / 100 * e
            return run(c1, side, e, start, e - side * R0, R0, None if kind == 'all at 3R, no BE' else edge)
        return rb, rm
    for kind in ('now', 'all at 0.25R', 'BE at 0.25R, trail', 'BE at 0.25R, all at 1R', 'BE at 0.25R, all at 2R', 'BE at 0.25R, all at 3R',
                 'BE at 1R, all at 3R', 'all at 3R, no BE'):
        if kind == 'now': A.run_breakout, A.run_magnet = orig_b, orig_m
        else: A.run_breakout, A.run_magnet = make_d(kind)
        ts = [dict(d=d, pnl=t['exit']['pnl'], why=t['exit']['why']) for d in D26 for t in A.day_trades(CX[d], Y.one[d], 929, True, False, 'classic') if t['taken']]
        p = [t['pnl'] for t in ts]; a = sum(t['pnl'] for t in ts if t['d'] in H1)
        eq = pk = dd = 0; run_ = worst_run = 0
        for v in p:
            eq += v; pk = max(pk, eq); dd = min(dd, eq - pk); run_ = run_ + 1 if v <= 0 else 0; worst_run = max(worst_run, run_)
        be = sum(t['why'] == 'breakeven' for t in ts)
        print(f"   {kind:24} {len(p):3} trades, {100 * sum(v > 0 for v in p) / len(p):3.0f}% won, breakeven exits {be:2}, net {sum(p):+7,.0f} "
              f"(Jan-Jun {a:+6,.0f}, Jul-Oct {sum(p) - a:+6,.0f}), worst fall {dd:6,.0f}, longest losing run {worst_run}, worst trade {min(p):+.0f}"
              f" | 5 lots Rs {sum(p) * RS:+,.0f}")
    A.run_breakout, A.run_magnet = orig_b, orig_m

"""2026 only: two ideas for smaller losses and more profit, on the alert program's calls (default settings).

    python y2026_reentry.py nifty        (or sensex)

1. SMALL STOP + ONE RE-ENTRY: every stop at most S points (Nifty 30 / 40 / 50, Sensex 100 / 130 / 170; the setup's own
   stop when that is smaller); book half and the trail scaled to that stop, as now. If the stop is hit, enter again
   once, the same way, when price comes back to the entry price (until 2:30), with the same small stop: two small
   losses at most instead of one big one. Also: no re-entry, and 'flip' (at the small stop, reverse once).
2. REVERSAL FROM OUR TARGET LEVELS: after a call, when price reaches its T2 (or T3) level (the reference targets:
   the next price levels beyond the entry) and a 5-minute candle closes back inside it within 30 minutes, trade the
   other way at that close with a very small stop just beyond the highest high (lowest low) since the touch, plus
   0.03%; out at 2x the stop, or book half at 1x the stop and trail the rest 1x behind the best price; by 3:15. Run as
   a separate book (one reversal per call), and added to the calls.
Costs 4 Nifty / 12 Sensex points a trade. January-June and July-October separately.
"""
import collections, sys
import y2026 as Y
sys.path.insert(0, '../../alerts')
import cprb_alerts as A

NM, D26, H1, COST = Y.B.name, Y.D26, Y.H1, Y.COST
spec = A.SPEC[NM]; sess = {d: Y.one[d] for d in Y.days}
vol = collections.defaultdict(dict)
for k, v in Y.bees.items(): vol[k[:10]][int(k[11:13]) * 60 + int(k[14:16])] = v[4]
daily = {d: Y.DAY[d] for d in Y.days}
CX = {d: A.context(spec, sess, vol, d, daily) for d in D26}
for d in D26: CX[d]['tvol'] = vol.get(d, {})
ORIG = (A.run_magnet, A.run_breakout, A.run_vol)

def defaults():
    A.RULES, A.SWEEP, A.VOLCHECK = 'classic', False, {'nifty': False, 'sensex': True}

def stats(p, days):
    a = sum(x for x, d in zip(p, days) if d in H1)
    eq = pk = dd = 0
    for v in p: eq += v; pk = max(pk, eq); dd = min(dd, eq - pk)
    return dict(n=len(p), w=sum(v > 0 for v in p), net=sum(p), a=a, b=sum(p) - a, dd=dd, worst=min(p, default=0))

def line(label, s, base=None):
    tag = '  <- better in both halves' if base and s['a'] > base['a'] and s['b'] > base['b'] else ''
    print(f"  {label:40} {s['n']:3} trades, {100 * s['w'] / max(1, s['n']):3.0f}% won | net {s['net']:+7,.0f} (Jan-Jun {s['a']:+6,.0f}, "
          f"Jul-Oct {s['b']:+6,.0f}) | worst trade {s['worst']:+5.0f}, worst fall {s['dd']:6,.0f}{tag}")

# ---------------- 1. small stop + re-entry ----------------
def again(c1, side, e, after_m):
    """The first minute after `after_m` (until 2:30) in which price is back at the entry price."""
    for m, o, h, l, c in c1:
        if after_m < m <= 870 and (h >= e if side > 0 else l <= e):
            return m, (max(o, e) if side > 0 else min(o, e)) if (o >= e if side > 0 else o <= e) else e
    return None, None

def patched(S, mode):
    om, ob, ov = ORIG
    def combine(first, side, e, c1, rerun):
        x = first['exit']
        if mode == 'none' or not x or x['why'] != 'stop':
            return first
        if mode == 'again':
            m2, e2 = again(c1, side, e, x['m'])
            if m2 is None: return first
            second = rerun(side, e2, m2 + 1)
        else:                                            # flip: the other way at the stop price
            second = rerun(-side, x['px'], x['m'] + 1)
        if not second['exit']: return first
        y = second['exit']
        return dict(ev=first['ev'] + second['ev'], stp=second['stp'],
                    exit=A.done(y['m'], y['px'], ('again: ' if mode == 'again' else 'flip: ') + y['why'], x['pnl'] + y['pnl']))
    def mag(c1, side, e, edge, over, cost, risk=None, R=None, start=556):
        r0 = 0.003 * e; s = min(r0, S)
        first = om(c1, side, e, edge, over, cost, s, s, start)
        rerun = lambda sd, e2, st: om(c1, sd, e2, edge if sd == side else e2 + sd * 4 * s, over, cost, s, s, st)
        return combine(first, side, e, c1, rerun)
    def bo(c1, side, e, start, stp, over, cost, R=None):
        s = min(side * (e - stp), S)
        first = ob(c1, side, e, start, e - side * s, over, cost, s)
        rerun = lambda sd, e2, st: ob(c1, sd, e2, st, e2 - sd * s, over, cost, s)
        return combine(first, side, e, c1, rerun)
    def vl(c1, side, e, start, stp, tgt, x, tgt2, over, cost):
        s = min(side * (e - stp), S)
        first = ov(c1, side, e, start, e - side * s, tgt, x, tgt2, over, cost)
        rerun = lambda sd, e2, st: ov(c1, sd, e2, st, e2 - sd * s, tgt if sd == side else e2 + sd * 2 * s, x, None, over, cost)
        return combine(first, side, e, c1, rerun)
    return mag, bo, vl

def calls(S=None, mode='none'):
    defaults()
    if S: A.run_magnet, A.run_breakout, A.run_vol = patched(S, mode)
    out = []
    try:
        for d in D26:
            for t in A.day_trades(CX[d], Y.one[d], 929, True, False, 'classic'):
                if t['taken'] and t['exit']:
                    out.append(dict(d=d, t=t))
    finally:
        A.run_magnet, A.run_breakout, A.run_vol = ORIG
    return out

# ---------------- 2. reversal from our target levels ----------------
def reversal(d, t, level_k, exit_kind):
    c1 = Y.one[d]; cx = CX[d]; side = t['side']
    T = A.target_levels(cx, c1, side, t['e'], t['known'])
    L = T[level_k]
    touch = next((m for m, o, h, l, c in c1 if m >= t['known'] and (h >= L if side > 0 else l <= L)), None)
    if touch is None or touch > 870: return None
    ext = L
    for m, o, h, l, c in c1:
        if m < touch: continue
        if m - touch > 30 or m > 870: return None
        ext = max(ext, h) if side > 0 else min(ext, l)
        if (m - A.OPEN) % 5 == 4 and m >= touch and (c < L if side > 0 else c > L):
            s = -side; e = c; stp = ext + side * 0.0003 * e; R = side * (stp - e)
            if R <= 0: return None
            if exit_kind == '2R':
                r = A.run_fixed(c1, s, e, m + 1, stp, e + s * 2 * R, A.OUT, True, COST)
            else:
                r = A.run_breakout(c1, s, e, m + 1, stp, True, COST, R)
            return dict(d=d, m=m, x=r['exit']['m'], pnl=r['exit']['pnl'], R=R)
    return None

if __name__ == '__main__':
    print(f"{NM.upper()} 2026, the alert program's calls (default settings), costs {COST:g} points a trade")
    base_c = calls()
    base = stats([c['t']['exit']['pnl'] for c in base_c], [c['d'] for c in base_c])
    line('now', base)
    print("\n1. SMALL STOP (+ ONE RE-ENTRY at the entry price, or a flip)")
    for S in ({'nifty': (30, 40, 50), 'sensex': (100, 130, 170)}[NM]):
        for mode in ('none', 'again', 'flip'):
            cs = calls(S, mode)
            line(f"stop at most {S} pts, {mode}", stats([c['t']['exit']['pnl'] for c in cs], [c['d'] for c in cs]), base)
    print("\n2. REVERSAL FROM OUR TARGET LEVELS (very small stop beyond the extreme), a separate book")
    for k, kl in ((1, 'T2'), (2, 'T3')):
        for ex in ('2R', 'trail'):
            rs = [r for r in (reversal(c['d'], c['t'], k, ex) for c in base_c) if r]
            s = stats([r['pnl'] for r in rs], [r['d'] for r in rs])
            avgR = sum(r['R'] for r in rs) / max(1, len(rs))
            line(f"reversal at {kl}, {ex} (stop avg {avgR:.0f})", s)
            both = [c['t']['exit']['pnl'] for c in base_c] + [r['pnl'] for r in rs]
            line(f"   calls + these reversals", stats(both, [c['d'] for c in base_c] + [r['d'] for r in rs]), base)

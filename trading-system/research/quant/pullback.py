"""Enter on the pullback instead of at the breakout (asked on 15 October 2026), and reversals at key levels confirmed
by the candle and the volume. 2023-2026, both indices, costs in, pessimistic fills.

    python pullback.py nifty        (or sensex)

The same calls as now (default settings) give the signal; only the entry and the stop change:
 BREAKOUT calls (the 15-minute high / low touched):
   now      enter at the touch, stop at the other side of the 15-minute range
   retest   wait for a 5-minute close beyond the level, then a limit order back at the level (60 minutes); stop: the
            same (orig), the middle of the range (mid), or half the distance (half)
   sweep    price goes back through the level (at least 0.03%) and a 1-minute (s1) / 5-minute (s5) candle closes beyond
            it again within 60 minutes: enter at that close, stop just beyond the dip (0.02%); up to 2 entries a call
   fvg      the first fair value gap (1-minute candles) beyond the level after the breakout: a limit at its middle, stop
            beyond its first candle (60 minutes)
 VOLUME LINE calls (a 5-minute close through a line):
   now      enter at the close, stop at the previous line
   retest   a limit back at the broken line (60 minutes); stop: the previous line (orig) or halfway to it (half)
   sweep    back through the line and a 1-minute close beyond it again: enter, stop beyond the dip
Exits: now (book half at 0.25x the stop, stop to entry, trail the rest 1x behind), fixed (Nifty 40 / Sensex 150), T2
(all at the second price level ahead, stop to entry at the first). Out by 3:15.
REVERSALS at key levels (P, CPR, R1 / S1, R2 / S2, yesterday's high / low, the 15-minute range, volume lines, the
POC): a 5-minute candle reaches the level and closes back with a long wick (at least half its range), on NIFTYBEES
volume at least 1.5x the last hour's average (or any volume); enter at the close, stop beyond the wick (+0.02%, at
most 0.4%), target fixed (Nifty 40 / Sensex 150) or the next level; 9:30-2:30, one at a time.
"""
import collections, itertools, sys
import levels_style as LS

A = LS.A
NM, COST = LS.NM, LS.COST
DAYS = LS.DAYS
FIX = {'nifty': 40, 'sensex': 150}[NM]

def exit_(c1, side, e, start, stp, mode, cx, limit=False):
    R = side * (e - stp)
    if R <= 0:
        return None
    if limit:                                   # the fill candle: only the stop counts in it
        fc = next(x for x in c1 if x[0] == start)
        if (fc[3] <= stp) if side > 0 else (fc[2] >= stp):
            return side * (stp - e) - COST, start
        start += 1
    if mode == 'now':
        p, x, _ = LS.walk(c1, side, e, start, stp, (e + side * 0.25 * R,), (0.5,), be_at=1, trail=R)
    elif mode == 'fixed':
        p, x, _ = LS.walk(c1, side, e, start, stp, (e + side * FIX,), (1,))
    else:
        T = A.target_levels(cx, c1, side, e, start)
        p, x, _ = LS.walk(c1, side, e, start, stp, T[:2], (0, 1), be_at=1)
    return p, x

def limit_fill(c1, side, px, stp, since, until):
    for m, o, h, l, c in c1:
        if m < since:
            continue
        if m > until:
            return None
        if (o <= stp) if side > 0 else (o >= stp):
            return None
        if (l <= px) if side > 0 else (h >= px):
            return m, (min(o, px) if side > 0 else max(o, px))
    return None

def calls():
    out = []
    for d in DAYS:
        for t in A.day_trades(LS.CX[d], LS.sess[d], 929, True, False, 'classic'):
            if t['taken'] and t['exit'] and t['src'] in ('BREAKOUT', 'VOLUME LINE'):
                out.append((d, t))
    return out

def variant(d, t, how, stopk, mode):
    """Trades (pnl) for one call under one entry style."""
    c1, cx, sd, e0 = LS.sess[d], LS.CX[d], t['side'], t['e']
    lvl = e0 if t['src'] == 'BREAKOUT' else t['x']
    other = t['stp0']
    m0 = t['known']
    res = []
    if how == 'now':
        r = exit_(c1, sd, e0, m0, other, mode, cx)
        return [r[0]] if r else []
    if how == 'retest':
        since = m0
        if t['src'] == 'BREAKOUT':              # a 5-minute close beyond the level first
            conf = next((x for x in c1 if x[0] >= m0 and (x[0] - 555) % 5 == 4 and sd * (x[4] - lvl) > 0), None)
            if not conf:
                return []
            since = conf[0] + 1
        stp = other if stopk == 'orig' else (lvl + other) / 2 if stopk == 'mid' else lvl - sd * 0.5 * sd * (lvl - other)
        f = limit_fill(c1, sd, lvl, stp, since, min(since + 59, 870))
        if not f:
            return []
        r = exit_(c1, sd, f[1], f[0], stp, mode, cx, limit=True)
        return [r[0]] if r else []
    if how in ('s1', 's5'):
        tf = 1 if how == 's1' else 5
        k, n = m0, 0
        while n < 2:                                    # up to 2 entries a call (again after a loss)
            dip = entry = None
            for m, o, h, l, c in c1:
                if m < k:
                    continue
                if m > min(k + 60, 870):
                    break
                ext = l if sd > 0 else h
                if sd * (lvl - ext) >= 0.0003 * lvl:    # back through the level: the sweep
                    dip = ext if dip is None else (min(dip, ext) if sd > 0 else max(dip, ext))
                if dip is not None and sd * (c - lvl) > 0 and (tf == 1 or (m - 555) % 5 == 4):
                    entry = (m, c); break               # closed beyond the level again: the reclaim
            if not entry:
                break
            stp = dip - sd * 0.0002 * lvl
            if sd * (entry[1] - stp) > 0.006 * lvl:
                break
            r = exit_(c1, sd, entry[1], entry[0] + 1, stp, mode, cx)
            if not r:
                break
            res.append(r[0]); n += 1; k = r[1] + 1
            if r[0] > 0:
                break
        return res
    if how == 'fvg':
        for i in range(len(c1) - 2):
            m = c1[i][0]
            if m < m0 - 1:
                continue
            if m > min(m0 + 60, 868):
                break
            a, b = c1[i], c1[i + 2]
            gap = (b[3] - a[2]) if sd > 0 else (a[3] - b[2])
            beyond = sd * (((b[3] + a[2]) / 2) - lvl) > 0
            if gap >= 0.0002 * lvl and beyond:
                px = (b[3] + a[2]) / 2 if sd > 0 else (a[3] + b[2]) / 2
                stp = (a[3] if sd > 0 else a[2]) - sd * 0.0002 * lvl
                f = limit_fill(c1, sd, px, stp, b[0] + 1, min(b[0] + 60, 870))
                if not f:
                    return []
                r = exit_(c1, sd, f[1], f[0], stp, mode, cx, limit=True)
                return [r[0]] if r else []
        return []

def reversals(volk, tgt):
    out = []
    for d in DAYS:
        c1, cx = LS.sess[d], LS.CX[d]
        L = LS.day_levels(cx, c1)
        vol = LS.vol.get(d, {})
        blocks = collections.OrderedDict()
        for x in c1:
            blocks.setdefault(555 + (x[0] - 555) // 5 * 5, []).append(x)
        keys = list(blocks)
        busy = -1
        for bi, s in enumerate(keys):
            blk = blocks[s]
            end = s + 4
            if s < A.RANGE_END or end > 870 or end <= busy or len(blk) < 5:
                continue
            o, h, l, c = blk[0][1], max(x[2] for x in blk), min(x[3] for x in blk), blk[-1][4]
            rngb = h - l
            if rngb <= 0:
                continue
            v = sum(vol.get(x[0], 0) for x in blk)
            past = [sum(vol.get(x[0], 0) for x in blocks[k]) for k in keys[max(0, bi - 12):bi]]
            if volk and (not past or v < volk * (sum(past) / len(past))):
                continue
            for name, lv in L.items():
                for side in (-1, 1):
                    if side < 0 and h >= lv > c and (h - max(o, c)) >= 0.5 * rngb:
                        pass
                    elif side > 0 and l <= lv < c and (min(o, c) - l) >= 0.5 * rngb:
                        pass
                    else:
                        continue
                    e = c
                    stp = (h if side < 0 else l) + (-side) * 0.0002 * lv
                    R = side * (e - stp)
                    if R <= 0 or R > 0.004 * e:
                        continue
                    if tgt == 'fixed':
                        T = e + side * FIX
                    else:
                        ahead = sorted((x for x in L.values() if side * (x - e) >= max(0.5 * R, 0.0005 * e)), key=lambda x: side * (x - e))
                        if not ahead:
                            continue
                        T = ahead[0]
                    p, x, _ = LS.walk(c1, side, e, end + 1, stp, (T,), (1,))
                    out.append((d, p)); busy = x
                    break
                if busy >= end:
                    break
    return out

if __name__ == '__main__':
    print(f"{NM.upper()} 2023-2026: entering on the pullback; costs {COST:g} points a trade; per year: trades, won %, net points")
    C = calls()
    for src in ('BREAKOUT', 'VOLUME LINE'):
        cs = [(d, t) for d, t in C if t['src'] == src]
        print(f"\n{src} calls ({len(cs)})")
        hows = [('now', '-')] + ([('retest', k) for k in ('orig', 'mid', 'half')] if src == 'BREAKOUT' else
                                 [('retest', k) for k in ('orig', 'half')]) + [('s1', '-'), ('s5', '-')] + \
               ([('fvg', '-')] if src == 'BREAKOUT' else [])
        for (how, sk), mode in itertools.product(hows, ('now', 'fixed', 'T2')):
            rows = [(d, p) for d, t in cs for p in variant(d, t, how, sk, mode)]
            LS.line(f"entry {how}{'' if sk == '-' else ' stop ' + sk} | exit {mode}", LS.stats(rows), 40)
    print("\nREVERSALS at key levels: a 5-minute rejection candle (long wick) with volume")
    for volk, tgt in itertools.product((0, 1.5), ('fixed', 'next')):
        LS.line(f"volume {'any' if not volk else '>=1.5x'} | target {tgt}", LS.stats(reversals(volk, tgt)), 40)

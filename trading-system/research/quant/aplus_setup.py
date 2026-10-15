"""The 'A+ entry setup' (the picture sent on 15 October 2026), both directions, on its own and with the alert
program's calls: 2026 first, then 2023-2025 to see whether it holds up.

    python aplus_setup.py nifty        (or sensex)

The setup, BUY (SELL is the mirror image), on 1- / 3- / 5-minute candles (entries 9:30-2:30):
  1. liquidity: a low that stops are under - today's earlier swing lows (a candle with `piv` higher lows on each
     side), yesterday's low, the 9:15-9:30 low;
  2. sweep: a candle goes below it and closes back above it (wick), or closes back above it within 2 candles (2bar);
  3. change of character (CHoCH): within 12 candles, a close above the last swing high before the sweep, without a
     new low below the sweep first;
  4. fair value gap (FVG) in that move up: a candle whose low is above the high of the candle two before it (at
     least 0.02% of price); the last one;
  5. entry: a limit order back in the gap - at its top (the first touch) or its middle; valid 60 minutes, cancelled
     if price reaches the stop first;
  6. stop: below the sweep's low (sweep) or below the gap's first candle (c1), +0.02%; skipped if more than 0.5% or
     less than 0.03% from the entry;
  7. target: 2x / 3x the stop, half (half at 1x, stop to entry, the rest at 3x), or liq (today's high before the sweep,
     at least 1.5x the stop away, else 3x). Out by 3:15. One trade at a time, at most 3 a day.
Fills: a 1-minute candle reaching both the stop and the target counts as the stop. Costs 4 Nifty / 12 Sensex points.
With our calls: one book (one trade at a time across both; whichever comes first) and two books (both run).
"""
import collections, itertools, json, sys
import levels_style as LS

A, Y = LS.A, LS.Y
NM, COST = LS.NM, LS.COST
DAYS = LS.DAYS
D26 = [d for d in DAYS if d >= '2026-01-01']
H1 = {d for d in D26 if d < '2026-07-01'}

def bars(c1, tf):
    out = []
    for m, o, h, l, c in c1:
        s = 555 + (m - 555) // tf * tf
        if out and out[-1][0] == s:
            b = out[-1]; out[-1] = (s, b[1], max(b[2], h), min(b[3], l), c)
        else:
            out.append((s, o, h, l, c))
    return out

def swings(B, piv, side):
    """Indices of swing lows (side 1) / highs (side -1), each with the index from which it is known."""
    out = []
    for i in range(piv, len(B) - piv):
        x = B[i][3] if side > 0 else B[i][2]
        nb = [B[j][3] if side > 0 else B[j][2] for j in range(i - piv, i + piv + 1) if j != i]
        if all((x < y) if side > 0 else (x > y) for y in nb):
            out.append((i, i + piv))
    return out

def setups(d, tf, piv, sweep):
    """Every complete sweep -> CHoCH -> FVG on day d: (minute the order is placed, side, gap top, gap middle,
    sweep extreme, gap's first candle extreme, today's extreme before the sweep)."""
    c1 = LS.sess[d]
    B = bars(c1, tf)
    cx = LS.CX[d]
    orl = min(x[3] for x in c1 if x[0] < A.RANGE_END); orh = max(x[2] for x in c1 if x[0] < A.RANGE_END)
    out = []
    for side in (1, -1):
        lows = swings(B, piv, side)            # liquidity on the sweep side
        highs = swings(B, piv, -side)          # the structure the CHoCH breaks
        used = set()
        for i in range(len(B)):
            end_i = B[i][0] + tf                # minute the sweep candle is complete
            if end_i - 1 < A.RANGE_END or end_i > 870:
                continue
            liq = [cx['yl'] if side > 0 else cx['yh'], orl if side > 0 else orh]
            liq += [B[k][3] if side > 0 else B[k][2] for k, known in lows if known < i]
            lo, hi, cl = B[i][3], B[i][2], B[i][4]
            swept = [L for L in liq if ((lo < L) if side > 0 else (hi > L)) and L not in used]
            if not swept:
                continue
            L = max(swept) if side > 0 else min(swept)
            back = (cl > L) if side > 0 else (cl < L)
            j0 = i
            if not back and sweep == '2bar' and i + 1 < len(B):
                back = (B[i + 1][4] > L) if side > 0 else (B[i + 1][4] < L)
                j0 = i + 1
            if not back:
                continue
            used.update(swept)
            ext = min(x[3] for x in B[i:j0 + 1]) if side > 0 else max(x[2] for x in B[i:j0 + 1])
            prior = [k for k, known in highs if known <= i and k < i]
            if not prior:
                continue
            lvl = B[prior[-1]][2] if side > 0 else B[prior[-1]][3]
            j = None
            for k in range(j0 + 1, min(len(B), j0 + 13)):
                if (B[k][3] < ext) if side > 0 else (B[k][2] > ext):
                    break                       # a new low beyond the sweep: not this one
                if (B[k][4] > lvl) if side > 0 else (B[k][4] < lvl):
                    j = k; break
            if j is None:
                continue
            gap = None
            for k in range(i - 1, j):           # candles k, k+1, k+2 with k+2 <= j+1
                if k < 0 or k + 2 >= len(B):
                    continue
                if side > 0 and B[k + 2][3] - B[k][2] >= 0.0002 * cl:
                    gap = (B[k + 2][3], B[k][2], B[k][3], k + 2)
                if side < 0 and B[k][3] - B[k + 2][2] >= 0.0002 * cl:
                    gap = (B[k + 2][2], B[k][3], B[k][2], k + 2)
            if gap is None:
                continue
            top, bot, c1x, k2 = gap
            placed = max(B[j][0], B[k2][0]) + tf
            if placed > 870:
                continue
            before = [x for x in c1 if x[0] < B[i][0]]
            far = (max(x[2] for x in before) if side > 0 else min(x[3] for x in before)) if before else None
            out.append((placed, side, top, (top + bot) / 2, ext, c1x, far))
    return sorted(out, key=lambda x: x[0])

SET = {}
def trades(tf, piv, sweep, entry, stop, tgt, days=DAYS):
    out = []
    for d in days:
        key = (d, tf, piv, sweep)
        if key not in SET:
            SET[key] = setups(d, tf, piv, sweep)
        c1 = LS.sess[d]
        busy, n = -1, 0
        for placed, side, top, mid, ext, c1x, far in SET[key]:
            if placed <= busy or n >= 3:
                continue
            px = top if entry == 'top' else mid
            stp = (ext if stop == 'sweep' else c1x) - side * 0.0002 * px
            R = side * (px - stp)
            if R <= 0.0003 * px or R > 0.005 * px:
                continue
            fill = None
            for m, o, h, l, c in c1:
                if m < placed:
                    continue
                if m > min(placed + 59, 870):
                    break
                if (o <= stp) if side > 0 else (o >= stp):
                    break                       # opened beyond the stop: cancelled
                if (l <= px) if side > 0 else (h >= px):
                    fill = (m, min(o, px) if side > 0 else max(o, px)); break
            if not fill:
                continue
            fm, e = fill
            R = side * (e - stp)
            if tgt == 'half':
                pnl, xm, _ = LS.walk(c1, side, e, fm + 1, stp, (e + side * R, e + side * 3 * R), (0.5, 0.5), be_at=1)
            else:
                if tgt == 'liq':
                    T = far if far is not None and side * (far - e) >= 1.5 * R else e + side * 3 * R
                else:
                    T = e + side * float(tgt[0]) * R
                pnl, xm, _ = LS.walk(c1, side, e, fm + 1, stp, (T,), (1,))
            # the fill candle itself may reach the stop (pessimistic)
            fc = next(x for x in c1 if x[0] == fm)
            if (fc[3] <= stp) if side > 0 else (fc[2] >= stp):
                pnl, xm = side * (stp - e) - COST, fm
            out.append(dict(d=d, m=fm, x=xm, side=side, pnl=pnl))
            busy, n = xm, n + 1
    return out

def ours():
    out = []
    for d in DAYS:
        for t in A.day_trades(LS.CX[d], LS.sess[d], 929, True, False, 'classic'):
            if t['taken'] and t['exit']:
                out.append(dict(d=d, m=t['m'], x=t['exit']['m'], side=t['side'], pnl=t['exit']['pnl']))
    return out

def one_book(a, b):
    """One trade at a time across both lists (per day, whichever comes first)."""
    by = collections.defaultdict(list)
    for t in a + b:
        by[t['d']].append(t)
    out = []
    for d, ts in by.items():
        busy = -1
        for t in sorted(ts, key=lambda t: t['m']):
            if t['m'] > busy:
                out.append(t); busy = t['x']
    return out

def show(label, ts, w=46):
    rows = [(t['d'], t['pnl']) for t in ts]
    a = sum(p for d, p in rows if d in H1)
    s = LS.stats(rows)
    y26 = s['2026']
    print(f"  {label:{w}} 2026: {y26['n']:3} tr {y26['win']:3}% won {y26['net']:+7,} (Jan-Jun {a:+6,.0f}, Jul-Oct {y26['net'] - a:+6,.0f}) "
          f"fall {LS.stats([r for r in rows if r[0] >= '2026'])['all']['dd']:+6,} | 2023 {s['2023']['net']:+6,} 2024 {s['2024']['net']:+6,} "
          f"2025 {s['2025']['net']:+6,}{'  <- every year +' if all(s[y]['net'] > 0 for y in LS.YEARS) else ''}")
    return s

if __name__ == '__main__':
    print(f"{NM.upper()}: the A+ entry setup (sweep -> CHoCH -> FVG retrace), both directions; costs {COST:g} points a trade")
    base = ours()
    show('OUR CALLS (now)', base)
    res = {}
    for v in itertools.product((1, 3, 5), (1, 2), ('wick', '2bar'), ('top', 'mid'), ('sweep', 'c1'), ('2R', '3R', 'half', 'liq')):
        res[v] = trades(*v)
    canon = (5, 2, 'wick', 'mid', 'sweep', '3R')
    print("\n  A+ ON ITS OWN")
    show('textbook: 5-min, sweep stop, FVG middle, 3R', res[canon])
    pos26 = sum(1 for v, ts in res.items() if sum(t['pnl'] for t in ts if t['d'] >= '2026') > 0)
    pos_all = sum(1 for v, ts in res.items() if all(sum(t['pnl'] for t in ts if t['d'][:4] == y) > 0 for y in LS.YEARS))
    print(f"  {len(res)} versions: positive in 2026 {pos26}; positive in every year 2023-2026 {pos_all}")
    rank26 = sorted(res, key=lambda v: -sum(t['pnl'] for t in res[v] if t['d'] >= '2026'))
    print("  the 5 best in 2026 (and their 2023-2025):")
    for v in rank26[:5]:
        show(f"{v[0]}m piv{v[1]} {v[2]} {v[3]} stop {v[4]} {v[5]}", res[v])
    train = sorted(res, key=lambda v: -sum(t['pnl'] for t in res[v] if t['d'] < '2026'))
    print("  the 5 best on 2023-2025 (chosen without 2026), and their 2026:")
    for v in train[:5]:
        show(f"{v[0]}m piv{v[1]} {v[2]} {v[3]} stop {v[4]} {v[5]}", res[v])
    print("\n  WITH OUR CALLS")
    for label, v in (('textbook', canon), ('best on 2023-2025', train[0]), ('best in 2026 (hindsight)', rank26[0])):
        show(f'one book: ours + A+ {label}', one_book(base, res[v]))
        show(f'two books: ours + A+ {label}', base + res[v])
    json.dump({' '.join(map(str, v)): LS.stats([(t['d'], t['pnl']) for t in ts]) for v, ts in res.items()},
              open(f'../.cache/aplus_{NM}.json', 'w'))

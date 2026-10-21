"""Pivot-level breaks on 2023-2026 (asked on 21 October 2026: "are you using the pivots along with the CPR?"). The
version y2026_pivots.py found on 2026 alone (864 tried): a 5-minute close through a pivot level (S3, S2, S1, BC, P,
TC, R1, R2, R3; levels within 0.05% merged) from 9:20 -> that way at the close; stop at the level behind; only when
the next level is at least 1x the stop away; not against today's CPR vs yesterday's; trail 1R behind the best price
after +1R, out by 3:15; one at a time. Here on 2023-2025 too, with neighbours (stop halfway back / at most 55 / 170,
target the next level, no direction filter, next level 1.5x). Costs 4 / 12; a candle reaching both counts as the stop.

    python pivot_breaks.py nifty        (or sensex)
"""
import itertools
import levels_style as LS
import weekly_cpr as WK

A = LS.A
NM, COST = LS.NM, LS.COST
CAP = {'nifty': 55, 'sensex': 170}[NM]

def piv_levels(cx):
    H, L, P = cx['yh'], cx['yl'], cx['lv']['p']
    xs = sorted([L - 2 * (H - P), P - (H - L), 2 * P - H, cx['lv']['bot'], P, cx['lv']['top'], 2 * P - L, P + (H - L),
                 H + 2 * (P - L)])
    out = []
    for x in xs:
        if out and x - out[-1] <= 0.0005 * x:
            out[-1] = (out[-1] + x) / 2
        else:
            out.append(x)
    return out

def day(d, stop, tk, filt, rr, cap):
    cx, c1 = LS.CX[d], LS.sess[d]
    lv = piv_levels(cx)
    b5 = WK.blocks5(c1)
    out, free = [], 0
    for j in range(1, len(b5)):
        m0, o, h, l, c = b5[j]
        pc = b5[j - 1][4]
        if m0 < 560 or m0 + 5 > 870 or m0 < free:
            continue
        for x in lv:
            side = 1 if pc < x <= c else -1 if pc > x >= c else 0
            if not side:
                continue
            if filt == 'rel' and side == -cx['rel']:
                break
            nxt = sorted((y for y in lv if side * (y - x) > 0), key=lambda y: abs(y - x))
            prv = sorted((y for y in lv if side * (x - y) > 0), key=lambda y: abs(y - x))
            if not nxt or not prv:
                break
            e = c
            stp = prv[0] if stop == 'prev' else (x + prv[0]) / 2
            risk = side * (e - stp)
            if risk <= 0 or side * (nxt[0] - e) < rr * risk:
                break
            if cap and risk > CAP:
                stp, risk = e - side * CAP, CAP
            if tk == 'trail':
                p, mx, _ = LS.walk(c1, side, e, m0 + 5, stp, trail=risk)
            else:
                p, mx, _ = LS.walk(c1, side, e, m0 + 5, stp, (nxt[0],), (1,))
            out.append((d, p))
            free = mx + 1
            break
    return out

if __name__ == '__main__':
    print(f"{NM.upper()} 2023-2026: pivot-level breaks; per year trades, won %, net points; costs {COST:g}")
    good = []
    for stop, tk, filt, rr, cap in itertools.product(('prev', 'half'), ('trail', 'next'), ('rel', 'none'), (1.0, 1.5), (False, True)):
        rows = [r for d in LS.DAYS for r in day(d, stop, tk, filt, rr, cap)]
        s = LS.stats(rows)
        lab = f"stop {stop}{' (cap)' if cap else ''}, {tk}, filter {filt}, next >= {rr:g}x"
        if (stop, tk, filt, rr, cap) == ('prev', 'trail', 'rel', 1.0, False):
            lab += '  <- the 2026 pick'
        LS.line(lab, s, 52)
        if all(s[y]['net'] > 0 for y in ('2023', '2024', '2025')):
            good.append((lab, s))
    print("\nmade money in each of 2023, 2024 and 2025:")
    for lab, s in good:
        LS.line(lab, s, 52)
    if not good:
        print("  none")

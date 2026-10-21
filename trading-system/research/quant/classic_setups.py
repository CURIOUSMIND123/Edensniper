"""Well-known intraday strategies, tested like the CPR (asked on 21 October 2026: "can't you find anything ... we are
also not doing reversals"). 2023-2026, both indices, costs 4 / 12 points a trade; a 1-minute candle reaching both the
stop and the target counts as the stop; one trade at a time per strategy; entries 9:20-2:30, out by 3:15. Versions
are chosen on 2023-2025 (money made in each year), then 2026.

    python classic_setups.py nifty        (or sensex)

CAMARILLA (Nick Stott; from yesterday's high H, low L, close C: H3 / L3 = C +/- 1.1 (H - L) / 4, H4 / L4 = C +/- 1.1
  (H - L) / 2), only on days that open between L3 and H3:
  reversal  price trades above H3 and a candle (1- or 5-minute) closes back below it -> SELL (L3 the other way); stop
            beyond H4 (at most 55 / 170); target C, 1x the stop, or half of it
  breakout  a 5-minute close beyond H4 / L4 -> that way; stop at H3 / L3 (at most 55 / 170); target 2x the stop, or
            trailing 1x behind the best price after +1x
GAP FILL  the open at least 0.25% / 0.5% (at most 1.5%) away from yesterday's close: against the gap, at the open (9:16)
  or after a first 5-minute candle that closed against the gap (9:20); stop beyond the day's extreme so far + 0.05%
  (at most 55 / 170, or 0.3%); target yesterday's close (the gap filled) or half the gap
OPEN = HIGH / OPEN = LOW  the first 5 / 15 minutes never traded above (below) the open (0.02%) -> SELL (BUY) at their
  close; stop beyond the open + 0.05% (at least 0.1%, at most 55 / 170); target 1x / 2x the stop, or 3:15
RSI-2 (Larry Connors), 5-minute candles: above the EMA 200, RSI 2 under 10 (5) -> BUY at the close; below it, RSI 2
  over 90 (95) -> SELL; out at the first 5-minute close with RSI 2 over 70 (under 30), the stop (55 / 170 or 35 / 100)
  or 3:15
BOLLINGER (20, 2), 5-minute: a close back inside the band after a close outside -> back toward the middle; stop beyond
  the last 3 candles (at most 55 / 170); target the middle band at entry; with or without the EMA 200 side
VWAP PULLBACK  VWAP from the index price weighted by NIFTYBEES volume; from 10:30, if every 5-minute close since 9:45 was
  above it (below), the first touch of VWAP -> BUY (SELL) there; stop 35 / 100 points; target the day's high (low) so
  far, or 2x the stop
"""
import collections, itertools, math
import levels_style as LS
import weekly_cpr as WK

A = LS.A
NM, COST = LS.NM, LS.COST
CAP = {'nifty': 55, 'sensex': 170}[NM]
SMALL = {'nifty': 35, 'sensex': 100}[NM]
DAYS = LS.DAYS

# ---------------- continuous 5-minute indicators ----------------
B5 = {}                                    # day -> [(start minute, o, h, l, c)]
seq = []
for d in LS.Y.days:
    if len(LS.sess.get(d, [])) < 300:
        continue
    B5[d] = WK.blocks5(LS.sess[d])
    seq += [(d, b[0], b[4]) for b in B5[d]]
closes = [x[2] for x in seq]
def ema(xs, k):
    out, a, e = [], 2 / (k + 1), None
    for x in xs:
        e = x if e is None else e + a * (x - e)
        out.append(e)
    return out
def rsi(xs, k):
    out, ag, al = [50.0], 0.0, 0.0
    for i in range(1, len(xs)):
        ch = xs[i] - xs[i - 1]
        g, l_ = max(ch, 0), max(-ch, 0)
        if i <= k:
            ag += g / k; al += l_ / k
        else:
            ag = (ag * (k - 1) + g) / k; al = (al * (k - 1) + l_) / k
        out.append(100 - 100 / (1 + ag / al) if al > 0 else 100.0)
    return out
E200 = ema(closes, 200)
R2 = rsi(closes, 2)
SMA20, SD20 = [], []
for i in range(len(closes)):
    w = closes[max(0, i - 19):i + 1]
    m = sum(w) / len(w)
    SMA20.append(m); SD20.append(math.sqrt(sum((x - m) ** 2 for x in w) / len(w)))
IX = {(d, s): i for i, (d, s, c) in enumerate(seq)}

def cam(cx):
    H, L, C = cx['yh'], cx['yl'], cx['yc']
    r = (H - L) * 1.1
    return dict(H3=C + r / 4, L3=C - r / 4, H4=C + r / 2, L4=C - r / 2, C=C)

def capstop(side, e, stp):
    return stp if side * (e - stp) <= CAP else e - side * CAP

def walk(c1, side, e, start, stp, tgt=None, trail=None):
    if side * (e - stp) <= 0:
        return None
    if tgt == 'calls':                        # the calls' exit: book half at 0.25x the risk, stop to entry, trail 1R
        R = side * (e - stp)
        r = LS.walk(c1, side, e, start, stp, (e + side * 0.25 * R,), (0.5,), be_at=1, trail=R)
        return r
    t = (tgt,) if tgt is not None else ()
    return LS.walk(c1, side, e, start, stp, t, (1,) if t else (), trail=trail)

# ---------------- the strategies: each gives [(day, points)] ----------------
def camarilla_rev(conf, tgt):
    out = []
    for d in DAYS:
        cx, c1 = LS.CX[d], LS.sess[d]
        k = cam(cx)
        o = c1[0][1]
        if not (k['L3'] < o < k['H3']):
            continue
        busy, used = -1, set()
        bars = [(x[0], x[1], x[2], x[3], x[4]) for x in c1] if conf == 'c1' else [(b[0] + 4, b[1], b[2], b[3], b[4]) for b in B5[d]]
        for m, bo, h, l, c in bars:
            if m < 560 or m > 870 or m <= busy:
                continue
            for side, lvl, far in ((-1, k['H3'], k['H4']), (1, k['L3'], k['L4'])):
                if side in used:
                    continue
                if (side < 0 and h > lvl and c < lvl) or (side > 0 and l < lvl and c > lvl):
                    used.add(side)
                    stp = capstop(side, c, far + side * -0.0002 * far)
                    R = side * (c - stp)
                    T = 'calls' if tgt == 'calls' else k['C'] if tgt == 'C' else c + side * (R if tgt == '1R' else 0.5 * R)
                    if T != 'calls' and side * (T - c) <= 0:
                        continue
                    r = walk(c1, side, c, m + 1, stp, T)
                    if r:
                        out.append((d, r[0])); busy = r[1]
                    break
    return out

def camarilla_bo(how):
    out = []
    for d in DAYS:
        cx, c1 = LS.CX[d], LS.sess[d]
        k = cam(cx)
        o = c1[0][1]
        if not (k['L3'] < o < k['H3']):
            continue
        done = set()
        prev = None
        for s, bo, h, l, c in B5[d]:
            if prev is None or s < 570 or s + 4 > 870:
                prev = c; continue
            side = 1 if prev <= k['H4'] < c else -1 if prev >= k['L4'] > c else 0
            prev = c
            if not side or side in done:
                continue
            done.add(side)
            stp = capstop(side, c, k['H3'] if side > 0 else k['L3'])
            R = side * (c - stp)
            r = walk(c1, side, c, s + 5, stp, c + side * 2 * R) if how == '2R' else walk(c1, side, c, s + 5, stp, trail=R)
            if r:
                out.append((d, r[0]))
                break
    return out

def gap_fill(gmin, when, tgt, stopk):
    out = []
    for d in DAYS:
        cx, c1 = LS.CX[d], LS.sess[d]
        o, yc = c1[0][1], cx['yc']
        g = (o - yc) / yc * 100
        if not (gmin <= abs(g) <= 1.5):
            continue
        side = -1 if g > 0 else 1
        if when == 'open':
            m0 = 555
            e = c1[0][4]
            ext = c1[0][2] if side < 0 else c1[0][3]
        else:
            b = B5[d][0]
            if side * (b[4] - b[1]) <= 0:            # the first 5 minutes must close against the gap
                continue
            m0, e = b[0] + 4, b[4]
            ext = b[2] if side < 0 else b[3]
        if side * (yc - e) <= 0:
            continue
        stp = ext - side * 0.0005 * ext if stopk == 'ext' else e - side * 0.003 * e
        stp = capstop(side, e, stp)
        T = 'calls' if tgt == 'calls' else yc if tgt == 'fill' else e + side * 0.5 * abs(yc - e)
        r = walk(c1, side, e, m0 + 1, stp, T)
        if r:
            out.append((d, r[0]))
    return out

def open_hl(mins, tgt):
    out = []
    for d in DAYS:
        c1 = LS.sess[d]
        o = c1[0][1]
        first = [x for x in c1 if x[0] < 555 + mins]
        hi, lo, e = max(x[2] for x in first), min(x[3] for x in first), first[-1][4]
        side = -1 if hi <= o * 1.0002 else 1 if lo >= o * 0.9998 else 0
        if not side:
            continue
        stp = o - side * 0.0005 * o
        if side * (e - stp) < 0.001 * e:
            stp = e - side * 0.001 * e
        stp = capstop(side, e, stp)
        R = side * (e - stp)
        T = None if tgt == '3:15' else 'calls' if tgt == 'calls' else e + side * (R if tgt == '1R' else 2 * R)
        r = walk(c1, side, e, 555 + mins, stp, T)
        if r:
            out.append((d, r[0]))
    return out

def rsi2(lo_th, sl):
    out = []
    for d in DAYS:
        c1 = LS.sess[d]
        busy = -1
        pos = None
        for s, bo, h, l, c in B5[d]:
            i = IX[(d, s)]
            m = s + 4
            if pos:
                side, e, stp, m_in = pos
                # the stop inside the candle (1-minute path)
                hit = None
                for x in c1:
                    if m_in < x[0] <= m:
                        if (x[3] <= stp) if side > 0 else (x[2] >= stp):
                            hit = x[0]; break
                if hit:
                    out.append((d, side * (stp - e) - COST)); pos = None; busy = hit
                elif (side > 0 and R2[i] > 70) or (side < 0 and R2[i] < 30) or m >= LS.OUT:
                    out.append((d, side * (c - e) - COST)); pos = None; busy = m
                else:
                    pos = (side, e, stp, m)
                continue
            if m < 565 or m > 870 or m <= busy:
                continue
            side = 1 if c > E200[i] and R2[i] < lo_th else -1 if c < E200[i] and R2[i] > 100 - lo_th else 0
            if side:
                pos = (side, c, c - side * sl, m)
        if pos:
            side, e, stp, m_in = pos
            out.append((d, side * (c1[-1][4] - e) - COST))
    return out

def bollinger(trend):
    out = []
    for d in DAYS:
        c1 = LS.sess[d]
        bs = B5[d]
        busy = -1
        for j in range(1, len(bs)):
            s, bo, h, l, c = bs[j]
            m = s + 4
            if m < 570 or m > 870 or m <= busy:
                continue
            i = IX[(d, s)]
            up, lo = SMA20[i] + 2 * SD20[i], SMA20[i] - 2 * SD20[i]
            pc = bs[j - 1][4]
            pu, pl = SMA20[i - 1] + 2 * SD20[i - 1], SMA20[i - 1] - 2 * SD20[i - 1]
            side = 1 if pc < pl and c > lo else -1 if pc > pu and c < up else 0
            if not side or (trend and side * (c - E200[i]) < 0):
                continue
            ext = min(b[3] for b in bs[max(0, j - 2):j + 1]) if side > 0 else max(b[2] for b in bs[max(0, j - 2):j + 1])
            stp = capstop(side, c, ext - side * 0.0002 * ext)
            T = SMA20[i]
            if side * (T - c) <= 0:
                continue
            r = walk(c1, side, c, m + 1, stp, T)
            if r:
                out.append((d, r[0])); busy = r[1]
    return out

def vwap_pb(tgt):
    out = []
    for d in DAYS:
        c1, vol = LS.sess[d], LS.vol.get(d, {})
        pv = vv = 0.0
        vw = {}
        for m, o, h, l, c in c1:
            v = vol.get(m, 0) or 1
            pv += (h + l + c) / 3 * v; vv += v
            vw[m] = pv / vv
        side = 0
        closes5 = [(b[0] + 4, b[4]) for b in B5[d] if 585 <= b[0] + 4 < 630]
        if closes5 and all(c > vw[m] for m, c in closes5 if m in vw):
            side = 1
        elif closes5 and all(c < vw[m] for m, c in closes5 if m in vw):
            side = -1
        if not side:
            continue
        ext = None
        for m, o, h, l, c in c1:
            ext = h if ext is None or (side > 0 and h > ext) else ext if side > 0 else l if ext is None or l < ext else ext
            if m < 630 or m > 870:
                continue
            w = vw.get(m - 1)
            if w is None:
                continue
            if (side > 0 and l <= w) or (side < 0 and h >= w):
                e = min(o, w) if side > 0 else max(o, w)
                stp = e - side * SMALL
                T = ext if tgt == 'extreme' else e + side * 2 * SMALL
                if side * (T - e) < 0.3 * SMALL:
                    break
                r = walk(c1, side, e, m + 1, stp, T)
                if r:
                    out.append((d, r[0]))
                break
    return out

if __name__ == '__main__':
    tests = collections.OrderedDict()
    for conf, tgt in itertools.product(('c1', 'c5'), ('C', '1R', '0.5R')):
        tests[f'camarilla reversal, {conf} close back, target {tgt}'] = lambda conf=conf, tgt=tgt: camarilla_rev(conf, tgt)
    for how in ('2R', 'trail'):
        tests[f'camarilla breakout H4 / L4, {how}'] = lambda how=how: camarilla_bo(how)
    for gmin, when, tgt, sk in itertools.product((0.25, 0.5), ('open', '9:20'), ('fill', 'half'), ('ext', '0.3%')):
        tests[f'gap fill {gmin}%+, at {when}, target {tgt}, stop {sk}'] = lambda a=gmin, b=when, c=tgt, e=sk: gap_fill(a, b, c, e)
    for mins, tgt in itertools.product((5, 15), ('1R', '2R', '3:15')):
        tests[f'open = high / low, first {mins} min, {tgt}'] = lambda a=mins, b=tgt: open_hl(a, b)
    for th, sl in itertools.product((10, 5), (CAP, SMALL)):
        tests[f'RSI-2 under {th} / over {100 - th}, stop {sl}'] = lambda a=th, b=sl: rsi2(a, b)
    for tr in (False, True):
        tests[f"bollinger reversal{' with EMA 200' if tr else ''}"] = lambda tr=tr: bollinger(tr)
    for tgt in ('extreme', '2R'):
        tests[f'VWAP pullback, target {tgt}'] = lambda tgt=tgt: vwap_pb(tgt)
    print(f"{NM.upper()} 2023-2026: per year trades, won %, net points; costs {COST:g}")
    good = []
    for lab, f in tests.items():
        s = LS.stats(f())
        LS.line(lab, s, 52)
        if all(s[y]['net'] > 0 for y in ('2023', '2024', '2025')):
            good.append((lab, s))
    print("\nmade money in each of 2023, 2024 and 2025 (then 2026):")
    for lab, s in sorted(good, key=lambda x: -min(x[1][y]['win'] for y in ('2023', '2024', '2025'))):
        LS.line(lab, s, 52)
    if not good:
        print("  none")

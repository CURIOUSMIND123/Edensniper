"""Is a reversal likely now? (asked on 19 October 2026: "mention on the chart when there is no chance of a reversal,
so that I don't take a trade unnecessarily"). On every trending moment 2023-2026: how often price then went 60 Nifty /
200 Sensex points AGAINST the day's move before 35 / 100 more WITH it (a trade against the move, the user's rule;
out at 3:15; a candle reaching both counts as the stop), and which signs change that.

    python reversal_odds.py nifty        (or sensex)

Moments: every 5-minute close 9:30-2:30. The day is FALLING when the close is below both the day's open and the CPR
bottom, RISING when above both the open and the CPR top; otherwise no trend (not counted). Signs, for a falling day
(a rising day the other way round):
  new low     minutes since the day's low was made: 0-5 (still making new lows) / 6-15 / 16-30 / 30+
  bounce      how far price is above the day's low, in stops (35 / 100 points): <0.3 / 0.3-0.7 / 0.7+
  rsi         RSI 14 (5-minute): under 30 (oversold) / 30-45 / 45+
  volume      the last 2 hours' down candles carried more NIFTYBEES volume than the up candles: with the fall / against
  move        how far below the open: <0.5% / 0.5-1% / 1%+
  level       a daily level (pivot, CPR, R1-R2 / S1-S2, yesterday's high / low) within 0.1%: near / none
  candle      the last 5-minute candle closed up (against the fall) / down
  time        before 10:30 / 10:30-12:30 / after 12:30
Break-even for a trade against the move: 41% (Nifty) / 37% (Sensex) won; pure chance 37% / 33%.
Every moment is counted, so one long fall gives many; the days are shown too.
"""
import collections, itertools
import cpr_confluence as CC
import levels_style as LS
import weekly_cpr as WK

NM, COST, TP, SL = CC.NM, CC.COST, CC.TP, CC.SL
BE = 100 * (SL + COST) / (TP + SL)

def outcome(c1, side, e, start):
    """1 if price went TP the trade's way before SL against (a candle reaching both: the stop), else 0; by 3:15."""
    up, dn = (e + TP, e - SL) if side > 0 else (e + SL, e - TP)
    for m, o, h, l, c in c1:
        if m < start:
            continue
        if side > 0:
            if l <= dn:
                return 0
            if h >= up:
                return 1
        else:
            if h >= up:
                return 0
            if l <= dn:
                return 1
        if m >= LS.OUT:
            return 0
    return 0

def moments():
    out = []
    for d in CC.DAYS:
        c1, cx = LS.sess[d], LS.CX[d]
        top, bot = cx['lv']['top'], cx['lv']['bot']
        L = list(WK.daily_cpr(cx).values())
        o0 = c1[0][1]
        by_m = {x[0]: x for x in c1}
        hi = lo = None
        him = lom = 0
        k = 0
        for s in range(570, 870, 5):
            j = CC.IDX.get((d, s))
            if j is None:
                continue
            while k < len(c1) and c1[k][0] <= s + 4:
                m, o, h, l, c = c1[k]
                if hi is None or h >= hi:
                    hi, him = h, m
                if lo is None or l <= lo:
                    lo, lom = l, m
                k += 1
            c = CC.C[j]
            D = -1 if c < min(o0, bot) else 1 if c > max(o0, top) else 0
            if not D:
                continue
            ext, extm = (lo, lom) if D < 0 else (hi, him)
            since = s + 4 - extm
            b = D * (ext - c) / SL
            r = CC.RSI[j] if D > 0 else 100 - CC.RSI[j]
            upv = sum(CC.bars[i][6] for i in range(max(0, j - 23), j + 1) if CC.bars[i][5] > CC.bars[i][2])
            dnv = sum(CC.bars[i][6] for i in range(max(0, j - 23), j + 1) if CC.bars[i][5] < CC.bars[i][2])
            mv = D * (c - o0) / o0 * 100
            f = dict(
                newext='0-5' if since <= 5 else '6-15' if since <= 15 else '16-30' if since <= 30 else '30+',
                bounce='<0.3' if b < 0.3 else '0.3-0.7' if b < 0.7 else '0.7+',
                rsi='stretched' if r > 70 else 'strong' if r >= 55 else 'fading',
                volume='with' if D * (upv - dnv) > 0 else 'against',
                move='<0.5%' if mv < 0.5 else '0.5-1%' if mv < 1 else '1%+',
                level='near' if any(abs(c - v) <= 0.001 * c for v in L) else 'none',
                candle='against' if D * (CC.C[j] - CC.bars[j][2]) < 0 else 'with',
                time='before 10:30' if s + 5 < 630 else '10:30-12:30' if s + 5 < 750 else 'after 12:30')
            out.append(dict(d=d, y=d[:4], D=D, f=f, rev=outcome(c1, -D, c, s + 5), cont=outcome(c1, D, c, s + 5)))
    return out

def summ(rs):
    by = collections.defaultdict(list)
    for r in rs:
        by[r['y']].append(r)
    return {y: (len(by[y]), len({r['d'] for r in by[y]}), 100 * sum(r['rev'] for r in by[y]) / len(by[y]) if by[y] else 0,
                100 * sum(r['cont'] for r in by[y]) / len(by[y]) if by[y] else 0) for y in LS.YEARS}

def line(label, s, w=40):
    print(f"  {label:{w}} " + ' | '.join(f"{y} {s[y][0]:5} ({s[y][1]:3} d) rev {s[y][2]:3.0f}% cont {s[y][3]:3.0f}%" for y in LS.YEARS))

if __name__ == '__main__':
    R = moments()
    print(f"{NM.upper()}: trending moments (5-minute closes, 9:30-2:30); rev = a trade against the move won ({TP} before "
          f"{SL}; break-even {BE:.0f}%), cont = a trade with the move won ({TP} before {SL})")
    line('every trending moment', summ(R))
    keys = list(R[0]['f'])
    print("\nONE SIGN AT A TIME")
    for k in keys:
        for v in sorted({r['f'][k] for r in R}):
            line(f"{k} {v}", summ([r for r in R if r['f'][k] == v]))
    print("\nPAIRS: the lowest chance of a reversal in every year 2023-2025 (at least 150 moments and 30 days a year)")
    res = []
    for a, b in itertools.combinations(keys, 2):
        for va in {r['f'][a] for r in R}:
            for vb in {r['f'][b] for r in R}:
                rs = [r for r in R if r['f'][a] == va and r['f'][b] == vb]
                s = summ(rs)
                if all(s[y][0] >= 150 and s[y][1] >= 30 for y in ('2023', '2024', '2025')):
                    res.append((f"{a} {va} + {b} {vb}", s))
    worst = lambda s: max(s[y][2] for y in ('2023', '2024', '2025'))
    best = lambda s: min(s[y][2] for y in ('2023', '2024', '2025'))
    for lab, s in sorted(res, key=lambda x: worst(x[1]))[:12]:
        line(lab, s, 52)
    print("\nPAIRS: the highest chance of a reversal in every year 2023-2025")
    for lab, s in sorted(res, key=lambda x: -best(x[1]))[:12]:
        line(lab, s, 52)

def trend_at(d, m):
    """The day's trend at the last 5-minute close before minute m: -1 falling, 1 rising, 0 none; and the time bucket."""
    c1, cx = LS.sess[d], LS.CX[d]
    s = 555 + (m - 555) // 5 * 5 - 5
    j = CC.IDX.get((d, s))
    if j is None or s < 570:
        return 0
    c, o0 = CC.C[j], c1[0][1]
    top, bot = cx['lv']['top'], cx['lv']['bot']
    return -1 if c < min(o0, bot) else 1 if c > max(o0, top) else 0

def calls_by_trend():
    A = LS.A
    A.CPR_CALLS = True
    rows = collections.defaultdict(list)
    for d in CC.DAYS:
        for t in A.day_trades(LS.CX[d], LS.sess[d], 929, True, False, 'classic'):
            if t['taken'] and t['exit']:
                tr = trend_at(d, t['m'] + 1)
                k = 'no trend' if tr == 0 else 'with the trend' if tr == t['side'] else 'AGAINST the trend'
                grp = 'CPR BREAK' if t['src'] == 'CPR BREAK' else 'other calls'
                rows[(grp, k)].append((d, t['exit']['pnl']))
    A.CPR_CALLS = False
    for k in sorted(rows):
        LS.line(f"{k[0]}: {k[1]}", LS.stats(rows[k]), 40)

if __name__ == '__main__':
    print("\nTHE CALLS (default settings + CPR BREAK): entered with / against / without the day's trend (at the last 5-minute close)")
    calls_by_trend()
    print("\nTHE CHANCE OF A REVERSAL BY TIME (for the chart)")
    for tb in ('before 10:30', '10:30-12:30', 'after 12:30'):
        rs = [r for r in R if r['f']['time'] == tb]
        s = summ(rs)
        print(f"  {tb:14} all years {100 * sum(r['rev'] for r in rs) / len(rs):3.0f}% (years {min(s[y][2] for y in LS.YEARS):.0f}-"
              f"{max(s[y][2] for y in LS.YEARS):.0f}%); still making new extremes (last 5 min): "
              f"{100 * sum(r['rev'] for r in rs if r['f']['newext'] == '0-5') / max(1, sum(r['f']['newext'] == '0-5' for r in rs)):3.0f}%")

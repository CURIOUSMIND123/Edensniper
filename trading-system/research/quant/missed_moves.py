"""The big days the calls miss (asked on 21 October 2026: "not taking these huge trades is concerning"). 2023-2026,
the calls with today's defaults; costs 4 / 12 points; a candle reaching both the stop and the target counts as the
stop. Rules chosen on 2023-2025, then 2026.

    python missed_moves.py nifty        (or sensex)

1. BIG DAYS: the index closed at least 0.8% from its open. How often, how far it went, and what the calls did on them
   (no trade / traded the day's way / only against it).
2. ADD-ONS for days with no CPR Magnet / breakout call (their own trades, next to the volume-line calls):
   a. LATE / CONFLICT BREAKOUT: the first touch of the 15-minute high / low after 9:30, until 10:00 / 11:00 / 11:30 /
      12:30, in the direction: of the opening gap / not against today's CPR vs yesterday's / either; on the POC side
      (Nifty) and with the volume check (Sensex) as the calls; stop at the other side of the range, at most 55 / 170;
      managed as the calls (book half at 0.25R, stop to entry, trail 1R).
   b. TREND ENTRY: the first 5-minute close that makes it a falling day (below both the day's open and the CPR) or a
      rising day (above both), from 9:35 / 10:00 / 10:30 until 12:30; with the move at that close; stop 35 / 55
      Nifty, 100 / 170 Sensex points; out: target 2x the stop, the stop trailing 1x behind the best price after +1x,
      the calls' management, or held to 3:15.
"""
import collections, itertools
import levels_style as LS
import weekly_cpr as WK

A = LS.A
NM, COST = LS.NM, LS.COST
CAP = {'nifty': 55, 'sensex': 170}[NM]
STOPS = {'nifty': (35, 55), 'sensex': (100, 170)}[NM]
DAYS = LS.DAYS
def calls_by_day():
    out = collections.defaultdict(list)
    for d in DAYS:
        for t in A.day_trades(LS.CX[d], LS.sess[d], 929, True, False, 'classic'):
            if t['taken'] and t['exit']:
                out[d].append(t)
    return out

def plan_traded(ts):
    return any(t['src'] in ('MAGNET', 'BREAKOUT', 'REVERSAL') for t in ts)

def breakout_addon(d, cutoff, mode):
    cx, c1 = LS.CX[d], LS.sess[d]
    first = [x for x in c1 if x[0] < A.RANGE_END]
    if not first:
        return None
    orh, orl = max(x[2] for x in first), min(x[3] for x in first)
    g = c1[0][1] - cx['yc']
    gap = 1 if g > 0 else -1 if g < 0 else 0
    vf = A.volume_fn(cx, c1, A.CLOSE) if A.vcheck(cx['name']) else None
    for side, e, start, m in A.touches(c1, orh, orl, A.RANGE_END):
        if m >= cutoff:
            return None
        if mode == 'gap' and side != gap:
            continue
        if mode == 'cpr' and side == -cx['rel']:
            continue
        if not A.poc_ok(cx, side, e) or (vf and not vf(side, m, 'BREAKOUT')):
            continue
        cs = A.capped_stop(cx, side, e, orl if side > 0 else orh)
        if not cs or side * (e - cs[0]) <= 0:
            continue
        r = A.run_breakout(c1, side, e, start, cs[0], True, cx['cost'], cs[1])
        return dict(d=d, side=side, m=m, pnl=r['exit']['pnl'])
    return None

def trend_addon(d, frm, sl, how):
    cx, c1 = LS.CX[d], LS.sess[d]
    top, bot, o0 = cx['lv']['top'], cx['lv']['bot'], c1[0][1]
    for b in WK.blocks5(c1):
        s, c = b[0], b[4]
        if s < A.RANGE_END or s + 5 < frm:
            continue
        if s + 5 > 750:
            return None
        D = -1 if c < min(o0, bot) else 1 if c > max(o0, top) else 0
        if not D:
            continue
        stp = c - D * sl
        if how == '2x':
            p = LS.walk(c1, D, c, s + 5, stp, (c + D * 2 * sl,), (1,))[0]
        elif how == 'trail':
            p = LS.walk(c1, D, c, s + 5, stp, trail=sl)[0]
        elif how == 'calls':
            p = A.run_breakout(c1, D, c, s + 5, stp, True, cx['cost'], sl)['exit']['pnl']
        else:
            p = LS.walk(c1, D, c, s + 5, stp)[0]
        return dict(d=d, side=D, m=s + 5, pnl=p)
    return None

def show(label, rows, big):
    s = LS.stats([(r['d'], r['pnl']) for r in rows])
    bg = [r['pnl'] for r in rows if r['d'] in big]
    LS.line(label, s, 46)
    print(f"  {'':46}   on big days: {len(bg)} trades, {sum(bg):+,.0f} pts; on the other days: "
          f"{len(rows) - len(bg)} trades, {sum(r['pnl'] for r in rows) - sum(bg):+,.0f} pts")
    return s

if __name__ == '__main__':
    C = calls_by_day()
    info = {}
    for d in DAYS:
        c1 = LS.sess[d]
        o, c = c1[0][1], c1[-1][4]
        info[d] = (100 * (c - o) / o, c - o)
    big = {d for d in DAYS if abs(info[d][0]) >= 0.8}
    print(f"{NM.upper()} 2023-2026: big days = closed at least 0.8% from the open; costs {COST:g}")
    print("\n1. BIG DAYS AND WHAT THE CALLS DID")
    for y in LS.YEARS:
        ds = [d for d in DAYS if d[:4] == y]
        bd = [d for d in ds if d in big]
        none = [d for d in bd if not C[d]]
        withd = [d for d in bd if any(t['side'] * info[d][1] > 0 for t in C[d])]
        only_against = [d for d in bd if C[d] and d not in withd]
        net = sum(t['exit']['pnl'] for d in bd for t in C[d])
        print(f"  {y}: {len(ds)} days, {len(bd)} big (avg move {sum(abs(info[d][1]) for d in bd) / max(1, len(bd)):.0f} pts open to "
              f"close); calls: none on {len(none)}, the day's way on {len(withd)}, only against it on {len(only_against)}; "
              f"net on big days {net:+,.0f}")
    print("\n2a. LATE / CONFLICT BREAKOUT on days with no Magnet / breakout call")
    res = {}
    for cutoff, mode in itertools.product((600, 660, 690, 750), ('gap', 'cpr', 'any')):
        rows = [r for d in DAYS if not plan_traded(C[d]) for r in [breakout_addon(d, cutoff, mode)] if r]
        res[('bo', cutoff, mode)] = show(f"until {A.hhmm(cutoff)}, direction: {mode}", rows, big)
    print("\n2b. TREND ENTRY (first close below both the open and the CPR / above both)")
    for frm, sl, how in itertools.product((575, 600, 630), STOPS, ('2x', 'trail', 'calls', '3:15')):
        rows = [r for d in DAYS for r in [trend_addon(d, frm, sl, how)] if r]
        res[('tr', frm, sl, how)] = show(f"from {A.hhmm(frm)}, stop {sl}, out: {how}", rows, big)
    ok = [k for k, s in res.items() if all(s[y]['net'] > 0 for y in ('2023', '2024', '2025'))]
    print("\nmade money in each of 2023, 2024 and 2025:", ok or 'none')

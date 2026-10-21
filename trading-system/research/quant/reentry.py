"""Second chance after a stopped call (asked on 21 October 2026: the CPR BREAK SELL at 22,928 hit its stop by 6 points
and Nifty then fell 200+ points). After a call (default settings + the CPR BREAK calls) loses at its stop, one more
trade the same way, 2023-2026, costs 4 / 12; a candle reaching both the stop and the target counts as the stop.
Chosen on 2023-2025, then 2026.

    python reentry.py nifty        (or sensex)

When (after the stop, until 2:30):
  same      price comes back to the call's entry price -> the same trade again (its stop distance)
  confirm   a 5-minute close makes it a trend day the call's way (beyond both the day's open and the CPR) -> at that close
  pullback  after that close, price comes back to the CPR edge it broke (SELL: the bottom; BUY: the top) -> there
  zone      price comes back to 20 / 35 points (Sensex 60 / 100) on the losing side of the entry -> there
Stop: 35 / 55 (Sensex 100 / 170) points; out: target 2x the stop, trailing 1x behind the best price after +1x, the
calls' management (book half at 0.25x, stop to entry, trail), or held to 3:15.
"""
import collections, itertools
import levels_style as LS
import weekly_cpr as WK

A = LS.A
NM, COST = LS.NM, LS.COST
STOPS = {'nifty': (35, 55), 'sensex': (100, 170)}[NM]
ZONES = {'nifty': (20, 35), 'sensex': (60, 100)}[NM]

def stopped_calls():
    A.CPR_CALLS = True
    out = []
    for d in LS.DAYS:
        for t in A.day_trades(LS.CX[d], LS.sess[d], 929, True, False, 'classic'):
            if t['taken'] and t['exit'] and t['exit']['why'] == 'stop' and t['exit']['m'] < 860:
                out.append((d, t))
    A.CPR_CALLS = False
    return out

def manage(c1, side, e, start, sl, how):
    stp = e - side * sl
    if how == '2x':
        return LS.walk(c1, side, e, start, stp, (e + side * 2 * sl,), (1,))[0]
    if how == 'trail':
        return LS.walk(c1, side, e, start, stp, trail=sl)[0]
    if how == 'calls':
        return LS.walk(c1, side, e, start, stp, (e + side * 0.25 * sl,), (0.5,), be_at=1, trail=sl)[0]
    return LS.walk(c1, side, e, start, stp)[0]

def entry(d, t, when, zone=None):
    """(minute, price) of the second entry, or None."""
    cx, c1 = LS.CX[d], LS.sess[d]
    sd, x0 = t['side'], t['exit']['m']
    top, bot, o0 = cx['lv']['top'], cx['lv']['bot'], c1[0][1]
    if when == 'same' or when == 'zone':
        lvl = t['e'] + (0 if when == 'same' else sd * -zone)
        for m, o, h, l, c in c1:
            if m <= x0 or m > 870:
                continue
            if (sd < 0 and h >= lvl) or (sd > 0 and l <= lvl):
                return m, (max(o, lvl) if sd < 0 else min(o, lvl))
        return None
    conf = None
    for b in WK.blocks5(c1):
        s, c = b[0], b[4]
        if s + 5 <= x0 or s + 5 > 870:
            continue
        if (sd < 0 and c < min(o0, bot)) or (sd > 0 and c > max(o0, top)):
            conf = (s + 5, c)
            break
    if not conf:
        return None
    if when == 'confirm':
        return conf[0] - 1, conf[1]
    lvl = bot if sd < 0 else top
    for m, o, h, l, c in c1:
        if m < conf[0] or m > 870:
            continue
        if (sd < 0 and h >= lvl) or (sd > 0 and l <= lvl):
            return m, (max(o, lvl) if sd < 0 else min(o, lvl))
    return None

if __name__ == '__main__':
    calls = stopped_calls()
    print(f"{NM.upper()} 2023-2026: {len(calls)} calls stopped out (default settings + CPR BREAK); one more trade the same way")
    good = []
    whens = [('same', None), ('confirm', None), ('pullback', None)] + [('zone', z) for z in ZONES]
    for (when, z), sl, how in itertools.product(whens, STOPS, ('2x', 'trail', 'calls', '3:15')):
        rows, seen = [], set()
        for d, t in calls:
            if d in seen:
                continue                                  # one second chance a day
            en = entry(d, t, when, z)
            if not en:
                continue
            seen.add(d)
            if when == 'same':
                sl_ = abs(t['e'] - t['stp0'])
                if sl != STOPS[0]:
                    continue
            else:
                sl_ = sl
            rows.append((d, manage(LS.sess[d], t['side'], en[1], en[0] + 1, sl_, how)))
        if not rows:
            continue
        lab = f"{when}{'' if z is None else ' ' + str(z)}, stop {'the call' if when == 'same' else sl}, out {how}"
        s = LS.stats(rows)
        LS.line(lab, s, 44)
        if all(s[y]['net'] > 0 for y in ('2023', '2024', '2025')):
            good.append((lab, s))
    print("\nmade money in each of 2023, 2024 and 2025:")
    for lab, s in good:
        LS.line(lab, s, 44)
    if not good:
        print("  none")

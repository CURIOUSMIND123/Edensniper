"""How far price came back against each call before it worked (asked on 17 October 2026), and what that allows:
a tighter stop, or entering lower on the pullback. All calls 2023-2026 (default settings), both indices.

    python mae_study.py nifty        (or sensex)

1. For every call, with today's stop: did T1 (book half; a volume-line call: its target) come first, or the stop, or
   neither by 3:15; and how far price went against the call first (points below a BUY's entry / above a SELL's).
   'Never came back' = never 1 point beyond the entry (Sensex 3). In the candle that reaches T1, its low (high)
   counts too, so the pullbacks are, if anything, overstated.
2. When the deep pullbacks happen: by setup, entry time, the width of the first 15-minute range (breakouts), year.
3. A capped stop: at most X points (Nifty 20 / 30 / 40 / 50, Sensex 60 / 100 / 150 / 200); book half, the targets
   and the trail as now. Chosen on 2023-2025, then 2026.
4. Entering on the pullback: a limit order X points better than the call's price (Nifty 5 / 10 / 15 / 20, Sensex
   15 / 30 / 45 / 60) for 60 minutes; the stop and T1 at the same prices as the call (so the risk is X points smaller);
   no fill = no trade. Also with the capped stop.
Costs 4 Nifty / 12 Sensex points a trade; a candle reaching both the stop and the target counts as the stop.
"""
import collections, itertools
import levels_style as LS

A = LS.A
NM, COST = LS.NM, LS.COST
EPS = 1 if NM == 'nifty' else 3
BINS = {'nifty': (10, 20, 30, 50), 'sensex': (30, 60, 100, 170)}[NM]
CAPS = {'nifty': (20, 30, 40, 50), 'sensex': (60, 100, 150, 200)}[NM]
OFFS = {'nifty': (5, 10, 15, 20), 'sensex': (15, 30, 45, 60)}[NM]

def t1_of(t):
    return A.half_price(t)

def manage(c1, t, e, start, stp):
    """Today's management from entry e: book half at the call's T1, stop to entry, trail 1R (the call's R)."""
    sd = t['side']
    R0 = sd * (t['e'] - t['stp0'])
    if t['src'] == 'VOLUME LINE':
        return LS.walk(c1, sd, e, start, stp, (t['tgt'],), (1,))[:2]
    if t['src'] == 'MAGNET':
        return LS.walk(c1, sd, e, start, stp, (t['t1'], t['edge']), (0.5, 0.5), be_at=1)[:2]
    R = t.get('R') or R0
    return LS.walk(c1, sd, e, start, stp, (t1_of(t),), (0.5,), be_at=1, trail=R)[:2]

def path_info(c1, t):
    """(outcome 'T1' / 'stop' / 'neither', deepest move against before that (points), minutes to T1)."""
    sd, e, stp, T1 = t['side'], t['e'], t['stp0'], t1_of(t)
    worst = 0.0
    for m, o, h, l, c in c1:
        if m < t['known']:
            continue
        adv, fav = (l, h) if sd > 0 else (h, l)
        worst = max(worst, sd * (e - adv))
        if sd * (adv - stp) <= 0:
            return 'stop', worst, None
        if sd * (fav - T1) >= 0:
            return 'T1', worst, m - t['known']
        if m >= LS.OUT:
            return 'neither', worst, None
    return 'neither', worst, None

def binname(x):
    if x < EPS:
        return 'never came back'
    lo = 0
    for b in BINS:
        if x < b:
            return f'came back {lo}-{b}'
        lo = b
    return f'came back {BINS[-1]}+'

def pct(a, b):
    return f"{100 * a / b:3.0f}%" if b else '  - '

if __name__ == '__main__':
    calls = []
    for d in LS.DAYS:
        c1 = LS.sess[d]
        for t in A.day_trades(LS.CX[d], c1, 929, True, False, 'classic'):
            if t['taken'] and t['exit']:
                out, worst, mins = path_info(c1, t)
                first = [x for x in c1 if x[0] < A.RANGE_END]
                calls.append(dict(d=d, t=t, out=out, worst=worst, mins=mins, R=t['side'] * (t['e'] - t['stp0']),
                                  rng=max(x[2] for x in first) - min(x[3] for x in first)))
    order = ['never came back'] + [f'came back {a}-{b}' for a, b in zip((0,) + BINS[:-1], BINS)] + [f'came back {BINS[-1]}+']
    print(f"{NM.upper()} 2023-2026: {len(calls)} calls; points against the call before T1 (today's stop)")

    def table(label, cs):
        n = len(cs)
        if n < 10:
            return
        t1 = [c for c in cs if c['out'] == 'T1']
        cnt = collections.Counter(binname(c['worst']) for c in t1)
        cells = ' | '.join(f"{k.replace('came back ', '')} {pct(cnt[k], n)}" for k in order)
        stop = sum(c['out'] == 'stop' for c in cs); nei = n - len(t1) - stop
        print(f"  {label:26} {n:3} calls | T1 after: {cells} | full stop {pct(stop, n)} | neither {pct(nei, n)} | stop avg {sum(c['R'] for c in cs) / n:4.0f}")

    print("\n1. WHAT HAPPENED AFTER THE ENTRY (share of all calls; 'never' = never came back to the entry price)")
    table('all calls', calls)
    for src in ('BREAKOUT', 'VOLUME LINE', 'MAGNET'):
        table(src.lower(), [c for c in calls if c['t']['src'] == src])
    for y in LS.YEARS:
        table(f'year {y}', [c for c in calls if c['d'][:4] == y])
    t1s = sorted(c['worst'] for c in calls if c['out'] == 'T1')
    q = lambda p: t1s[int(p * (len(t1s) - 1))]
    print(f"  calls that reached T1: half came back less than {q(0.5):.0f} points, 75% less than {q(0.75):.0f}, 90% less than {q(0.9):.0f}, "
          f"95% less than {q(0.95):.0f}; T1 took {sorted(c['mins'] for c in calls if c['mins'] is not None)[len(t1s) // 2]} minutes (median)")

    print("\n2. WHEN THE DEEP PULLBACKS HAPPEN")
    bo = [c for c in calls if c['t']['src'] == 'BREAKOUT']
    for lab, f in (('entry 9:30-9:44', lambda c: c['t']['m'] < 585), ('entry 9:45-10:00', lambda c: c['t']['m'] >= 585)):
        table(f'breakout, {lab}', [c for c in bo if f(c)])
    if bo:
        ws = sorted(c['rng'] for c in bo)
        a, b = ws[len(ws) // 3], ws[2 * len(ws) // 3]
        table(f'breakout, 15-min range < {a:.0f}', [c for c in bo if c['rng'] < a])
        table(f'breakout, range {a:.0f}-{b:.0f}', [c for c in bo if a <= c['rng'] < b])
        table(f'breakout, range > {b:.0f}', [c for c in bo if c['rng'] >= b])
    vl = [c for c in calls if c['t']['src'] == 'VOLUME LINE']
    for lab, f in (('before 11:00', lambda c: c['t']['m'] < 660), ('11:00-13:00', lambda c: 660 <= c['t']['m'] < 780), ('after 13:00', lambda c: c['t']['m'] >= 780)):
        table(f'volume line, {lab}', [c for c in vl if f(c)])

    print("\n3. A CAPPED STOP (book half, targets and trail as now)")
    base = [(c['d'], c['t']['exit']['pnl']) for c in calls]
    LS.line('now', LS.stats(base), 30)
    for cap in CAPS:
        rows = []
        for c in calls:
            t, c1 = c['t'], LS.sess[c['d']]
            stp = t['e'] - t['side'] * min(c['R'], cap)
            rows.append((c['d'], manage(c1, t, t['e'], t['known'], stp)[0]))
        LS.line(f'stop at most {cap} points', LS.stats(rows), 30)

    print("\n4. ENTERING ON THE PULLBACK (a limit order X points better; same stop and T1 prices)")
    for off, cap in itertools.product(OFFS, (None,) + CAPS[1:3]):
        rows, filled = [], 0
        for c in calls:
            t, c1, sd = c['t'], LS.sess[c['d']], c['t']['side']
            px = t['e'] - sd * off
            fill = None
            for m, o, h, l, cl in c1:
                if m < t['known']:
                    continue
                if m > min(t['known'] + 59, 870):
                    break
                if (o <= t['stp0']) if sd > 0 else (o >= t['stp0']):
                    break
                if (l <= px) if sd > 0 else (h >= px):
                    fill = (m, min(o, px) if sd > 0 else max(o, px)); break
            if not fill:
                continue
            filled += 1
            stp = t['stp0'] if cap is None else fill[1] - sd * min(sd * (fill[1] - t['stp0']), cap)
            fc = next(x for x in c1 if x[0] == fill[0])
            if (fc[3] <= stp) if sd > 0 else (fc[2] >= stp):
                rows.append((c['d'], sd * (stp - fill[1]) - COST)); continue
            rows.append((c['d'], manage(c1, t, fill[1], fill[0] + 1, stp)[0]))
        LS.line(f'{off} pts better{"" if cap is None else f", stop <= {cap}"} ({100 * filled / len(calls):.0f}% filled)', LS.stats(rows), 30)

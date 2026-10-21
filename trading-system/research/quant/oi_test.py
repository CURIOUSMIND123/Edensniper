"""Option OI for the calls (asked on 21 October 2026: "based on OI can we add something for our strategies"). OI from
the exchanges' end-of-day F&O bhavcopies (fetch_pcr.py --all): for each session the figures of the evening before,
known before 9:15 - the nearest expiry's put / call OI ratio (PCR), its put / call OI change ratio, the strike with
the most call OI (the call wall: resistance) and with the most put OI (the put wall: support). Intraday OI history
isn't free; the alert program records the chain every minute from 21 October 2026 on (DATA_DIR/oi/).
Costs 4 / 12 points; a candle reaching both the stop and the target counts as the stop. Chosen on 2023-2025, then 2026.

    python oi_test.py nifty        (or sensex)

1. PCR AS A BIAS: the calls (default settings + the extra calls), BUYs and SELLs by yesterday's PCR. A filter is
   worth it only when the calls it drops lost money in each year.
2. ROOM TO THE WALL: BUYs by how far the call wall is above the entry, SELLs by how far the put wall is below, in
   stops (R): wall behind (already through it), under 1R, 1-2R, 2R or more.
3. WALL BREAKS AS CALLS: a 5-minute close through yesterday's call wall (BUY) / put wall (SELL) from 9:20 to 2:30 ->
   that way at the close; stop 35 / 55 (Sensex 100 / 170) points or the break candle's other end (at most that);
   out at 2x the stop, trailing 1x behind the best price after +1x, or held to 3:15; with or without the CPR
   direction filter (today's CPR vs yesterday's). Each wall once a day; one trade at a time.
4. WALL FADES AS CALLS: a 5-minute candle reaches the call wall from below and closes back under it -> SELL (the put
   wall from above and back over it -> BUY); stops and exits as in 3.
5. PCR AND THE DAY: yesterday's PCR -> how often the day closed above its open, the average open-to-close.
"""
import collections, itertools, json
import levels_style as LS
import weekly_cpr as WK

A = LS.A
NM, COST = LS.NM, LS.COST
YRS = ('2023', '2024', '2025')
STOPS = {'nifty': (35, 55), 'sensex': (100, 170)}[NM]
OI = json.load(open(f'../.cache/pcr_{NM}.json'))
SESS = sorted(LS.sess)
PREV = {d: SESS[k - 1] for k, d in enumerate(SESS) if k}

def oi(d):
    """The OI figures known before day d opens (yesterday's bhavcopy), or None."""
    return OI.get(PREV.get(d))

def bucket(x, edges):
    for k, e in enumerate(edges):
        if x < e:
            return k
    return len(edges)

def blabel(k, edges, fmt='{:g}'):
    if k == 0:
        return f"under {fmt.format(edges[0])}"
    if k == len(edges):
        return f"{fmt.format(edges[-1])} or more"
    return f"{fmt.format(edges[k - 1])} - {fmt.format(edges[k])}"

def good_drop(s):
    """The dropped calls lost money in each of 2023-2025."""
    return all(s[y]['n'] and s[y]['net'] < 0 for y in YRS)

# ---------------- the calls, with yesterday's OI ----------------
def calls():
    LS.extras(True)
    out = []
    for d in LS.DAYS:
        x = oi(d)
        if not x:
            continue
        for t in A.day_trades(LS.CX[d], LS.sess[d], 929, True, False, 'classic'):
            if t['taken'] and t['exit']:
                out.append(dict(d=d, t=t, oi=x, risk=abs(t['e'] - t['stp0'])))
    LS.extras(False)
    return out

PCR_EDGES = (0.7, 0.9, 1.1, 1.3)
def part1(cs):
    print("\n1. PCR AS A BIAS: the calls by yesterday's PCR (nearest expiry; under 1 = more call OI, above 1 = more put OI)")
    for key, edges in (('pcr_near', PCR_EDGES), ('pcr_all', PCR_EDGES), ('chg_near', (0.5, 1.0, 2.0))):
        print(f"  {key}:")
        for side, nm in ((1, 'BUY'), (-1, 'SELL')):
            for k in range(len(edges) + 1):
                rows = [(c['d'], c['t']['exit']['pnl']) for c in cs if c['t']['side'] == side and c['oi'].get(key) is not None
                        and bucket(c['oi'][key], edges) == k]
                if rows:
                    LS.line(f"{nm}s, {key} {blabel(k, edges)}", LS.stats(rows), 30)
    print("  filters (skip BUYs when the PCR is under x, SELLs when it is over y):")
    found = []
    for key in ('pcr_near', 'pcr_all'):
        for lo, hi in itertools.product((0, 0.6, 0.7, 0.8, 0.9, 1.0), (1.0, 1.1, 1.2, 1.3, 1.5, 9)):
            if lo == 0 and hi == 9:
                continue
            drop = lambda c: (c['t']['side'] > 0 and c['oi'][key] < lo) or (c['t']['side'] < 0 and c['oi'][key] > hi)
            sd = LS.stats([(c['d'], c['t']['exit']['pnl']) for c in cs if drop(c)])
            if good_drop(sd):
                found.append((f"{key}: BUY >= {lo:g}, SELL <= {hi:g}: dropped", sd))
    for lab, s in found:
        LS.line(lab, s, 40)
    if not found:
        print("    none: no PCR filter dropped only calls that lost money in each of 2023-2025")

ROOM_EDGES = (0, 1, 2)
def part2(cs):
    print("\n2. ROOM TO THE WALL: BUYs by the call wall above, SELLs by the put wall below, in stops (R)")
    for side, nm, w in ((1, 'BUY', 'ce_max'), (-1, 'SELL', 'pe_max')):
        for k in range(len(ROOM_EDGES) + 1):
            rows = [(c['d'], c['t']['exit']['pnl']) for c in cs if c['t']['side'] == side and c['risk'] > 0
                    and c['oi'][w] and bucket(side * (c['oi'][w] - c['t']['e']) / c['risk'], ROOM_EDGES) == k]
            if rows:
                lab = 'wall behind' if k == 0 else blabel(k, ROOM_EDGES) + 'R'
                LS.line(f"{nm}s, {lab}", LS.stats(rows), 30)
    found = []
    for lim in (0.5, 1, 1.5, 2):
        drop = lambda c: c['risk'] > 0 and c['oi']['ce_max' if c['t']['side'] > 0 else 'pe_max'] is not None and \
            0 <= c['t']['side'] * (c['oi']['ce_max' if c['t']['side'] > 0 else 'pe_max'] - c['t']['e']) / c['risk'] < lim
        sd = LS.stats([(c['d'], c['t']['exit']['pnl']) for c in cs if drop(c)])
        LS.line(f"filter: skip with the wall under {lim:g}R ahead: dropped", sd, 40)
        if good_drop(sd):
            found.append(lim)
    print("  " + (f"worth it: under {', '.join(f'{x:g}R' for x in found)}" if found else
                  "none: no room filter dropped only calls that lost money in each of 2023-2025"))

def wall_trades(d, kind, stop, out_how, filt):
    x = oi(d)
    if not x or not x['ce_max'] or not x['pe_max']:
        return []
    cx, c1 = LS.CX[d], LS.sess[d]
    b5 = WK.blocks5(c1)
    walls = [(x['ce_max'], 1 if kind == 'break' else -1, 'call'), (x['pe_max'], -1 if kind == 'break' else 1, 'put')]
    done, out, free = set(), [], 0
    for j in range(1, len(b5)):
        m0, o, h, l, c = b5[j]
        pc = b5[j - 1][4]
        if m0 < 560 or m0 + 5 > 870 or m0 < free:
            continue
        for w, side, nm in walls:
            if nm in done:
                continue
            if kind == 'break':
                hit = (side > 0 and pc < w <= c) or (side < 0 and pc > w >= c)
            else:                                   # fade: reached the wall and closed back
                hit = (side < 0 and pc < w <= h and c < w) or (side > 0 and pc > w >= l and c > w)
            if not hit:
                continue
            done.add(nm)
            if filt and side == -cx['rel']:
                continue
            far = (c - l) if side > 0 else (h - c)
            risk = min(stop, far) if out_how.startswith('candle') else stop
            if risk <= 0:
                continue
            stp = c - side * risk
            how = out_how.split(':')[-1]
            if how == '2x':
                p, mx, _ = LS.walk(c1, side, c, m0 + 5, stp, (c + side * 2 * risk,), (1,))
            elif how == 'trail':
                p, mx, _ = LS.walk(c1, side, c, m0 + 5, stp, trail=risk)
            else:
                p, mx, _ = LS.walk(c1, side, c, m0 + 5, stp)
            out.append((d, p))
            free = mx + 1
            break
    return out

def part3_4():
    good = []
    for kind, title in (('break', '3. WALL BREAKS AS CALLS'), ('fade', '4. WALL FADES AS CALLS')):
        print(f"\n{title}")
        for stop, out_how, filt in itertools.product(STOPS, ('fixed:2x', 'fixed:trail', 'fixed:3:15', 'candle:2x',
                                                              'candle:trail'), (False, True)):
            rows = [r for d in LS.DAYS for r in wall_trades(d, kind, stop, out_how, filt)]
            s = LS.stats(rows)
            lab = f"{kind}, stop {stop}{' (candle)' if out_how.startswith('candle') else ''}, " \
                  f"{out_how.split(':', 1)[1]}{', CPR filter' if filt else ''}"
            LS.line(lab, s, 40)
            if all(s[y]['net'] > 0 for y in YRS):
                good.append((lab, s))
    print("\nmade money in each of 2023, 2024 and 2025:")
    for lab, s in good:
        LS.line(lab, s, 40)
    if not good:
        print("  none")

def part5():
    print("\n5. PCR AND THE DAY: yesterday's PCR -> days that closed above the open, average open-to-close (points)")
    by = collections.defaultdict(list)
    for d in LS.DAYS:
        x = oi(d)
        if x:
            c1 = LS.sess[d]
            by[bucket(x['pcr_near'], PCR_EDGES)].append((d, c1[-1][4] - c1[0][1]))
    for k in sorted(by):
        print(f"  PCR {blabel(k, PCR_EDGES):12} " + ' | '.join(
            f"{y} {len(v):3} d {round(100 * sum(m > 0 for m in v) / len(v)) if v else 0:3}% up {sum(v) / len(v) if v else 0:+6.0f}"
            for y in LS.YEARS for v in [[m for dd, m in by[k] if dd[:4] == y]]))

if __name__ == '__main__':
    have = collections.Counter(d[:4] for d in LS.DAYS if oi(d))
    print(f"{NM.upper()}: option OI from the evening before; days with OI: " + ', '.join(f"{y} {have[y]}" for y in LS.YEARS)
          + f"; costs {COST:g}")
    cs = calls()
    part1(cs)
    part2(cs)
    part3_4()
    part5()

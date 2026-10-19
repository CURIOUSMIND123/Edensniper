"""The trading style asked for on 15 October 2026, tested on every day with data (January 2023 - 9 October 2026), both
indices, costs in (4 Nifty / 12 Sensex points a trade).

    python levels_style.py nifty        (or sensex)        writes ../.cache/levels_<index>.json too

0. NOW: the alert program's calls as they are (default settings), year by year: is 2026 typical?
1. SMALL STOP ON THE SAME CALLS: the stop at the low (BUY) / high (SELL) of the last 2 or 3 candles before the entry
   (1-minute or 5-minute candles), a little beyond (0.02%), at least 0.03% away; then
     - the targets T1 / T2 / T3 = the next three price levels (CPR, pivots R1-R3 / S1-S3, yesterday's high / low, the
       15-minute range, the 3-day volume lines, the POC): how often each is reached before the stop (the probability
       the app would show), and exits: all at T1, all at T2 (stop to entry at T1), all at T3, half at T1 + half at T2,
       2x / 3x the stop, and today's management (book half at 0.25x the stop, stop to entry, trail) with the small stop.
2. REVERSAL AT KEY LEVELS: price comes up to a level (pivot P, CPR top / bottom, R1 / S1, R2 / S2, yesterday's high /
   low, the 15-minute high / low, the 3-day volume lines, yesterday's POC) and doesn't hold above it -> SELL (and the
   other way: comes down to a level and doesn't hold below it -> BUY). 'Doesn't hold': the touching 1-minute candle
   closes back (c1), 3 one-minute closes back in a row (c3), or a 5-minute candle closes back (c5). Stop: beyond the
   highest high (lowest low) of the last 2 / 3 one-minute candles and the level, +0.02%; skipped when that is more than
   0.08% / 0.12% / 0.20% away ('very small stop'). Target: the next level (P from R1 / S1), 1.5x / 2x / 3x the stop;
   out after 60 minutes or at 3:15. 9:30-2:30, one trade at a time, each level once a day.
   Versions are chosen on 2023-2025 and then checked on 2026, which they didn't see.
3. ROTATION: after price first reaches R1 (S1), how often it came back to P before going 0.2% beyond; after it
   comes back to P, how often it went on to the other side (S1 / R1).
4. CALLS + REVERSALS / PULLBACKS: the calls (small stop, best exit from 1) plus the best level trades of 2, split into
   trades with the call's direction (pullback re-entries) and against it (reversals).

Fills: inside a 1-minute candle that reaches both the stop and the target, the stop counts (pessimistic).
"""
import collections, itertools, json, os, pickle, sys
import y2026 as Y
sys.path.insert(0, '../../alerts')
import cprb_alerts as A

NM, COST = Y.B.name, Y.COST
spec = A.SPEC[NM]
YEARS = ('2023', '2024', '2025', '2026')
OUT = A.OUT

# ---------------- data: candles, NIFTYBEES volume (2023-2026), each day's levels ----------------
sess = {d: Y.one[d] for d in Y.days}
daily = {d: Y.DAY[d] for d in Y.days}
vol = collections.defaultdict(dict)
for f in ('../.cache/niftybees_1m_old.json', '../.cache/niftybees_1m.json'):
    for k, v in json.load(open(f)).items():
        vol[k[:10]][int(k[11:13]) * 60 + int(k[14:16])] = v[4]
A.RULES, A.SWEEP, A.CPR_CALLS = 'classic', False, False       # the calls as before (cpr_plus.py: the CPR BREAK calls)
CACHE = f'../.cache/levels_cx_{NM}.pkl'
if os.path.exists(CACHE):
    CX = pickle.load(open(CACHE, 'rb'))
else:
    CX = {}
    for d in Y.days:
        if len(sess[d]) < 300:
            continue
        try:
            cx = A.context(spec, sess, vol, d, daily)
        except SystemExit:
            continue
        cx['tvol'] = vol.get(d, {})
        prev = cx['prev']                              # yesterday's POC for the level trades (every index)
        cx['poc1'] = A.poc_va(*A.combine([A.day_hist(sess[prev], vol.get(prev, {}), spec['bin'])]), spec['bin'])[0]
        CX[d] = cx
    pickle.dump(CX, open(CACHE, 'wb'))
DAYS = sorted(CX)
_full = [d for d in Y.days if len(sess[d]) >= 300]
for d in DAYS:                                         # contexts saved before the CPR BREAK calls: their RSI start
    if 'c5h' not in CX[d]:
        CX[d]['c5h'] = A.closes5(sess, [x for x in _full if x < d][-3:])

def stats(rows):
    """rows: [(day, pnl)] -> per year and in all."""
    out = {}
    for y in YEARS + ('all',):
        p = [x for d, x in rows if y == 'all' or d[:4] == y]
        eq = pk = dd = 0
        for v in p:
            eq += v; pk = max(pk, eq); dd = min(dd, eq - pk)
        out[y] = dict(n=len(p), win=round(100 * sum(v > 0 for v in p) / len(p)) if p else 0, net=round(sum(p)),
                      worst=round(min(p)) if p else 0, dd=round(dd))
    return out

def line(label, s, w=44):
    ys = ' | '.join(f"{y} {s[y]['n']:3} tr {s[y]['win']:3}% {s[y]['net']:+7,}" for y in YEARS)
    a = s['all']
    flag = '  <- every year +' if all(s[y]['net'] > 0 for y in YEARS) else ''
    print(f"  {label:{w}} {ys} | all {a['n']:4} tr {a['win']:3}% {a['net']:+8,} worst {a['worst']:+5} fall {a['dd']:+7,}{flag}")

# ---------------- a pessimistic walk: stop first when a candle reaches both ----------------
def walk(c1, side, e, start, stp, targets=(), fracs=(), be_at=None, last=OUT, trail=None):
    """From minute `start`: book fracs[k] at targets[k]; after target number be_at the stop goes to the entry; trail
    = R: after +R, the stop follows R behind the best price. Out at `last` (and 3:15) at the close."""
    left, pnl, k, best = 1.0, 0.0, 0, e
    for m, o, h, l, c in c1:
        if m < start:
            continue
        adv, fav = (l, h) if side > 0 else (h, l)
        if side * (o - stp) <= 0:                         # opened beyond the stop
            return pnl + left * side * (o - e) - COST, m, k
        if side * (adv - stp) <= 0:
            return pnl + left * side * (stp - e) - COST, m, k
        while k < len(targets) and side * (fav - targets[k]) >= 0:
            pnl += fracs[k] * side * (targets[k] - e); left -= fracs[k]; k += 1
            if be_at is not None and k == be_at and side * (e - stp) > 0:
                stp = e
            if left <= 1e-9:
                return pnl - COST, m, k
        if trail:
            best = max(best, h) if side > 0 else min(best, l)
            if side * (best - e) >= trail:
                ns = best - side * trail
                if side * (ns - stp) > 0:
                    stp = ns
        if m >= min(last, OUT):
            return pnl + left * side * (c - e) - COST, m, k
    return pnl + left * side * (c1[-1][4] - e) - COST, c1[-1][0], k

def small_stop(c1, side, e, start, kind):
    """kind '1m2', '1m3', '5m2', '5m3': beyond the extreme of the last 2 / 3 one- / five-minute candles before
    `start`, +0.02%; at least 0.03% from the entry."""
    tf, n = int(kind[0]), int(kind[2])
    before = [x for x in c1 if x[0] < start]
    if tf == 5:
        blocks = collections.OrderedDict()
        for x in before:
            blocks.setdefault(555 + (x[0] - 555) // 5 * 5, []).append(x)
        done_ = [v for k, v in blocks.items() if k + 4 < start]
        rows = [y for v in done_[-n:] for y in v] or before[-1:]
    else:
        rows = before[-n:]
    ext = min(x[3] for x in rows) if side > 0 else max(x[2] for x in rows)
    s = ext - side * 0.0002 * e
    if side * (e - s) < 0.0003 * e:
        s = e - side * 0.0003 * e
    return s

# ---------------- 0. the calls as they are ----------------
def calls():
    out = []
    for d in DAYS:
        for t in A.day_trades(CX[d], sess[d], 929, True, False, 'classic'):
            if t['taken'] and t['exit']:
                out.append(dict(d=d, t=t))
    return out

def part0_1():
    cs = calls()
    print(f"\n0. NOW: the alert program's calls as they are, {len(cs)} calls")
    line('book half 0.25R, stop to entry, trail (now)', stats([(c['d'], c['t']['exit']['pnl']) for c in cs]))
    print("\n1. SMALL STOP ON THE SAME CALLS (T1-T3 = the next price levels)")
    res, probs = {}, {}
    for kind in ('setup', '1m2', '1m3', '5m2', '5m3'):
        rows = collections.defaultdict(list)
        reach = collections.defaultdict(lambda: [0, 0, 0, 0])
        risk = []
        for c in cs:
            d, t = c['d'], c['t']
            c1, sd, e, st0 = sess[d], t['side'], t['e'], t['known']
            stp = t['stp0'] if kind == 'setup' else small_stop(c1, sd, e, st0, kind)
            if sd * (e - stp) <= 0:
                continue
            R = sd * (e - stp); risk.append(R)
            T = A.target_levels(CX[d], c1, sd, e, st0)
            _, _, k = walk(c1, sd, e, st0, stp, T, (0, 0, 1), None)         # how far it got before the stop
            grp = 'all'
            for g in (grp, t['src']):
                reach[(g, d[:4] if d < '2026' else '2026')][0] += 1
                for j in range(3):
                    reach[(g, d[:4] if d < '2026' else '2026')][j + 1] += k > j
            ex = {
                'all at T1': walk(c1, sd, e, st0, stp, T[:1], (1,)),
                'all at T2 (stop to entry at T1)': walk(c1, sd, e, st0, stp, T[:2], (0, 1), 1),
                'all at T3 (stop to entry at T1)': walk(c1, sd, e, st0, stp, T, (0, 0, 1), 1),
                'half T1 + half T2 (stop to entry)': walk(c1, sd, e, st0, stp, T[:2], (0.5, 0.5), 1),
                'all at 2x stop': walk(c1, sd, e, st0, stp, (e + sd * 2 * R,), (1,)),
                'all at 3x stop': walk(c1, sd, e, st0, stp, (e + sd * 3 * R,), (1,)),
                'now: half 0.25R, entry, trail 1R': walk(c1, sd, e, st0, stp, (e + sd * 0.25 * R,), (0.5,), 1, trail=R),
            }
            for k_, v in ex.items():
                rows[k_].append((d, v[0]))
        print(f"  stop {kind}: average {sum(risk) / max(1, len(risk)):.0f} points from the entry")
        for k_, v in rows.items():
            s = stats(v); res[f'{kind} | {k_}'] = s
            line(f'  {kind} | {k_}', s, 50)
        probs[kind] = {f'{g}|{y}': v for (g, y), v in reach.items()}
    return cs, res, probs

# ---------------- 2. reversals at key levels ----------------
def day_levels(cx, c1):
    lv, yh, yl = cx['lv'], cx['yh'], cx['yl']
    P = lv['p']
    L = {'P': P, 'CPR top': lv['top'], 'CPR bottom': lv['bot'], 'R1': 2 * P - yl, 'S1': 2 * P - yh,
         'R2': P + (yh - yl), 'S2': P - (yh - yl), 'yesterday high': yh, 'yesterday low': yl}
    for i, x in enumerate(cx['lines']):
        L[f'volume line {i + 1}'] = x
    if cx.get('poc1') is not None:
        L['POC'] = cx['poc1']
    first = [x for x in c1 if x[0] < A.RANGE_END]
    L['15-min high'], L['15-min low'] = max(x[2] for x in first), min(x[3] for x in first)
    return L

def kind_of(name):
    return 'volume line' if name.startswith('volume line') else name

def signals(d, confirm, nk):
    """Every 'doesn't hold' at a level on day d: (minute of entry, side, entry, stop, level name, level)."""
    c1 = sess[d]
    L = day_levels(CX[d], c1)
    out, used = [], set()
    by_m = {x[0]: i for i, x in enumerate(c1)}
    for i in range(1, len(c1)):
        m, o, h, l, c = c1[i]
        if m < A.RANGE_END or m > 870:
            continue
        pc = c1[i - 1][4]
        for name, lvl in L.items():
            for side in (-1, 1):                          # -1: came up to it, SELL; 1: came down to it, BUY
                if (name, side) in used:
                    continue
                touched = (h >= lvl and pc < lvl) if side < 0 else (l <= lvl and pc > lvl)
                if not touched:
                    continue
                e = j = None
                if confirm == 'c1':
                    if (c < lvl) if side < 0 else (c > lvl):
                        e, j = c, i
                elif confirm == 'c3':
                    k = i
                    while k < len(c1) and k <= i + 2 and ((c1[k][4] < lvl) if side < 0 else (c1[k][4] > lvl)):
                        k += 1
                    if k == i + 3:
                        e, j = c1[i + 2][4], i + 2
                else:                                     # c5: the 5-minute candle the touch is in closes back
                    end = 555 + (m - 555) // 5 * 5 + 4
                    if end in by_m:
                        k = by_m[end]
                        blk = c1[i:k + 1]
                        if (max(x[2] for x in blk) < lvl * 1.0015 and blk[-1][4] < lvl) if side < 0 else \
                           (min(x[3] for x in blk) > lvl * 0.9985 and blk[-1][4] > lvl):
                            e, j = blk[-1][4], k
                if e is None:
                    used.add((name, side))                # it held beyond the level: not this level again today
                    continue
                ext = max(x[2] for x in c1[max(0, j - nk + 1):j + 1]) if side < 0 else min(x[3] for x in c1[max(0, j - nk + 1):j + 1])
                ext = max(ext, lvl) if side < 0 else min(ext, lvl)
                stp = ext - side * 0.0002 * lvl
                used.add((name, side))
                out.append((c1[j][0], side, e, stp, name, lvl, L))
    return sorted(out, key=lambda x: x[0])

SIG = {}
def level_trades(confirm, nk, maxr, tgt, last):
    """Simulated level trades (one at a time) for every day: [(day, pnl, side, level name, entry minute)]."""
    out = []
    for d in DAYS:
        key = (d, confirm, nk)
        if key not in SIG:
            SIG[key] = signals(d, confirm, nk)
        busy = -1
        c1 = sess[d]
        for m, side, e, stp, name, lvl, L in SIG[key]:
            if m <= busy:
                continue
            R = side * (e - stp)
            if R <= 0 or R > maxr * e or R < 0.0002 * e:
                continue
            if tgt == 'next':
                ahead = sorted((x for x in L.values() if side * (x - e) >= max(R, 0.0005 * e)), key=lambda x: side * (x - e))
                if not ahead:
                    continue
                T = ahead[0]
            else:
                T = e + side * float(tgt[:-1]) * R
            pnl, xm, _ = walk(c1, side, e, m + 1, stp, (T,), (1,), last=(m + 60 if last == '60m' else OUT))
            out.append((d, pnl, side, name, m))
            busy = xm
    return out

def part2():
    print("\n2. REVERSAL AT KEY LEVELS (very small stop), chosen on 2023-2025, then 2026")
    res = {}
    for confirm, nk, maxr, tgt, last in itertools.product(('c1', 'c3', 'c5'), (2, 3), (0.0008, 0.0012, 0.002),
                                                          ('next', '1.5R', '2R', '3R'), ('60m', '3:15')):
        tr = level_trades(confirm, nk, maxr, tgt, last)
        res[(confirm, nk, maxr, tgt, last)] = (stats([(d, p) for d, p, *_ in tr]), tr)
    train = lambda s: sum(s[y]['net'] for y in YEARS[:3])
    ranked = sorted(res.items(), key=lambda kv: train(kv[1][0]), reverse=True)
    pos = sum(1 for k, (s, _) in res.items() if all(s[y]['net'] > 0 for y in YEARS))
    print(f"  {len(res)} versions; positive in every year 2023-2026: {pos}; positive in 2023-2025 together: "
          f"{sum(1 for k, (s, _) in res.items() if train(s) > 0)}")
    print("  the 8 best on 2023-2025, and how they did in 2026:")
    for k, (s, _) in ranked[:8]:
        line(f"{k[0]} last{k[1]} stop<={k[2] * 100:.2f}% {k[3]} {k[4]}", s)
    print("  the 3 worst on 2023-2025:")
    for k, (s, _) in ranked[-3:]:
        line(f"{k[0]} last{k[1]} stop<={k[2] * 100:.2f}% {k[3]} {k[4]}", s)
    best = ranked[0]
    print(f"  the best version by level (all years):")
    by = collections.defaultdict(list)
    for d, p, side, name, m in best[1][1]:
        by[('SELL at ' if side < 0 else 'BUY at ') + kind_of(name)].append((d, p))
    for k in sorted(by, key=lambda k: -sum(p for _, p in by[k])):
        line(k, stats(by[k]))
    return res, best

# ---------------- 3. rotation P <-> R1 / S1 ----------------
def part3():
    print("\n3. ROTATION: after the first touch of R1 (S1) on the day")
    cnt = collections.Counter()
    for d in DAYS:
        c1 = sess[d]
        L = day_levels(CX[d], c1)
        P, R1, S1 = L['P'], L['R1'], L['S1']
        for name, lvl, side in (('R1', R1, -1), ('S1', S1, 1)):
            if c1[0][1] * side < lvl * side or (side < 0 and c1[0][1] >= R1) or (side > 0 and c1[0][1] <= S1):
                continue                                    # opened beyond the level: not a 'reach'
            i = next((i for i, x in enumerate(c1) if (x[2] >= lvl if side < 0 else x[3] <= lvl)), None)
            if i is None:
                continue
            cnt[name + ' reached'] += 1
            far = lvl * (1 - side * 0.002)
            first = None
            for x in c1[i + 1:]:
                if (x[3] <= P) if side < 0 else (x[2] >= P):
                    first = 'P'; break
                if (x[2] >= far) if side < 0 else (x[3] <= far):
                    first = 'beyond'; break
            cnt[f'{name} then {first}'] += 1
            if first == 'P':
                j = next(k for k in range(i + 1, len(c1)) if ((c1[k][3] <= P) if side < 0 else (c1[k][2] >= P)))
                other = S1 if side < 0 else R1
                if any((x[3] <= other) if side < 0 else (x[2] >= other) for x in c1[j:]):
                    cnt[f'{name} then P then {"S1" if side < 0 else "R1"}'] += 1
    for name in ('R1', 'S1'):
        n = cnt[name + ' reached']
        if not n:
            continue
        o = 'S1' if name == 'R1' else 'R1'
        print(f"  {name} reached on {n} days: back to P first {cnt[name + ' then P']} ({100 * cnt[name + ' then P'] / n:.0f}%), "
              f"0.2% beyond {name} first {cnt[name + ' then beyond']} ({100 * cnt[name + ' then beyond'] / n:.0f}%), neither "
              f"{cnt[name + ' then None']}; of those back at P, on to {o} {cnt[f'{name} then P then {o}']}")
    return dict(cnt)

if __name__ == '__main__':
    print(f"{NM.upper()} {DAYS[0]} - {DAYS[-1]} ({len(DAYS)} days), costs {COST:g} points a trade; per year: trades, won %, net points")
    cs, r1, probs = part0_1()
    print("\n  how often the next levels were reached before the small stop (T1 / T2 / T3), 2023-2025 -> 2026:")
    for kind, pr in probs.items():
        for g in ('all', 'BREAKOUT', 'MAGNET', 'VOLUME LINE'):
            a = [pr.get(f'{g}|{y}', [0, 0, 0, 0]) for y in ('2023', '2024', '2025')]
            n = sum(x[0] for x in a)
            b = pr.get(f'{g}|2026', [0, 0, 0, 0])
            if n:
                print(f"    stop {kind:5} {g:11} 2023-25: {n:3} calls, T1 {100 * sum(x[1] for x in a) / n:3.0f}% T2 {100 * sum(x[2] for x in a) / n:3.0f}% "
                      f"T3 {100 * sum(x[3] for x in a) / n:3.0f}% | 2026: {b[0]:3} calls, T1 {100 * b[1] / max(1, b[0]):3.0f}% "
                      f"T2 {100 * b[2] / max(1, b[0]):3.0f}% T3 {100 * b[3] / max(1, b[0]):3.0f}%")
    r2, best = part2()
    r3 = part3()
    # 4. calls (small stop, best exit) + level trades with / against the call
    print("\n4. CALLS + LEVEL TRADES (the best version of 2): with the call's direction (pullbacks) / against it (reversals)")
    calls_side = {}
    for c in cs:
        calls_side.setdefault(c['d'], []).append((c['t']['m'], c['t']['side']))
    w, ag, none = [], [], []
    for d, p, side, name, m in best[1][1]:
        prior = [s for mm, s in calls_side.get(d, []) if mm < m]
        (none if not prior else w if prior[-1] == side else ag).append((d, p))
    line('level trades with the call (pullback / re-entry)', stats(w))
    line('level trades against the call (reversal)', stats(ag))
    line('level trades on days / before any call', stats(none))
    json.dump(dict(part1={k: v for k, v in r1.items()}, probs=probs, part2={' '.join(map(str, k)): v[0] for k, v in r2.items()},
                   best=' '.join(map(str, best[0])), part3=r3), open(f'../.cache/levels_{NM}.json', 'w'))

"""How high can the CPR Breakout's win rate go while it still makes money?

    python cpr_orb_winrate.py nifty        (or sensex)

Base: the CPR Breakout entry (touch of the first 15-minute high / low, 9:30-13:00, stop at the other side of the
range, no trade against today's CPR vs yesterday's). Varied:
  width   narrow-CPR days only / every day
  exit    fixed target 0.1R .. 3R (R = entry to stop), trail (stop 1R behind the best price after +1R), or
          half (book half at the target, stop to entry, trail the rest)
  rev     reversal trade after a failed break, or not
  trend filters, each on or off (the trade must agree with it):
    d20     yesterday's close vs the 20-day average close (above -> buys only)
    d5      yesterday's close vs the close 5 days before
    prev    yesterday's candle colour
    gap     today's open vs yesterday's close
    first   the first 15-minute candle's colour
    cprnow  at entry, price is beyond the CPR in the trade's direction (above it for buys)
    ema     the 5-minute EMA 50
A trade counts as won when it made money after costs (4 Nifty / 12 Sensex points).
"""
import collections, itertools, json, sys
import cpr_orb as C

B, one, LV, TEST, COST = C.B, C.one, C.LV, C.TEST, C.COST
DAYS = B.days
IDX = {d: i for i, d in enumerate(DAYS)}
FEAT = {}
for d in TEST:
    i = IDX[d]; cl = [B.DAY[x][3] for x in DAYS[i - 20:i]]
    yo, yh, yl, yc = B.DAY[DAYS[i - 1]]; o = one[d][0][1]
    first = [x for x in one[d] if x[0] < 570]
    sg = lambda v: 1 if v > 0 else -1 if v < 0 else 0
    FEAT[d] = dict(d20=sg(yc - sum(cl) / 20), d5=sg(yc - B.DAY[DAYS[i - 6]][3]), prev=sg(yc - yo), gap=sg(o - yc),
                   first=sg(first[-1][4] - first[0][1]))
FILTERS = ('d20', 'd5', 'prev', 'gap', 'first', 'cprnow', 'ema')

def sim_half(d, side, start, e, stp, tgt, R):
    """Half off at the target, then stop to entry and trail 1R behind the best price."""
    half, best = None, e
    for m, o, h, l, c in one[d]:
        if m < start: continue
        for px in C.path(o, h, l, c):
            if side * (px - stp) <= 0:
                rest = side * (stp - e)
                return (rest if half is None else (half + rest) / 2) - COST, m
            if half is None and side * (px - tgt) >= 0:
                half = side * (tgt - e)
                if side * (e - stp) > 0: stp = e
        best = max(best, h) if side > 0 else min(best, l)
        if side * (best - e) >= R:
            ns = best - side * R
            if side * (ns - stp) > 0: stp = ns
        if m >= C.T_OUT:
            rest = side * (c - e)
            return (rest if half is None else (half + rest) / 2) - COST, m
    rest = side * (one[d][-1][4] - e)
    return (rest if half is None else (half + rest) / 2) - COST, one[d][-1][0]

def trade(d, side, e, start, stp, ex):
    R = side * (e - stp)
    kind, k = ex
    if kind == 'fixed': return C.sim(d, side, start, e, stp, e + side * k * R, 'fixed', R)
    if kind == 'trail': return C.sim(d, side, start, e, stp, None, 'trail', R)
    return sim_half(d, side, start, e, stp, e + side * k * R, R)

def day(d, wf, ex, rev, fl):
    lv = LV[d]
    if wf == 'narrow' and lv['rank'] >= 1 / 3: return []
    first = [x for x in one[d] if x[0] < 570]
    orh, orl = max(x[2] for x in first), min(x[3] for x in first)
    f = FEAT[d]
    for side, e, start, m in C.candidates(d, 'touch', orh, orl, 570):
        if side == -C.REL[d]: continue
        if any(f[k] == -side or f[k] == 0 for k in fl if k in f): continue
        if 'cprnow' in fl and side * (e - (lv['top'] if side > 0 else lv['bot'])) <= 0: continue
        if 'ema' in fl and side * (e - C.ema_at(d, m)) <= 0: continue
        stp = orl if side > 0 else orh
        if side * (e - stp) <= 0: continue
        pnl, mx = trade(d, side, e, start, stp, ex)
        out = [(d, pnl)]
        if rev and pnl <= 0:
            for s2, e2, st2, m2 in C.candidates(d, 'touch', orh, orl, mx + 1):
                if s2 != -side: continue
                stp2 = orl if s2 > 0 else orh
                if s2 * (e2 - stp2) <= 0: break
                out.append((d, trade(d, s2, e2, st2, stp2, ex)[0])); break
        return out
    return []

EXITS = [('fixed', k) for k in (0.1, 0.25, 0.5, 0.75, 1, 1.5, 2, 3)] + [('trail', 0)] + [('half', k) for k in (0.25, 0.5, 1)]
FL = [c for n in range(0, 4) for c in itertools.combinations(FILTERS, n)]       # up to 3 filters at once
GRID = list(itertools.product(('narrow', 'any'), EXITS, (False, True), FL))

def evaluate(P):
    wf, ex, rev, fl = P
    ts = [t for d in TEST for t in day(d, wf, ex, rev, fl)]
    s90 = set(TEST[-90:]); p90 = [v for d, v in ts if d in s90]; pa = [v for d, v in ts]
    yrs = collections.defaultdict(float)
    for d, v in ts: yrs[d[:4]] += v
    return dict(P=[wf, list(ex), rev, list(fl)], n90=len(p90), w90=sum(v > 0 for v in p90), net90=sum(p90),
                won90=sum(v for v in p90 if v > 0), lost90=sum(v for v in p90 if v <= 0),
                n=len(pa), w=sum(v > 0 for v in pa), net=sum(pa), yrs=dict(yrs))

if __name__ == '__main__':
    import multiprocessing as mp
    with mp.Pool() as pool: res = pool.map(evaluate, GRID, chunksize=25)
    json.dump(res, open(f'../.cache/cpr_winrate_{B.name}.json', 'w'))
    print(f"{B.name.upper()}: {len(res)} versions")
    print("Trade-off with no trend filter, narrow days, reversal on: target size -> win rate and profit")
    for r in res:
        if r['P'][0] == 'narrow' and r['P'][2] and not r['P'][3]:
            print(f"  {str(r['P'][1]):16} last 90: {r['n90']:3} trades, won {100*r['w90']/max(1,r['n90']):3.0f}%, net {r['net90']:+7,.0f} | "
                  f"since 2023: {r['n']:4} trades, won {100*r['w']/max(1,r['n']):3.0f}%, net {r['net']:+8,.0f}")

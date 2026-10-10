"""Scalping the CPR / pivot / 15-minute levels: small fixed targets and stops, up to 5 trades a day.

    python cpr_scalp.py nifty        (or sensex)

Every time price crosses a level on a 1-minute candle (followed inside the candle: green open-low-high-close, red
open-high-low-close), a trade can start at the level:
  levels  or   the first 15-minute candle's high and low (from 9:30)
          cpr  the CPR top and bottom (from 9:16)
          piv  R1, S1, R2, S2 (from 9:16)
          all  all of them
  mode    break  trade in the direction price crossed the level
          bounce trade back the other way (the level holds)
  target  10 / 15 / 20 / 30 points, stop 10 / 20 / 30 / 40 points (Nifty-sized: scaled to the index price,
          so about 3.2x on Sensex)
  time    out after 10 or 30 minutes, or hold to 15:15
  width   narrow-CPR days only / every day
  filter  none / cpr (open above the CPR -> buys only, below -> sells only) / rel (no trade against today's CPR vs
          yesterday's) / first (with the first 15-minute candle's colour)
One trade at a time, new entries 9:16-14:30, at most 5 a day. Costs: 4 Nifty / 12 Sensex points a trade.
A trade counts as won when it made money after costs.
"""
import collections, itertools, json, statistics as st
import cpr_orb as C

B, one, LV, TEST, COST = C.B, C.one, C.LV, C.TEST, C.COST
REF = 22500.0

def path(o, h, l, c): return (o, l, h, c) if c >= o else (o, h, l, c)

def day(d, P):
    lvset, mode, T, S, H, wf, flt = P
    lv = LV[d]
    if wf == 'narrow' and lv['rank'] >= 1 / 3: return []
    first = [x for x in one[d] if x[0] < 570]
    orh, orl = max(x[2] for x in first), min(x[3] for x in first)
    o0 = one[d][0][1]; cb = 1 if o0 > lv['top'] else -1 if o0 < lv['bot'] else 0
    fc = 1 if first[-1][4] > first[0][1] else -1 if first[-1][4] < first[0][1] else 0
    early = {'cpr': [lv['top'], lv['bot']], 'piv': [lv['r1'], lv['s1'], lv['r2'], lv['s2']]}
    out, pos, prev = [], None, one[d][0][4]
    for m, o, h, l, c in one[d]:
        if m < 556: continue
        pts = (prev,) + path(o, h, l, c); prev = c
        k = 0
        while k < len(pts) - 1:
            a, b = pts[k], pts[k + 1]
            if pos is None:
                if len(out) >= 5 or m >= 870: break
                lvls = []
                if lvset in ('cpr', 'all'): lvls += early['cpr']
                if lvset in ('piv', 'all'): lvls += early['piv']
                if lvset in ('or', 'all') and m >= 570: lvls += [orh, orl]
                hit = None
                for L in lvls:
                    if a < L <= b or a > L >= b:
                        dist = abs(L - a)
                        if hit is None or dist < hit[1]: hit = (L, dist, 1 if b > a else -1)
                if hit is None: k += 1; continue
                L, _, cross = hit
                side = cross if mode == 'break' else -cross
                ok = not ((flt == 'cpr' and side != cb) or (flt == 'rel' and side == -C.REL[d]) or (flt == 'first' and (m < 570 or side != fc)))
                if not ok: k += 1; continue
                e = L if k > 0 else b                      # jumped through it between candles: fill at the open
                sc = e / REF
                pos = dict(side=side, e=e, stp=e - side * S * sc, tgt=e + side * T * sc, m0=m)
                if k == 0: k += 1
                else: pts = pts[:k] + (L,) + pts[k + 1:]   # the rest of this segment (level -> b) can already exit
                continue
            sd, e = pos['side'], pos['e']
            # walk from a to b: stop or target crossed?
            for px in (b,):
                if sd * (px - pos['stp']) <= 0: out.append((d, sd * (pos['stp'] - e) - COST, m - pos['m0'])); pos = None; break
                if sd * (px - pos['tgt']) >= 0: out.append((d, sd * (pos['tgt'] - e) - COST, m - pos['m0'])); pos = None; break
            k += 1
        if pos is not None and ((H and m >= pos['m0'] + H) or m >= C.T_OUT):
            out.append((d, pos['side'] * (c - pos['e']) - COST, m - pos['m0'])); pos = None
        if m >= C.T_OUT: break
    return out

GRID = list(itertools.product(('or', 'cpr', 'piv', 'all'), ('break', 'bounce'), (10, 15, 20, 30), (10, 20, 30, 40), (10, 30, 0),
                              ('narrow', 'any'), ('none', 'cpr', 'rel', 'first')))

def evaluate(P):
    ts = [t for d in TEST for t in day(d, P)]
    s90 = set(TEST[-90:]); p90 = [t[1] for t in ts if t[0] in s90]; pa = [t[1] for t in ts]
    yrs = collections.defaultdict(float)
    for t in ts: yrs[t[0][:4]] += t[1]
    return dict(P=list(P), n90=len(p90), w90=sum(v > 0 for v in p90), net90=sum(p90), won90=sum(v for v in p90 if v > 0),
                lost90=sum(v for v in p90 if v <= 0), n=len(pa), w=sum(v > 0 for v in pa), net=sum(pa), yrs=dict(yrs),
                hold=st.median([t[2] for t in ts]) if ts else 0)

if __name__ == '__main__':
    import multiprocessing as mp
    with mp.Pool() as pool: res = pool.map(evaluate, GRID, chunksize=25)
    json.dump(res, open(f'../.cache/cpr_scalp_{B.name}.json', 'w'))
    wr = lambda r, a='90': r['w' + a] / max(1, r['n' + a]) if a else r['w'] / max(1, r['n'])
    print(f"{B.name.upper()}: {len(res)} scalping versions")
    for thr in (0.9, 0.8, 0.7):
        hi = [r for r in res if r['n90'] >= 20 and wr(r) >= thr]
        print(f"  won {int(thr*100)}%+ in the last 90 sessions (20+ trades): {len(hi)}; made money there: {sum(r['net90'] > 0 for r in hi)}; "
              f"also since 2023: {sum(r['net90'] > 0 and r['net'] > 0 for r in hi)}")
    print("  best 10 since 2023 that also made money in the last 90 (20+ trades):")
    for r in sorted([r for r in res if r['n90'] >= 20 and r['net90'] > 0], key=lambda r: -r['net'])[:10]:
        print(f"    {str(r['P']):55} last90 {r['n90']} tr {100*wr(r):.0f}% {r['net90']:+,.0f} | since 2023 {r['n']} tr {100*wr(r, ''):.0f}% {r['net']:+,.0f} | hold {r['hold']:.0f} min")

"""High-accuracy versions (asked on 15 October 2026): small fixed targets (Nifty 30 / 40 / 50, Sensex 100 / 150 /
200 points), limited losses, several entries a day; a version counts only if it won at least 70% of its trades AND
made money in every year 2023, 2024 and 2025 (chosen without 2026); then 2026.

    python highwin.py nifty        (or sensex)

Entries (each one at a time, as many a day as come):
  ours        the alert program's calls (default settings): the entry and its own stop
  A+ tf/piv/sweep   the A+ setup (aplus_setup.py): a limit order in the middle of the fair value gap, stop beyond
              the sweep
Direction filter: none / cpr (BUY only above the CPR's pivot, SELL only below) / day (only the way of the day's first
  call of the alert program, after it).
Stop: the entry's own (own), moved closer to at most 1.5x / 2x the target (cap1.5 / cap2), or the trade skipped when
  its own stop is more than 1.5x / 2x the target (skip1.5 / skip2).
Breakeven: none, or the stop to the entry once price is 60% of the way to the target (be).
Out at the target, the stop, or 3:15. Costs 4 Nifty / 12 Sensex points a trade; a 1-minute candle reaching both the
stop and the target counts as the stop. Won = closed with a profit after costs.
"""
import collections, itertools, json, sys
import levels_style as LS
import aplus_setup as AP

A = LS.A
NM, COST = LS.NM, LS.COST
DAYS = LS.DAYS
TGTS = {'nifty': (30, 40, 50), 'sensex': (100, 150, 200)}[NM]

def gen_ours():
    out = collections.defaultdict(list)
    for d in DAYS:
        for t in A.day_trades(LS.CX[d], LS.sess[d], 929, True, False, 'classic'):
            if t['taken']:
                out[d].append(dict(m=t['known'], side=t['side'], px=t['e'], limit=False, stp=t['stp0'], src=t['src']))
    return out

def gen_ap(tf, piv, sweep):
    out = collections.defaultdict(list)
    for d in DAYS:
        for placed, side, top, mid, ext, c1x, far in AP.setups(d, tf, piv, sweep):
            out[d].append(dict(m=placed, side=side, px=mid, limit=True, stp=ext - side * 0.0002 * mid, src='A+'))
    return out

OURS_FIRST = {}

def run(sig, filt, T, stop, be):
    res = []
    for d in DAYS:
        c1 = LS.sess[d]
        P = LS.CX[d]['lv']['p']
        first = OURS_FIRST.get(d)
        busy = -1
        for s in sig.get(d, []):
            if s['m'] <= busy or s['m'] > 870:
                continue
            side = s['side']
            if filt == 'cpr' and side * (s['px'] - P) <= 0:
                continue
            if filt == 'day' and (first is None or s['m'] <= first[0] or side != first[1]):
                continue
            # fill
            if s['limit']:
                fill = None
                for m, o, h, l, c in c1:
                    if m < s['m']:
                        continue
                    if m > min(s['m'] + 59, 870):
                        break
                    if (o <= s['stp']) if side > 0 else (o >= s['stp']):
                        break
                    if (l <= s['px']) if side > 0 else (h >= s['px']):
                        fill = (m, min(o, s['px']) if side > 0 else max(o, s['px'])); break
                if not fill:
                    continue
                fm, e = fill
                start = fm                       # the fill candle counts (pessimistic: it may reach the stop)
            else:
                fm, e, start = s['m'], s['px'], s['m']
            own = side * (e - s['stp'])
            if own <= 0:
                continue
            if stop.startswith('skip') and own > float(stop[4:]) * T:
                continue
            R = min(own, float(stop[3:]) * T) if stop.startswith('cap') else own
            stp = e - side * R
            tg = e + side * T
            pnl, xm, k = walk_be(c1, side, e, start, stp, tg, be, T, s['limit'])
            res.append((d, pnl))
            busy = xm
    return res

def walk_be(c1, side, e, start, stp, tg, be, T, limit=False):
    for m, o, h, l, c in c1:
        if m < start:
            continue
        adv, fav = (l, h) if side > 0 else (h, l)
        if side * (o - stp) <= 0 and m > start:
            return side * (o - e) - COST, m, 0
        if side * (adv - stp) <= 0:
            return side * (stp - e) - COST, m, 0
        if limit and m == start:
            continue                              # the fill candle: its high / low may have come before the fill
        if side * (fav - tg) >= 0:
            return T - COST, m, 1
        if be and side * (fav - e) >= 0.6 * T and side * (e - stp) > 0:
            stp = e
        if m >= LS.OUT:
            return side * (c - e) - COST, m, 0
    return side * (c1[-1][4] - e) - COST, c1[-1][0], 0

def summary(rows):
    out = {}
    for y in LS.YEARS + ('all',):
        p = [x for d, x in rows if y == 'all' or d[:4] == y]
        w = [x for x in p if x > 0]; ls_ = [x for x in p if x <= 0]
        eq = pk = dd = 0
        for v in p:
            eq += v; pk = max(pk, eq); dd = min(dd, eq - pk)
        out[y] = dict(n=len(p), win=round(100 * len(w) / len(p)) if p else 0, net=round(sum(p)),
                      aw=round(sum(w) / len(w)) if w else 0, al=round(sum(ls_) / len(ls_)) if ls_ else 0, dd=round(dd))
    return out

def show(label, s, w=48):
    ys = ' | '.join(f"{y} {s[y]['n']:3} tr {s[y]['win']:3}% {s[y]['net']:+6,}" for y in LS.YEARS)
    a = s['all']
    print(f"  {label:{w}} {ys} | avg win {a['aw']:+4} loss {a['al']:+5} fall {a['dd']:+6,}")

def qualifies(s):
    return all(s[y]['win'] >= 70 and s[y]['net'] > 0 and s[y]['n'] >= 10 for y in ('2023', '2024', '2025'))

if __name__ == '__main__':
    print(f"{NM.upper()}: small fixed targets {TGTS}, costs {COST:g} points; per year: trades, won %, net points")
    gens = {'ours': gen_ours()}
    for d, ss in gens['ours'].items():
        if ss:
            OURS_FIRST[d] = (ss[0]['m'], ss[0]['side'])
    for tf, piv, sw in itertools.product((1, 3, 5), (1, 2), ('wick', '2bar')):
        gens[f'A+ {tf}m piv{piv} {sw}'] = gen_ap(tf, piv, sw)
    res = {}
    for g, filt, T, stop, be in itertools.product(gens, ('none', 'cpr', 'day'), TGTS,
                                                  ('own', 'cap1.5', 'cap2', 'skip1.5', 'skip2'), (False, True)):
        if g == 'ours' and filt == 'day':
            continue
        res[(g, filt, T, stop, be)] = summary(run(gens[g], filt, T, stop, be))
    q = [k for k, s in res.items() if qualifies(s)]
    print(f"\n  {len(res)} versions; won >= 70% and made money in each of 2023, 2024, 2025: {len(q)}")
    lab = lambda k: f"{k[0]} | {k[1]} | T{k[2]} | {k[3]} | {'be' if k[4] else 'no be'}"
    for k in sorted(q, key=lambda k: -min(res[k][y]['net'] for y in ('2023', '2024', '2025')))[:20]:
        show(lab(k), res[k], 60)
    print("\n  the highest win rates over 2023-2025 (whatever the money), for comparison:")
    for k in sorted(res, key=lambda k: -min(res[k][y]['win'] for y in ('2023', '2024', '2025')))[:8]:
        show(lab(k), res[k], 60)
    print("\n  our calls with small targets:")
    for k in sorted((k for k in res if k[0] == 'ours' and k[1] == 'none' and not k[4]), key=lambda k: (k[2], k[3])):
        show(lab(k), res[k], 60)
    json.dump({' | '.join(map(str, k)): v for k, v in res.items()}, open(f'../.cache/highwin_{NM}.json', 'w'))
    json.dump([' | '.join(map(str, k)) for k in q], open(f'../.cache/highwin_q_{NM}.json', 'w'))

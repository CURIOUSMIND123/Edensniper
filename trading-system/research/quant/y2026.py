"""2026 only: why CPR Magnet and CPR Breakout trades lost, and which adjustments help (volume zones, Fibonacci, trend).

    python y2026.py nifty        (or sensex)

Trades (same rules as the Pine indicators):
  magnet   cpr_magnet.pine: 9:15 candle 0.2%+ beyond a CPR that isn't narrow -> back to the CPR edge, stop 0.3%
  trail    cpr_breakout.pine with Exit = Trail and the gap filter off
  scalp    cpr_breakout.pine defaults (book half at 0.25R, opening-gap direction)
Real volume: NIFTYBEES (the Nifty ETF) 1-minute volume, spread over the index's 1-minute candle range (the index
itself has no volume; Sensex uses the same Nifty ETF volume as a proxy). Volume zones from the previous 15 / 30
sessions: point of control (POC), value area (70%), high-volume nodes (HVN, local peaks).
Fibonacci: the previous 30 sessions' high and low, retracements 23.6 / 38.2 / 50 / 61.8 / 78.6%, measured in the
direction of the move (low first then high = up move).
Every adjustment is checked on January-June 2026 and then on July-9 October 2026 separately.
"""
import collections, json, statistics as st, sys
import numpy as np
import cpr_orb as C
import cpr_orb_winrate as W
import pa_ml as PA

B = C.B
one, five, LV, DAY, days, COST = B.one, B.five, B.LV, B.DAY, B.days, B.COST
IDX = {d: i for i, d in enumerate(days)}
D26 = [d for d in C.TEST if d >= '2026-01-01']
H1 = {d for d in D26 if d < '2026-07-01'}
BIN = {'nifty': 5.0, 'sensex': 16.0, 'btcist': 25.0}[B.name]

# ---------------- real-volume profile (NIFTYBEES volume on the index's price range) ----------------
bees = json.load(open('../.cache/niftybees_1m.json')) if B.name != 'btcist' else \
    {k: [0, 0, 0, 0, v] for k, v in json.load(open('../.cache/btcist_vol.json')).items()}   # Bitcoin: its own volume
VH = {}
for d in days:
    if d < '2025-10-01': continue
    lo = min(x[3] for x in one[d]); hi = max(x[2] for x in one[d]); base = int(lo // BIN)
    h = np.zeros(int(hi // BIN) - base + 1)
    for m, o, hh, l, c in one[d]:
        v = bees.get(f"{d} {m // 60:02d}:{m % 60:02d}", [0, 0, 0, 0, 0])[4]
        a, b = int(l // BIN) - base, int(hh // BIN) - base
        h[a:b + 1] += v / (b - a + 1)
    VH[d] = (base, h)

def profile(d, n):
    """POC, VAH, VAL and high-volume nodes from the n sessions before d."""
    ds = days[IDX[d] - n:IDX[d]]
    base = min(VH[x][0] for x in ds); top = max(VH[x][0] + len(VH[x][1]) for x in ds)
    p = np.zeros(top - base)
    for x in ds:
        b0, h = VH[x]; p[b0 - base:b0 - base + len(h)] += h
    k = int(np.argmax(p)); tot = p.sum(); a = b = k; s = p[k]
    while s < 0.7 * tot:
        up = p[b + 1] if b + 1 < len(p) else -1; dn = p[a - 1] if a > 0 else -1
        if up >= dn: b += 1; s += up
        else: a -= 1; s += dn
    sm = np.convolve(p, np.ones(3) / 3, 'same'); thr = np.percentile(sm[sm > 0], 70)
    hvn = [(base + i + 0.5) * BIN for i in range(1, len(sm) - 1) if sm[i] >= thr and sm[i] >= sm[i - 1] and sm[i] >= sm[i + 1]]
    return dict(poc=(base + k + 0.5) * BIN, vah=(base + b + 1) * BIN, val=(base + a) * BIN, hvn=hvn)

def fib(d, n=30):
    ds = days[IDX[d] - n:IDX[d]]
    hi_d = max(ds, key=lambda x: DAY[x][1]); lo_d = min(ds, key=lambda x: DAY[x][2])
    H, L = DAY[hi_d][1], DAY[lo_d][2]; up = IDX[hi_d] > IDX[lo_d]
    lv = [H - r * (H - L) if up else L + r * (H - L) for r in (0.236, 0.382, 0.5, 0.618, 0.786)]
    return dict(levels=lv + [H, L], up=up, H=H, L=L)

PROF15 = {d: profile(d, 15) for d in D26}; PROF30 = {d: profile(d, 30) for d in D26}; FIB = {d: fib(d) for d in D26}

def atr_at(d, m):
    j = max(0, (m - 555) // 5 - 1)
    return PA.ATR[(d, min(j, len(five[d]) - 1))]

# ---------------- the three strategies, with entry details ----------------
def magnet(d):
    lv = LV[d]
    if lv['rank'] < 1 / 3: return []
    o, e = one[d][0][1], one[d][0][4]
    side = -1 if o > lv['top'] else 1 if o < lv['bot'] else 0
    if not side: return []
    edge = lv['top'] if side < 0 else lv['bot']
    if side * (edge - e) < 0.002 * e: return []
    pnl, mx = B.sim(d, side, 556, e, e - side * 0.003 * e, edge)
    return [dict(d=d, side=side, m=556, e=e, tgt=edge, risk=0.003 * e, pnl=pnl, mx=mx)]

def breakout(d, mode):
    lv = LV[d]
    if lv['rank'] >= 1 / 3: return []
    first = [x for x in one[d] if x[0] < 570]; orh, orl = max(x[2] for x in first), min(x[3] for x in first)
    f = W.FEAT[d]; out = []
    for side, e, start, m in C.candidates(d, 'touch', orh, orl, 570):
        if side == -C.REL[d]: continue
        if mode == 'scalp' and f['gap'] != side: continue
        stp = orl if side > 0 else orh; R = side * (e - stp)
        if R <= 0: continue
        ex = ('half', 0.25) if mode == 'scalp' else ('trail', 0)
        pnl, mx = W.trade(d, side, e, start, stp, ex)
        out.append(dict(d=d, side=side, m=m, e=e, tgt=e + side * R, risk=R, pnl=pnl, mx=mx))
        if pnl <= 0:
            for s2, e2, st2, m2 in C.candidates(d, 'touch', orh, orl, mx + 1):
                if s2 != -side: continue
                stp2 = orl if s2 > 0 else orh; R2 = s2 * (e2 - stp2)
                if R2 <= 0: break
                p2, mx2 = W.trade(d, s2, e2, st2, stp2, ex)
                out.append(dict(d=d, side=s2, m=m2, e=e2, tgt=e2 + s2 * R2, risk=R2, pnl=p2, mx=mx2, rev=1)); break
        return out
    return []

def describe(t):
    """Measurements at entry, all known at that moment, signed so that + means 'in the trade's favour'."""
    d, s, e = t['d'], t['side'], t['e']; i = IDX[d]; a = atr_at(d, t['m'])
    yo, yh, yl, yc = DAY[days[i - 1]]; o = one[d][0][1]
    p15, p30, fb = PROF15[d], PROF30[d], FIB[d]
    lo_, hi_ = sorted((e, t['tgt']))
    near = lambda lv: min(abs(e - x) for x in lv) / a
    return dict(
        sell=int(s < 0), early=int(t['m'] < 600), gap_with=int(np.sign(o - yc) == s), prev_with=int(np.sign(yc - yo) == s),
        trend5_with=int(np.sign(yc - DAY[days[i - 6]][3]) == s), fib_trend_with=int((1 if fb['up'] else -1) == s),
        above_poc30=int(s * (e - p30['poc']) > 0), in_va30=int(p30['val'] <= e <= p30['vah']),
        hvn_block15=int(any(lo_ < x < hi_ for x in p15['hvn'])), hvn_block30=int(any(lo_ < x < hi_ for x in p30['hvn'])),
        near_hvn30=int(near(p30['hvn'] + [p30['poc']]) < 0.5), fib_block=int(any(lo_ < x < hi_ for x in fb['levels'])),
        near_fib=int(near(fb['levels']) < 0.5), high_vol=int(100 * a / e > st.median(100 * PA.ATR[(x, 10)] / five[x][10][4] for x in days[i - 20:i])))

def split(ts, label, w=None):
    """Trades, won, lost, net in H1 / H2 / all 2026."""
    out = []
    for nm, xs in (('Jan-Jun', [t for t in ts if t['d'] in H1]), ('Jul-Oct', [t for t in ts if t['d'] not in H1]), ('2026', ts)):
        p = [t['pnl'] for t in xs]
        out.append(f"{nm} {len(p):3} tr {sum(v > 0 for v in p):3}W/{sum(v <= 0 for v in p):<3}L {sum(p):+7,.0f}")
    return f"  {label:34} " + ' | '.join(out)

if __name__ == '__main__':
    strat = {'magnet': [t for d in D26 for t in magnet(d)], 'trail': [t for d in D26 for t in breakout(d, 'trail')],
             'scalp': [t for d in D26 for t in breakout(d, 'scalp')]}
    print(f"{B.name.upper()} 2026 ({D26[0]} to {D26[-1]}), points after costs")
    for nm, ts in strat.items():
        for t in ts: t.update(describe(t))
        print(f"\n== {nm} ==\n" + split(ts, 'as is'))
        print("  what the losers had in common (share of winners vs losers with each property):")
        keys = [k for k in ts[0] if k not in ('d', 'side', 'm', 'e', 'tgt', 'risk', 'pnl', 'mx', 'rev')]
        w = [t for t in ts if t['pnl'] > 0]; lo = [t for t in ts if t['pnl'] <= 0]
        for k in keys:
            print(f"    {k:15} winners {100*st.mean(t[k] for t in w) if w else 0:3.0f}%  losers {100*st.mean(t[k] for t in lo) if lo else 0:3.0f}%")
        print("  adjustments (keep only trades with / without the property):")
        for k in keys:
            for want in (1, 0):
                print(split([t for t in ts if t[k] == want], f"{'only' if want else 'skip'} {k}"))
    json.dump({k: [{kk: (float(vv) if isinstance(vv, (np.floating, float)) else vv) for kk, vv in t.items()} for t in v] for k, v in strat.items()},
              open(f'../.cache/y2026_{B.name}.json', 'w'))

def breakout_live(d, mode, poc_on=True, cut=600, days_kind='narrow'):
    """CPR Breakout exactly as tradingview/cpr_breakout.pine trades it with the 2026 adjustments: entries only
    before `cut` (minutes from midnight; 600 = 10:00) and only on the 30-day volume POC side (reversal included).
    days_kind: 'narrow' (narrow-CPR days only), 'other' (the rest) or 'any'."""
    lv = LV[d]; nar = lv['rank'] < 1 / 3
    if (days_kind == 'narrow' and not nar) or (days_kind == 'other' and nar): return []
    first = [x for x in one[d] if x[0] < 570]; orh, orl = max(x[2] for x in first), min(x[3] for x in first)
    f = W.FEAT[d]; poc = PROF30[d]['poc']; ex = ('half', 0.25) if mode == 'scalp' else ('trail', 0)
    pocok = lambda s, e: not poc_on or s * (e - poc) > 0
    for side, e, start, m in C.candidates(d, 'touch', orh, orl, 570):
        if m >= cut: break
        if side == -C.REL[d] or (mode == 'scalp' and f['gap'] != side) or not pocok(side, e): continue
        stp = orl if side > 0 else orh; R = side * (e - stp)
        if R <= 0: continue
        pnl, mx = W.trade(d, side, e, start, stp, ex)
        out = [dict(d=d, side=side, m=m, e=e, pnl=pnl, mx=mx)]
        if pnl <= 0:
            for s2, e2, st2, m2 in C.candidates(d, 'touch', orh, orl, mx + 1):
                if m2 >= cut: break
                if s2 != -side or not pocok(s2, e2): continue
                stp2 = orl if s2 > 0 else orh
                if s2 * (e2 - stp2) <= 0: break
                p2, mx2 = W.trade(d, s2, e2, st2, stp2, ex)
                out.append(dict(d=d, side=s2, m=m2, e=e2, pnl=p2, mx=mx2, rev=1)); break
        return out
    return []

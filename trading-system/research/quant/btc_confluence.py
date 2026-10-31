"""Bitcoin: levels + indicators together (asked on 31 October 2026: pivots, WaveTrend "TCI", CPR with RSI, volume
distribution levels, MACD - mixed, stops 150-300 points). BTCUSDT perpetual 1-minute candles (btc_scalp.py's data),
trades from July 2026; chosen on July-September, checked on October; costs 0.06% a trade; a candle reaching both the
stop and the target counts as the stop; out after 24 hours; one trade at a time per setup.

    python -I btc_confluence.py ../.cache/btc_raw

Levels for each UTC day: the floor pivots from the day before (P, R1, R2, S1, S2) and the CPR (TC / BC); the volume
profile of the 3 days before (real BTC volume, $50 bins): the POC, the value area edges (VAH / VAL) and the high-volume
lines (as the alert program draws them for Nifty).
Indicators on 5-minute candles: RSI 14; WaveTrend (LazyBear: esa = EMA(hlc3, 10), d = EMA(|hlc3 - esa|, 10), ci =
(hlc3 - esa) / (0.015 d), wt1 = EMA(ci, 21) - the "TCI" -, wt2 = SMA(wt1, 4)); MACD 12 / 26 / 9 on 15-minute candles.
Setups (at a 5-minute close):
  REV       a candle reaches a support level and closes back above it -> BUY (a resistance and back below -> SELL)
  + RSI     ... with RSI 14 at or below 35 (SELL: at or above 65)
  + WT      ... with WaveTrend's wt1 crossing up through wt2 below -40 within the last 3 candles (SELL: down, above 40)
  + MACD    ... with the 15-minute MACD histogram turning up (SELL: down)
  ALL       all three
  BREAK     a 5-minute close through a level with RSI >= 55, wt1 > wt2 and the MACD histogram > 0 -> BUY (mirror -> SELL)
"""
import collections, itertools, statistics as st, sys
sys.path.insert(0, '.')
sys.path.insert(0, '../../alerts')
import btc_scalp as B
import cprb_alerts as A

B5, B15 = B.B5, B.B15

def ema(v, n):
    out, k, e = [], 2 / (n + 1), None
    for x in v:
        e = x if e is None else e + k * (x - e)
        out.append(e)
    return out

def rsi(c, n=14):
    out, ag, al = [None] * len(c), 0.0, 0.0
    for i in range(1, len(c)):
        ch = c[i] - c[i - 1]
        g, l = max(ch, 0), max(-ch, 0)
        if i <= n:
            ag += g / n; al += l / n
        else:
            ag = (ag * (n - 1) + g) / n; al = (al * (n - 1) + l) / n
        if i >= n:
            out[i] = 100 if al == 0 else 100 - 100 / (1 + ag / al)
    return out

hlc3 = [(b[2] + b[3] + b[4]) / 3 for b in B5]
esa = ema(hlc3, 10)
dd = ema([abs(a - b) for a, b in zip(hlc3, esa)], 10)
ci = [(a - b) / (0.015 * d) if d else 0 for a, b, d in zip(hlc3, esa, dd)]
WT1 = ema(ci, 21)
WT2 = [st.mean(WT1[max(0, i - 3):i + 1]) for i in range(len(WT1))]
RSI = rsi([b[4] for b in B5])
c15 = [b[4] for b in B15]
macd = [a - b for a, b in zip(ema(c15, 12), ema(c15, 26))]
HIST15 = [m - s for m, s in zip(macd, ema(macd, 9))]
T15 = {b[0]: i for i, b in enumerate(B15)}

def hist_at(s):
    """The MACD histogram of the last 15-minute candle complete at minute s, and the one before."""
    i = T15.get((s - 15) // 15 * 15)
    return (HIST15[i], HIST15[i - 1]) if i and i > 0 else (None, None)

# ---------------- the day's levels ----------------
DAYK = collections.defaultdict(list)
for k in B.KS:
    DAYK[k // 1440].append(k)
DAYS = sorted(DAYK)
LEV = {}
for j in range(3, len(DAYS)):
    d, prev = DAYS[j], DAYK[DAYS[j - 1]]
    H, L, Cl = max(B.R[k][1] for k in prev), min(B.R[k][2] for k in prev), B.R[prev[-1]][3]
    P = (H + L + Cl) / 3
    bc = (H + L) / 2
    tc = 2 * P - bc
    lv = [(P, 'pivot P'), (2 * P - L, 'R1'), (P + H - L, 'R2'), (2 * P - H, 'S1'), (P - (H - L), 'S2'),
          (max(tc, bc), 'CPR'), (min(tc, bc), 'CPR')]
    hs = []
    for dd_ in DAYS[j - 3:j]:
        ks = DAYK[dd_]
        hs.append(A.day_hist([(k,) + B.R[k][:4] for k in ks], {k: B.R[k][4] for k in ks}, 50.0))
    base, p = A.combine(hs)
    poc, vah, val = A.poc_va(base, p, 50.0)
    lv += [(poc, 'POC'), (vah, 'VAH / VAL'), (val, 'VAH / VAL')] + [(x, 'volume line') for x in A.vol_lines(base, p, 50.0)]
    LEV[d] = lv

def signals(kind, need):
    """kind 'rev' / 'break'; need = the set of confirmations for 'rev' ('rsi', 'wt', 'macd')."""
    out = []
    for i in range(30, len(B5)):
        s, o, h, l, c, v, tb = B5[i]
        lv = LEV.get(s // 1440)
        if not lv or RSI[i] is None:
            continue
        pc = B5[i - 1][4]
        h0, h1 = hist_at(s + 5)
        for x, nm in lv:
            if kind == 'rev':
                side = 1 if (l <= x < c and pc > x) else -1 if (h >= x > c and pc < x) else 0
                if not side:
                    continue
                ok = True
                if 'rsi' in need:
                    ok &= RSI[i] <= 35 if side > 0 else RSI[i] >= 65
                if 'wt' in need:
                    ok &= any((WT1[j] > WT2[j] and WT1[j - 1] <= WT2[j - 1] and WT1[j] < -40) if side > 0 else
                              (WT1[j] < WT2[j] and WT1[j - 1] >= WT2[j - 1] and WT1[j] > 40) for j in range(i - 2, i + 1))
                if 'macd' in need:
                    ok &= h0 is not None and (h0 > h1 if side > 0 else h0 < h1)
            else:
                side = 1 if pc < x <= c else -1 if pc > x >= c else 0
                if not side:
                    continue
                ok = h0 is not None and (RSI[i] >= 55 and WT1[i] > WT2[i] and h0 > 0 if side > 0 else
                                         RSI[i] <= 45 and WT1[i] < WT2[i] and h0 < 0)
            if ok:
                out.append((s + 5, side, c, nm))
                break
    return out

def table(name, sig):
    print(f"\n  {name}: {len(sig)} signals")
    best = []
    for sl, tp in itertools.product((150, 200, 300), (150, 300, 450, 600)):
        rows = B.run(sig, tp, sl)
        sel = [x for x in rows if B.T(x[0]) < B.SEL_END]
        chk = [x for x in rows if B.T(x[0]) >= B.SEL_END]
        w = lambda r: round(100 * sum(x[1] == 'win' for x in r) / len(r)) if r else 0
        n = lambda r: sum(x[2] for x in r)
        print(f"    stop {sl} target {tp}: Jul-Sep {len(sel):4} tr {w(sel):3}% won {n(sel):+8,.0f} | Oct {len(chk):3} tr {w(chk):3}% won {n(chk):+7,.0f}"
              + ('   <- both +' if n(sel) > 0 and n(chk) > 0 else ''))

if __name__ == '__main__':
    print(f"BTCUSDT perpetual, trades {B.START:%Y-%m-%d} - {B.T(B.KS[-1]):%Y-%m-%d}; points = $ per BTC after costs; "
          f"won = the target before the stop")
    for name, kind, need in (('REV (a level, no confirmation)', 'rev', set()), ('REV + RSI', 'rev', {'rsi'}),
                             ('REV + WT (TCI)', 'rev', {'wt'}), ('REV + MACD', 'rev', {'macd'}),
                             ('REV + RSI + WT', 'rev', {'rsi', 'wt'}), ('REV + RSI + MACD', 'rev', {'rsi', 'macd'}),
                             ('ALL: REV + RSI + WT + MACD', 'rev', {'rsi', 'wt', 'macd'}), ('BREAK + RSI + WT + MACD', 'break', set())):
        table(name, signals(kind, need))
    # which levels did best for the all-confirmations reversal
    sig = signals('rev', {'rsi', 'wt'})
    print("\n  REV + RSI + WT by level, stop 200 target 300:")
    for nm in sorted({x[3] for x in sig}):
        rows = B.run([x for x in sig if x[3] == nm], 300, 200)
        p = [x[2] for x in rows]
        print(f"    {nm:12} {len(p):4} tr {round(100 * sum(x[1] == 'win' for x in rows) / len(rows)) if rows else 0:3}% won {sum(p):+8,.0f}")

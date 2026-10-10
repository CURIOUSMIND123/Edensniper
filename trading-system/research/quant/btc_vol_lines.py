"""Volume lines on Bitcoin: break a high-volume line, ride to the next one. Designed on 2023-2025, tested on 2026.

    python btc_vol_lines.py

Volume lines, rebuilt every day at 00:00 UTC from the last 3 / 7 / 15 days of hourly BTCUSDT futures candles
(each hour's volume spread over its high-low range, $40 bins): the point of control plus every high-volume peak
(local top of the smoothed profile in its top 30%), lines closer than 0.15% merged.
Entry: an hourly close through a line (the previous close was on the other side) -> trade that way at the next
open. Target: the next line in that direction. Stop: 0.5 or 1 ATR behind the broken line, or at the previous line.
Skip when the target is less than 1 / 1.5 / 2 times the stop distance away. Out after 48 hours at most.
Long-and-short or long-only. Costs 0.11% a trade plus Binance's funding every 8 hours.
Design rule (set before looking at 2026): versions that made money in each of 2023, 2024 and 2025; the best by
profit against worst fall goes forward. 2026 is shown for every version too.
"""
import collections, itertools, json
import numpy as np
import btc_trend as BT                       # hourly candles, funding, path rule, leverage helper

O, H, L, C, T, HOUR, FUND = BT.O, BT.H, BT.L, BT.C, BT.T, BT.HOUR, BT.FUND
VOL = np.array([BT.raw[k][4] for k in T]); N_ = len(T); COST = BT.COST
BIN = 40.0
DAYS = [k[:10] for k in T]
first_of = {}
for i, d in enumerate(DAYS): first_of.setdefault(d, i)
dlist = sorted(first_of)
tr = np.maximum(H - L, np.maximum(abs(H - np.roll(C, 1)), abs(L - np.roll(C, 1)))); ATR = BT.ema(tr, 14)

def day_hist(d):
    i0 = first_of[d]; i1 = first_of.get(dlist[dlist.index(d) + 1], N_) if d != dlist[-1] else N_
    lo = L[i0:i1].min(); base = int(lo // BIN); h = np.zeros(int(H[i0:i1].max() // BIN) - base + 2)
    for i in range(i0, i1):
        a, b = int(L[i] // BIN) - base, int(H[i] // BIN) - base; h[a:b + 1] += VOL[i] / (b - a + 1)
    return base, h
HIST = {d: day_hist(d) for d in dlist}

def lines(d, n):
    k = dlist.index(d); ds = dlist[max(0, k - n):k]
    if len(ds) < n: return []
    base = min(HIST[x][0] for x in ds); top = max(HIST[x][0] + len(HIST[x][1]) for x in ds)
    p = np.zeros(top - base)
    for x in ds: b0, h = HIST[x]; p[b0 - base:b0 - base + len(h)] += h
    sm = np.convolve(p, np.ones(3) / 3, 'same'); thr = np.percentile(sm[sm > 0], 70)
    peaks = [i for i in range(1, len(sm) - 1) if sm[i] >= thr and sm[i] >= sm[i - 1] and sm[i] >= sm[i + 1]]
    peaks.append(int(np.argmax(p)))
    prices = sorted((base + i + 0.5) * BIN for i in set(peaks))
    merged = []
    for x in prices:
        if merged and x - merged[-1] <= 0.0015 * x: merged[-1] = (merged[-1] + x) / 2
        else: merged.append(x)
    return merged
LINES = {(d, n): lines(d, n) for d in dlist for n in (3, 7, 15)}

def run(n, stop_kind, rr, direction, y0='2023-01-01', y1='2026-12-31'):
    trades = []; pos = None
    for i in range(1, N_ - 1):
        d = DAYS[i]
        if pos:
            side, e, stp, tgt, ei, fund, mae = pos
            if HOUR[i] % 8 == 0 and i > ei: fund += side * FUND.get(T[i], 0.0001)
            out = None
            for px in BT.path(O[i], H[i], L[i], C[i]):
                mae = max(mae, side * (e - px) / e)
                if side * (px - stp) <= 0: out = stp if side * (O[i] - stp) > 0 else O[i]; break
                if side * (px - tgt) >= 0: out = tgt if side * (tgt - O[i]) > 0 else O[i]; break
            if out is None and i - ei >= 48: out = C[i]
            if out is not None:
                trades.append((T[ei], side, e, out, side * (out - e) / e - COST - fund, mae, abs(e - pos0) / e)); pos = None
            else:
                pos = (side, e, stp, tgt, ei, fund, mae); continue
        if not (y0 <= d <= y1): continue
        lv = LINES.get((d, n)) or []
        if not lv: continue
        for x in lv:
            side = 1 if C[i - 1] < x <= C[i] else -1 if C[i - 1] > x >= C[i] else 0
            if not side or (side < 0 and direction == 'long'): continue
            e = O[i + 1]
            nxt = [y for y in lv if side * (y - x) > 0]
            if not nxt: break
            tgt = min(nxt, key=lambda y: abs(y - x))
            if stop_kind == 'prev':
                prv = [y for y in lv if side * (x - y) > 0]
                if not prv: break
                stp = max(prv) if side > 0 else min(prv)
            else:
                stp = x - side * (0.5 if stop_kind == 'atr0.5' else 1.0) * ATR[i]
            risk, reward = side * (e - stp), side * (tgt - e)
            if risk <= 0 or reward < rr * risk: break
            pos = (side, e, stp, tgt, i + 1, 0.0, 0.0); pos0 = stp
            break
    return trades

def stats(ts, a, b):
    p = [t[4] for t in ts if a <= t[0][:10] <= b]
    if not p: return dict(n=0, tot=0, win=0, dd=0)
    eq = pk = dd = 0.0
    for v in p: eq += v; pk = max(pk, eq); dd = min(dd, eq - pk)
    return dict(n=len(p), tot=sum(p), win=sum(v > 0 for v in p) / len(p), dd=dd)

if __name__ == '__main__':
    fmt = lambda s: f"{s['n']:4} tr {100*s['win']:3.0f}% won {100*s['tot']:+7.1f}% (worst fall {100*s['dd']:6.1f}%)"
    res = {}; cands = []
    for n, sk, rr, dr in itertools.product((3, 7, 15), ('atr0.5', 'atr1', 'prev'), (1.0, 1.5, 2.0), ('both', 'long')):
        ts = run(n, sk, rr, dr); res[(n, sk, rr, dr)] = ts
        ys = [stats(ts, f'{y}-01-01', f'{y}-12-31') for y in (2023, 2024, 2025)]
        dsg = stats(ts, '2023-01-01', '2025-12-31'); s26 = stats(ts, '2026-01-01', '2026-12-31')
        ok = all(y['tot'] > 0 for y in ys)
        print(f"  {n:2}-day lines, stop {sk:6}, target >= {rr}x stop, {dr:4}: 2023-25 {fmt(dsg)} {'every year +' if ok else '            '} | 2026 {fmt(s26)}")
        if ok: cands.append((dsg['tot'] / max(1e-9, -dsg['dd']), (n, sk, rr, dr)))
    s26s = [stats(ts, '2026-01-01', '2026-12-31')['tot'] for ts in res.values()]
    print(f"\n{len(res)} versions: {len(cands)} made money in each of 2023-2025; {sum(v > 0 for v in s26s)} made money in 2026. "
          f"Average 2026 per version {100 * sum(s26s) / len(s26s):+.1f}%")
    if cands:
        _, best = max(cands); ts = [t for t in res[best] if t[0] >= '2026-01-01']
        print(f"Picked on 2023-2025: {best}; 2026: {fmt(stats(ts, '2026-01-01', '2026-12-31'))}")
        for lev in (1, 2, 3, 5, 10, 20, 150):
            eq, bust, low = BT.grow(ts, lev=lev)
            print(f"   {lev:3}x: Rs 30,000 -> Rs {eq:,.0f}" + (' (wiped out)' if bust else ''))
    else:
        print("No version made money in each of 2023, 2024 and 2025, so nothing goes forward to 2026.")

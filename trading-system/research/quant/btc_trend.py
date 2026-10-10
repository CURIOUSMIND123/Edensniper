"""A Bitcoin strategy built for Bitcoin: designed on 2023-2025, then tested on 2026 (which the design never saw).

    python btc_trend.py

Binance BTCUSDT futures, hourly candles (UTC), Jan 2023 - 9 Oct 2026. Four families, 60 versions in all:
  donchian  buy a close above the highest high of the last N candles (sell below the lowest low); exit on the
            opposite N/2 channel, or a 2x / 3x ATR trailing stop. 1-hour or 4-hour candles, N = 20 or 55.
  ema       hold in the direction of EMA fast vs EMA slow (20/50 or 50/200), 1-hour or 4-hour candles; with or
            without a 3x ATR trailing stop.
  volbo     daily volatility breakout: buy when price rises k x yesterday's range above today's 00:00 UTC open
            (sell when it falls k x below), k = 0.3 / 0.5 / 0.7; stop at the open; out at the day's end or held
            until the next day's opposite signal.
  dip       buy dips in an uptrend: 1-hour close above its EMA 200 and RSI(2) under 10 (or 5); out when the close
            is back above EMA 5 or after 24 hours; stop 3x ATR (mirror for shorts in a downtrend if "both").
Each family runs long-and-short or long-only. Signals at a candle's close, entry at the next candle's open, stops
checked hour by hour (open -> nearer extreme -> farther extreme -> close). Costs: 0.05% taker fee each side + 0.01%
slippage = 0.11% of the position per trade, plus Binance's actual funding every 8 hours while a trade is open.
Design rule (decided before looking at 2026): keep versions that made money in each of 2023, 2024 and 2025, and
take the one with the best profit-to-worst-fall ratio from each family. Then report 2026 for those, and for all.
"""
import collections, itertools, json, statistics as st
import numpy as np

COST = 0.0011
raw = json.load(open('../.cache/btc_1h.json'))
FUND = json.load(open('../.cache/btc_funding.json'))
T = sorted(raw)
O = np.array([raw[k][0] for k in T]); H = np.array([raw[k][1] for k in T]); L = np.array([raw[k][2] for k in T])
C = np.array([raw[k][3] for k in T]); N_ = len(T)
HOUR = np.array([int(k[11:13]) for k in T]); DAYS = [k[:10] for k in T]

def ema(x, n):
    out = np.empty_like(x); a = 2 / (n + 1); out[0] = x[0]
    for i in range(1, len(x)): out[i] = out[i - 1] + a * (x[i] - out[i - 1])
    return out

def tf_view(step):
    """Candles of `step` hours (aligned to 00:00 UTC): for each hour, is it the last hour of a candle, and the
    candle-level highs / lows / closes / ATR up to that candle."""
    last = (HOUR % step) == step - 1
    idx = np.where(last)[0]; starts = idx - (step - 1)
    hh = np.array([H[s:e + 1].max() for s, e in zip(starts, idx)]); ll = np.array([L[s:e + 1].min() for s, e in zip(starts, idx)])
    cc = C[idx]; pc = np.concatenate([[cc[0]], cc[:-1]])
    tr = np.maximum(hh - ll, np.maximum(abs(hh - pc), abs(ll - pc))); atr = ema(tr, 14)
    return idx, hh, ll, cc, atr

VIEWS = {s: tf_view(s) for s in (1, 4)}

def path(o, h, l, c): return (o, h, l, c) if abs(h - o) < abs(o - l) else (o, l, h, c)

def simulate(signal_at, exit_at, stop_rule):
    """signal_at(i) -> +1 / -1 / 0 at the close of hour i (entry next open); exit_at(i, side, entry_i) -> bool;
    stop_rule(i, side, entry, stop) -> new stop (trailing) or the initial stop when stop is None.
    Returns trades: (entry time, side, entry, exit, pnl after costs and funding as a fraction, MAE fraction, stop distance)."""
    trades = []; pos = None
    for i in range(N_ - 1):
        if pos:
            side, e, stp, ei, fund, mae = pos
            if HOUR[i] % 8 == 0 and i > ei:                      # funding at 00 / 08 / 16 UTC while the trade is open
                fund += side * FUND.get(T[i], 0.0001)
            out = None
            for px in path(O[i], H[i], L[i], C[i]):
                mae = max(mae, side * (e - px) / e)
                if side * (px - stp) <= 0: out = stp if side * (O[i] - stp) > 0 else O[i]; break
            if out is None and exit_at(i, side, ei): out = C[i]
            if out is not None:
                trades.append((T[ei], side, e, out, side * (out - e) / e - COST - fund, mae, pos_stop0[0]))
                pos = None
            else:
                pos = (side, e, stop_rule(i, side, e, stp), ei, fund, mae)
                continue
        if pos is None:
            s = signal_at(i)
            if s:
                e = O[i + 1]; stp = stop_rule(i, s, e, None)
                pos_stop0 = [abs(e - stp) / e]
                pos = (s, e, stp, i + 1, 0.0, 0.0)
    return trades

# ---------------- the four families ----------------
def donchian(step, n, exit_kind, direction):
    idx, hh, ll, cc, atr = VIEWS[step]; at = {h: j for j, h in enumerate(idx)}
    def sig(i):
        j = at.get(i)
        if j is None or j < n: return 0
        if cc[j] > hh[j - n:j].max(): return 1
        if cc[j] < ll[j - n:j].min() and direction == 'both': return -1
        return 0
    def ex(i, side, ei):
        j = at.get(i)
        if exit_kind != 'channel' or j is None or j < n // 2: return False
        return cc[j] < ll[j - n // 2:j].min() if side > 0 else cc[j] > hh[j - n // 2:j].max()
    def stop(i, side, e, cur):
        j = at.get(i, None)
        k = 3.0 if exit_kind in ('channel', 'atr3') else 2.0
        if cur is None:
            jj = max(x for x in (at.get(i), max((v for h, v in at.items() if h <= i), default=0)) if x is not None)
            return e - side * k * atr[jj]
        if j is None or exit_kind == 'channel': return cur
        ns = cc[j] - side * k * atr[j]
        return ns if side * (ns - cur) > 0 else cur
    return sig, ex, stop

def ema_cross(step, fast, slow, trail, direction):
    idx, hh, ll, cc, atr = VIEWS[step]; at = {h: j for j, h in enumerate(idx)}
    ef, es = ema(cc, fast), ema(cc, slow)
    def sig(i):
        j = at.get(i)
        if j is None or j < slow: return 0
        if ef[j] > es[j]: return 1
        if ef[j] < es[j] and direction == 'both': return -1
        return 0
    def ex(i, side, ei):
        j = at.get(i)
        return j is not None and side * (ef[j] - es[j]) <= 0
    def stop(i, side, e, cur):
        j = at.get(i)
        if cur is None:
            jj = max(v for h, v in at.items() if h <= i)
            return e - side * (3 if trail else 20) * atr[jj]       # no trail: only a far emergency stop
        if j is None or not trail: return cur
        ns = cc[j] - side * 3 * atr[j]
        return ns if side * (ns - cur) > 0 else cur
    return sig, ex, stop

DAYOPEN = {}; DAYRNG = {}
by = collections.defaultdict(list)
for i, d in enumerate(DAYS): by[d].append(i)
dl = sorted(by)
for a, b in zip(dl, dl[1:]):
    DAYOPEN[b] = O[by[b][0]]; DAYRNG[b] = H[by[a]].max() - L[by[a]].min()

def volbo(k, hold, direction):
    state = {}
    def sig(i):
        d = DAYS[i]
        if d not in DAYOPEN or HOUR[i] == 23 or state.get(d): return 0
        up, dn = DAYOPEN[d] + k * DAYRNG[d], DAYOPEN[d] - k * DAYRNG[d]
        if C[i] > up: state[d] = 1; return 1
        if C[i] < dn and direction == 'both': state[d] = 1; return -1
        return 0
    def ex(i, side, ei):
        if hold == 'day': return HOUR[i] == 23
        d = DAYS[i]                                           # 'next': out when the opposite signal fires
        if d not in DAYOPEN: return False
        return (C[i] < DAYOPEN[d] - k * DAYRNG[d]) if side > 0 else (C[i] > DAYOPEN[d] + k * DAYRNG[d])
    def stop(i, side, e, cur):
        if cur is None: return DAYOPEN[DAYS[i]] if hold == 'day' else e - side * 1.0 * DAYRNG[DAYS[i]]
        return cur
    return sig, ex, stop

def dip(thr, out_kind, direction):
    e200, e5 = ema(C, 200), ema(C, 5)
    d = np.diff(C, prepend=C[0]); up = np.where(d > 0, d, 0); dn = np.where(d < 0, -d, 0)
    au, ad = ema(up, 3), ema(dn, 3); rsi = 100 - 100 / (1 + au / np.maximum(ad, 1e-9))
    tr = np.maximum(H - L, np.maximum(abs(H - np.roll(C, 1)), abs(L - np.roll(C, 1)))); atr = ema(tr, 14)
    def sig(i):
        if i < 200: return 0
        if C[i] > e200[i] and rsi[i] < thr: return 1
        if direction == 'both' and C[i] < e200[i] and rsi[i] > 100 - thr: return -1
        return 0
    def ex(i, side, ei):
        if out_kind == 'ema5': return side * (C[i] - e5[i]) > 0 and i > ei
        return i - ei >= 24
    def stop(i, side, e, cur): return e - side * 3 * atr[i] if cur is None else cur
    return sig, ex, stop

FAMILIES = {
    'donchian': [((s, n, x, dr), donchian) for s, n, x, dr in itertools.product((1, 4), (20, 55), ('channel', 'atr2', 'atr3'), ('both', 'long'))],
    'ema': [((s, f, sl, tr, dr), ema_cross) for s, (f, sl), tr, dr in itertools.product((1, 4), ((20, 50), (50, 200)), (True, False), ('both', 'long'))],
    'volbo': [((k, h, dr), volbo) for k, h, dr in itertools.product((0.3, 0.5, 0.7), ('day', 'next'), ('both', 'long'))],
    'dip': [((t, x, dr), dip) for t, x, dr in itertools.product((10, 5), ('ema5', '24h'), ('long', 'both'))],
}

def stats(ts, y0, y1):
    p = [t[4] for t in ts if y0 <= t[0][:10] <= y1]
    if not p: return dict(n=0, tot=0, win=0, dd=0)
    eq = pk = dd = 0.0
    for v in p: eq += v; pk = max(pk, eq); dd = min(dd, eq - pk)
    return dict(n=len(p), tot=sum(p), win=sum(v > 0 for v in p) / len(p), dd=dd)

def grow(ts, lev=None, risk=None, cap=20):
    eq = 30000.0; low = eq
    for t in ts:
        Lv = lev if lev else min(cap, risk / max(t[6], 1e-4))
        if t[5] >= 1 / Lv - 0.004: return 0.0, t[0][:10], low
        eq *= 1 + Lv * t[4]; low = min(low, eq)
        if eq < 100: return eq, t[0][:10], low
    return eq, None, low

if __name__ == '__main__':
    results = {}
    for fam, items in FAMILIES.items():
        for args, fn in items:
            ts = simulate(*fn(*args))
            results[(fam, args)] = ts
    fmt = lambda s: f"{s['n']:4} tr {100*s['win']:3.0f}% won {100*s['tot']:+7.1f}% (worst fall {100*s['dd']:6.1f}%)"
    print("DESIGN YEARS 2023-2025, then 2026 (unseen). Totals are % of price per 1x position, after fees and funding.")
    picks = {}
    for fam in FAMILIES:
        print(f"\n== {fam} ==")
        cands = []
        for (f, args), ts in results.items():
            if f != fam: continue
            ys = [stats(ts, f'{y}-01-01', f'{y}-12-31') for y in (2023, 2024, 2025)]
            dsg = stats(ts, '2023-01-01', '2025-12-31'); s26 = stats(ts, '2026-01-01', '2026-12-31')
            ok = all(y['tot'] > 0 for y in ys)
            print(f"  {str(args):32} 2023-25 {fmt(dsg)} {'every year +' if ok else '            '} | 2026 {fmt(s26)}")
            if ok: cands.append((dsg['tot'] / max(1e-9, -dsg['dd']), args, s26))
        if cands:
            _, a, s26 = max(cands); picks[fam] = a
            print(f"  -> picked on 2023-2025: {a}; 2026: {fmt(s26)}")
        else:
            print("  -> no version made money in each of 2023, 2024 and 2025")
    allv = [stats(ts, '2026-01-01', '2026-12-31')['tot'] for ts in results.values()]
    print(f"\nAll {len(allv)} versions in 2026: {sum(v > 0 for v in allv)} made money. Bitcoin itself 2026: "
          f"{100 * (C[-1] / O[T.index('2026-01-01 00:00')] - 1):+.1f}%")
    json.dump({f"{f}|{a}": [list(map(str, t[:1])) + [float(x) for x in t[1:]] for t in ts] for (f, a), ts in results.items()},
              open('../.cache/btc_trend_trades.json', 'w'))
    print("\nRs 30,000 in 2026, picked versions (compounding; liquidation checked against the worst move inside each trade):")
    for fam, a in picks.items():
        ts = [t for t in results[(fam, a)] if t[0] >= '2026-01-01']
        line = []
        for lev in (1, 2, 3, 5, 10, 20, 50, 150):
            eq, bust, low = grow(ts, lev=lev)
            line.append(f"{lev}x Rs {eq:,.0f}" + (' (wiped out)' if bust else ''))
        for r in (0.01, 0.02):
            eq, bust, low = grow(ts, risk=r)
            line.append(f"risk {int(r*100)}%/trade Rs {eq:,.0f}" + (' (wiped out)' if bust else '') + f" (low Rs {low:,.0f})")
        print(f"  {fam} {a}:\n     " + ' | '.join(line))

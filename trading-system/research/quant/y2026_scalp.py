"""2026 only: pure scalping, several trades a day, with tight ("sniper") entries, small stops and quick exits.

    python y2026_scalp.py grid nifty     (and: grid sensex) every version on index points, costs included
    python y2026_scalp.py pick           the versions that made money in both halves of 2026 on both indices
    python y2026_scalp.py price nifty    (and: price sensex) the picked versions' trades as options (Rs 30,000)
    python y2026_scalp.py                the report in rupees: one account for both indices

The entry is a stop order at the signal candle's high (BUY) or low (SELL), valid for the next 3 one-minute candles:
the trade starts only if price keeps going the signal's way. Stop just beyond the signal candle (0.01% of price);
skipped when that is wider than the stop limit. Target R x the stop. Out after the time limit, or at 3:15.
Signals 9:30-2:45, one trade at a time, at most N a day.

Setups (1-minute candles; volume = NIFTYBEES, the Nifty ETF, for both indices):
  vwap      trend pullback to VWAP: the last T closes all on one side of VWAP and VWAP moving that way over 15
            minutes; the candle dips to VWAP (within a tolerance) and closes back on the trend side
  ema       trend pullback to the EMA 9: EMA 9 above EMA 21 (below for SELL) for the last T candles and EMA 21
            rising; the candle dips to the EMA 9 and closes beyond the EMA 21
  retest    break and retest of a key level: 3 closes beyond the level, then within 30 minutes a candle comes back
            to it and closes beyond it (levels: CPR top / pivot / bottom, yesterday's high / low, the 15-minute
            high / low; 'all' adds the 3-day volume lines)
  burst     momentum: a candle whose body is 2 / 3x the average range of the last 20 candles (with NIFTYBEES volume
            2x its average, or any volume); entry at the next candle's open, stop at the candle's other end
Filters: 'plan' = only in the direction of the opening gap and not against today's CPR vs yesterday's (the daily
plan's direction); 'signal' = only after the indicator's own trade of the day (default settings), in its direction; the volume check (the last 2 hours' up-candle volume beats the down-candle volume for a BUY);
stop for the day after 2 losing trades.
Costs: 4 Nifty / 12 Sensex index points a trade (round trip) on index points; as options, y2026_options.py's model
(the day's implied volatility, time decay, slippage 1 / 2 premium points, 0.13% charges, Rs 20 an order), at the
money, nearest expiry, as many lots as Rs 30,000 buys.
"""
import collections, itertools, json, math, sys

FAMS = {
    'vwap':   [dict(tol=t, T=T) for t in (0.0002, 0.0005) for T in (10, 30)],
    'ema':    [dict(tol=t, T=T) for t in (0.0002, 0.0005) for T in (10, 30)],
    'retest': [dict(tol=t, lv=lv) for t in (0.0002, 0.0005) for lv in ('core', 'all')],
    'burst':  [dict(k=k, vm=vm) for k in (2.0, 3.0) for vm in (0.0, 2.0)],
}
CAPS = (0.0010, 0.0015)                  # the widest stop allowed, share of price (Nifty ~25 / 37, Sensex ~80 / 120)
RS_ = (1.0, 1.5, 2.0, 3.0)               # target = R x the stop
TIMES = (10, 20, 45)                     # out after this many minutes at the latest
BIAS = ('none', 'plan', 'signal')
VCHK = (False, True)
MAXN = (3, 8)
LOSS2 = (False, True)
START, LAST, OUT = 570, 885, 915
START30 = '2026-09-10'

def key(fam, sp, cap, R, tm, bias, vc, mx, l2):
    return f"{fam}|{json.dumps(sp, sort_keys=True)}|{cap}|{R}|{tm}|{bias}|{int(vc)}|{mx}|{int(l2)}"

def path(o, h, l, c):
    return (o, l, h, c) if c >= o else (o, h, l, c)

# ---------------- per day: candles, VWAP, EMAs, signals ----------------
def day_data(Y, A, cx, d, vol):
    c1 = [x for x in Y.one[d] if 555 <= x[0] <= 929]
    m = [x[0] for x in c1]; o = [x[1] for x in c1]; h = [x[2] for x in c1]; l = [x[3] for x in c1]; c = [x[4] for x in c1]
    v = [vol.get(d, {}).get(x, 0.0) for x in m]
    vw, pv, sv = [], 0.0, 0.0
    for i in range(len(c1)):
        tp = (h[i] + l[i] + c[i]) / 3; w = v[i] if v[i] > 0 else 1e-9
        pv += tp * w; sv += w; vw.append(pv / sv)
    def ema(n):
        a, out, e = 2 / (n + 1), [], c[0]
        for x in c: e = e + a * (x - e); out.append(e)
        return out
    gap = (1 if c1[0][1] > cx['yc'] else -1 if c1[0][1] < cx['yc'] else 0) if c1 else 0
    first = [x for x in c1 if x[0] < 570]
    lv = cx['lv']
    core = [lv['top'], lv['p'], lv['bot'], cx['yh'], cx['yl']]
    orh, orl = (max(x[2] for x in first), min(x[3] for x in first)) if first else (None, None)
    return dict(d=d, m=m, o=o, h=h, l=l, c=c, v=v, vw=vw, e9=ema(9), e21=ema(21), gap=gap, rel=cx['rel'],
                core=core, orr=(orh, orl), lines=list(cx['lines']), vf=A.volume_fn(cx, Y.one[d], 929))

def signals(D, fam, sp):
    """(i, side, trigger, stop, market): the signal candle i; enter beyond trigger in the next 3 candles (or at the
    next candle's open when market)."""
    m, o, h, l, c, v, vw = D['m'], D['o'], D['h'], D['l'], D['c'], D['v'], D['vw']
    n, out = len(m), []
    for i in range(20, n - 1):
        if not (START <= m[i] <= LAST): continue
        px = c[i]; buf = 0.0001 * px
        if fam == 'vwap':
            T = sp['T']
            if i < T + 15: continue
            for s in (1, -1):
                if all(s * (c[j] - vw[j]) > 0 for j in range(i - T, i)) and s * (vw[i] - vw[i - 15]) > 0 \
                        and s * (c[i] - vw[i]) > 0 and (l[i] <= vw[i] * (1 + sp['tol']) if s > 0 else h[i] >= vw[i] * (1 - sp['tol'])):
                    out.append((i, s, h[i] if s > 0 else l[i], l[i] - buf if s > 0 else h[i] + buf, False))
        elif fam == 'ema':
            T = sp['T']; e9, e21 = D['e9'], D['e21']
            if i < T + 5: continue
            for s in (1, -1):
                if all(s * (e9[j] - e21[j]) > 0 for j in range(i - T, i)) and s * (e21[i] - e21[i - 5]) > 0 \
                        and s * (c[i] - e21[i]) > 0 and (l[i] <= e9[i] * (1 + sp['tol']) if s > 0 else h[i] >= e9[i] * (1 - sp['tol'])):
                    out.append((i, s, h[i] if s > 0 else l[i], l[i] - buf if s > 0 else h[i] + buf, False))
        elif fam == 'burst':
            rng = sum(h[j] - l[j] for j in range(i - 20, i)) / 20
            avv = sum(v[j] for j in range(i - 20, i)) / 20
            body = c[i] - o[i]
            if rng > 0 and abs(body) >= sp['k'] * rng and (sp['vm'] == 0 or (avv > 0 and v[i] >= sp['vm'] * avv)):
                s = 1 if body > 0 else -1
                out.append((i, s, None, l[i] - buf if s > 0 else h[i] + buf, True))
    if fam == 'retest':
        lvls = list(D['core']) + (D['lines'] if sp['lv'] == 'all' else [])
        orh, orl = D['orr']
        for L in lvls + ([orh, orl] if orh else []):
            if L is None: continue
            for s in (1, -1):
                broke = None
                for i in range(3, n - 1):
                    if L in (orh, orl) and m[i] < 570: continue
                    if broke is None:
                        if all(s * (c[j] - L) > 0 for j in (i - 2, i - 1, i)) and s * (c[i - 3] - L) <= 0: broke = i
                        continue
                    if i - broke > 30: break
                    if not (START <= m[i] <= LAST): continue
                    if (l[i] <= L * (1 + sp['tol']) if s > 0 else h[i] >= L * (1 - sp['tol'])) and s * (c[i] - L) > 0:
                        buf = 0.0001 * c[i]
                        out.append((i, s, h[i] if s > 0 else l[i], min(l[i], L) - buf if s > 0 else max(h[i], L) + buf, False))
                        break
        out.sort()
    return out

def outcome(D, sig, cap, R, tm, cost):
    """Walk the trade on the 1-minute path. -> (entry minute, exit minute, points after cost, entry px, exit px) or None."""
    i, s, trig, stp, market = sig
    m, o, h, l, c = D['m'], D['o'], D['h'], D['l'], D['c']
    n = len(m)
    if market:
        j0, e = i + 1, o[i + 1]
        if s * (e - stp) <= 0: return None
        risk = s * (e - stp)
    else:
        risk = s * (trig - stp)
    if risk <= 0 or risk > cap * c[i]: return None
    ent, e = None, None
    j = i + 1
    while j < n and m[j] < OUT:
        pts = path(o[j], h[j], l[j], c[j])
        k0 = 0
        if ent is None:
            if market:
                ent, e = j, o[j]; tgt = e + s * R * risk; stop = e - s * risk
            else:
                if j > i + 3: return None
                hit = None
                for k, p in enumerate(pts):
                    if s * (p - trig) >= 0: hit = k; break
                if hit is None: j += 1; continue
                ent, e = j, (pts[hit] if hit == 0 else trig); k0 = hit
                stop = e - s * risk; tgt = e + s * R * risk
        for k in range(k0, 4):
            p = pts[k]
            if s * (p - stop) <= 0:
                x = p if k == 0 and j > ent else stop
                return m[ent], m[j], s * (x - e) - cost, e, x
            if s * (p - tgt) >= 0:
                x = p if k == 0 and j > ent else tgt
                return m[ent], m[j], s * (x - e) - cost, e, x
        if m[j] - m[ent] >= tm - 1 or m[j + 1 if j + 1 < n else j] >= OUT:
            return m[ent], m[j], s * (c[j] - e) - cost, e, c[j]
        j += 1
    if ent is None: return None
    return m[ent], m[n - 1], s * (c[n - 1] - e) - cost, e, c[n - 1]

def run_version(days_sig, fam, sp, cap, R, tm, bias, vc, mx, l2):
    """days_sig: {d: (D-lite, [(sig, {(cap,R,tm): outcome})])} -> list of trades."""
    out = []
    for d, (D, sigs) in days_sig.items():
        free, n, losses = 0, 0, 0
        for sig, oc in sigs:
            r = oc.get((cap, R, tm))
            if r is None: continue
            i, s = sig[0], sig[1]
            if r[0] < free or n >= mx or (l2 and losses >= 2): continue
            if bias == 'plan' and (s != D['gap'] or s == -D['rel']): continue
            if bias == 'signal':
                last = [x for x in D['sig'] if x[0] <= r[0]]
                if not last or last[-1][1] != s: continue
            if vc and not D['vf'](s, r[0], 'SCALP'): continue
            out.append((d, s, r)); free = r[1] + 1; n += 1; losses += r[2] <= 0
    return out

def stats(ts, H1):
    p = [t[2][2] for t in ts]; a = sum(t[2][2] for t in ts if t[0] in H1)
    eq = pk = dd = 0
    for x in p: eq += x; pk = max(pk, eq); dd = min(dd, eq - pk)
    return dict(n=len(p), w=sum(x > 0 for x in p), net=sum(p), a=a, b=sum(p) - a, dd=dd,
                days=len({t[0] for t in ts}), l30=sum(t[2][2] for t in ts if t[0] >= START30))

def load(nm):
    SIG = collections.defaultdict(list)                  # the indicator's own trades (y2026_capital.py dump)
    for t in json.load(open(f'../.cache/default_trades_{nm}.json')): SIG[t['d']].append((t['m'], t['side']))
    sys.argv = [sys.argv[0], nm]
    import y2026 as Y
    sys.path.insert(0, '../../alerts')
    import cprb_alerts as A
    spec = A.SPEC[nm]; sess = {d: Y.one[d] for d in Y.days}
    vol = collections.defaultdict(dict)
    for k, v in Y.bees.items(): vol[k[:10]][int(k[11:13]) * 60 + int(k[14:16])] = v[4]
    daily = {d: Y.DAY[d] for d in Y.days}
    DD = {}
    for d in Y.D26:
        cx = A.context(spec, sess, vol, d, daily); cx['tvol'] = vol.get(d, {})
        DD[d] = day_data(Y, A, cx, d, vol); DD[d]['sig'] = sorted(SIG.get(d, []))
    return Y, A, DD

def all_outcomes(DD, fam, sp, cost):
    res = {}
    for d, D in DD.items():
        sigs = []
        for sig in signals(D, fam, sp):
            sigs.append((sig, {(cap, R, tm): outcome(D, sig, cap, R, tm, cost) for cap in CAPS for R in RS_ for tm in TIMES}))
        sigs.sort(key=lambda x: (min((r[0] for r in x[1].values() if r), default=10 ** 6), x[0][0]))
        res[d] = (D, sigs)
    return res

def grid(nm):
    Y, A, DD = load(nm)
    out = {}
    for fam, sps in FAMS.items():
        for sp in sps:
            res = all_outcomes(DD, fam, sp, Y.COST)
            for cap, R, tm, bias, vc, mx, l2 in itertools.product(CAPS, RS_, TIMES, BIAS, VCHK, MAXN, LOSS2):
                ts = run_version(res, fam, sp, cap, R, tm, bias, vc, mx, l2)
                out[key(fam, sp, cap, R, tm, bias, vc, mx, l2)] = stats(ts, Y.H1)
            print(nm, fam, sp, 'done', flush=True)
    json.dump(out, open(f'../.cache/scalp_grid_{nm}.json', 'w'))

PT = {'nifty': 32.5, 'sensex': 10.0}      # rupees per index point per lot (an at-the-money option moves about half)

def pick():
    G = {nm: json.load(open(f'../.cache/scalp_grid_{nm}.json')) for nm in ('nifty', 'sensex')}
    keys = list(G['nifty'])
    print(f"{len(keys)} versions per index (index points after costs, 2026)")
    for nm in G:
        nets = sorted(r['net'] for r in G[nm].values())
        pos = sum(x > 0 for x in nets); both = sum(r['a'] > 0 and r['b'] > 0 for r in G[nm].values())
        print(f"  {nm}: made money {pos} of {len(nets)}, in both halves {both}; middle version {nets[len(nets) // 2]:+,.0f}, best {nets[-1]:+,.0f}")
    fams = collections.Counter(k.split('|')[0] for k in keys)
    for f in fams:
        for nm in G:
            ks = [k for k in keys if k.startswith(f + '|')]
            nets = sorted(G[nm][k]['net'] for k in ks)
            print(f"    {f:7} {nm:6}: {sum(x > 0 for x in nets):4} of {len(nets)} made money, middle {nets[len(nets) // 2]:+8,.0f}, best {nets[-1]:+8,.0f}")
    good = [k for k in keys if all(G[nm][k]['a'] > 0 and G[nm][k]['b'] > 0 and G[nm][k]['n'] >= 150 for nm in G)]
    print(f"\nboth halves on both indices, at least 150 trades on each (about 4 a week): {len(good)}")
    sc = lambda k: sum(G[nm][k]['net'] * PT[nm] for nm in G)
    for k in sorted(good, key=sc, reverse=True)[:25]:
        print(f"  Rs/lot {sc(k):+9,.0f}  {k}")
        for nm in G:
            r = G[nm][k]
            print(f"      {nm:6} {r['n']:4} trades on {r['days']:3} days, {100 * r['w'] / r['n']:3.0f}% won, net {r['net']:+7,.0f} (Jan-Jun {r['a']:+6,.0f}, "
                  f"Jul-Oct {r['b']:+6,.0f}), worst fall {r['dd']:7,.0f}, last 30 days {r['l30']:+6,.0f}")
    json.dump(sorted(good, key=sc, reverse=True)[:25], open('../.cache/scalp_pick.json', 'w'))

if __name__ == '__main__':
    if sys.argv[1:2] == ['grid']: grid(sys.argv[2])
    elif sys.argv[1:2] == ['pick']: pick()

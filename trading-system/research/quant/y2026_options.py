"""2026 only: the indicator's trades priced as the options you would actually buy, time decay included.

    python y2026_options.py nifty        (or sensex; needs fetch_options.py first)

Each trade (default rules: original + volume check; also the 'breakeven at 0.25R, then trail' and 'whole trade at 3R'
exits of y2026_exits.py) is a BUY of a call (BUY signal) or a put (SELL signal):
  strike   at the money at entry (ATM), one strike in the money (ITM) or out of the money (OTM)
  expiry   the nearest weekly expiry (on expiry day: that day's), or the next one
The option price at entry, book-half and exit is Black-Scholes on the index price at that minute with the day's
implied volatility, solved from the exchange's real prices for that option (bhavcopy open, and close when it isn't
expiry day), and the time left to expiry in trading minutes. So time decay (and the speed of expiry day) is in.
Costs: slippage 1 Nifty / 2 Sensex premium points a trade, 0.13% of the selling price (STT and charges), Rs 20 an
order. Rupees at 5 lots (Nifty 65, Sensex 20 a lot). Also: the same with the old estimate (half the index points).
"""
import collections, json, math, sys
import y2026 as Y
sys.path.insert(0, '../../alerts')
import cprb_alerts as A
import y2026_exits as X

NM, D26, H1 = Y.B.name, Y.D26, Y.H1
STEP = {'nifty': 50, 'sensex': 100}[NM]
UNITS = {'nifty': 65, 'sensex': 20}[NM] * 5
SLIP = {'nifty': 1.0, 'sensex': 2.0}[NM]
OPT = json.load(open(f'../.cache/opt_{NM}.json'))
R_RATE = 0.065
CX, walk_be, walk = X.CX, X.walk_be, X.walk

def ncdf(x): return 0.5 * (1 + math.erf(x / math.sqrt(2)))

def bs(S, K, T, iv, typ):
    if T <= 1e-9 or iv <= 0: return max(0.0, (S - K) if typ == 'CE' else (K - S))
    v = iv * math.sqrt(T); d1 = (math.log(S / K) + (R_RATE + 0.5 * iv * iv) * T) / v; d2 = d1 - v
    if typ == 'CE': return S * ncdf(d1) - K * math.exp(-R_RATE * T) * ncdf(d2)
    return K * math.exp(-R_RATE * T) * ncdf(-d2) - S * ncdf(-d1)

def implied(price, S, K, T, typ):
    if T <= 1e-9 or price <= max(0.0, (S - K) if typ == 'CE' else (K - S)) + 0.05: return None
    lo, hi = 0.01, 3.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if bs(S, K, T, mid, typ) > price: hi = mid
        else: lo = mid
    return (lo + hi) / 2

def wdays(a, b):
    """Weekdays after date a up to and including date b."""
    import datetime as dt
    x, y = dt.date.fromisoformat(a), dt.date.fromisoformat(b); n = 0
    while x < y:
        x += dt.timedelta(days=1); n += x.weekday() < 5
    return n

def T_of(d, exp, minute):
    return max(0.0, (930 - minute) + 375 * wdays(d, exp)) / (375 * 252)

IVC = {}
def day_iv(d, exp, K, typ):
    """The day's implied volatility of this option: from its open (9:15) and, if not expiry day, its close."""
    key = (d, exp, K, typ)
    if key in IVC: return IVC[key]
    ch = OPT[d][exp]
    ks = sorted(ch, key=lambda s: abs(float(s) - K))
    one = Y.one[d]; S_open, S_close = one[0][1], one[-1][4]
    ivs = []
    for s in ks[:3]:
        q = ch[s].get(typ)
        if not q: continue
        o, h, l, c, v = q
        if v <= 0: continue
        a = implied(o, S_open, float(s), T_of(d, exp, 555), typ) if o > 0 else None
        b = implied(c, S_close, float(s), T_of(d, exp, 929), typ) if (c > 0 and exp != d) else None
        ivs = [x for x in (a, b) if x and 0.03 < x < 2.0]
        if ivs: break
    IVC[key] = sum(ivs) / len(ivs) if ivs else None
    return IVC[key]

def option_trade(d, side, legs, strike_kind, expiry_kind):
    """legs: [(entry minute, entry index price), [(weight, exit minute, exit index price), ...]] -> rupees, points
    (premium per unit, after costs), or None if the option isn't in the data."""
    (m0, S0), exits = legs
    exps = sorted(OPT.get(d, {}))
    if not exps: return None
    exp = (exps[1] if len(exps) > 1 else None) if expiry_kind == 'next' else exps[0]
    if expiry_kind == 'skip0' and exps[0] == d: exp = exps[1] if len(exps) > 1 else None
    if exp is None: return None
    typ = 'CE' if side > 0 else 'PE'
    K = round(S0 / STEP) * STEP + {'ATM': 0, 'ITM': -side * STEP, 'OTM': side * STEP}[strike_kind]
    iv = day_iv(d, exp, K, typ)
    if iv is None: return None
    P0 = bs(S0, K, T_of(d, exp, m0), iv, typ)
    pts = sum(w * (bs(S1, K, T_of(d, exp, m1), iv, typ) - P0) for w, m1, S1 in exits)
    sell = sum(w * bs(S1, K, T_of(d, exp, m1), iv, typ) for w, m1, S1 in exits)
    pts -= SLIP + 0.0013 * sell
    orders = 1 + len(exits)
    return pts * UNITS - 20 * orders, pts, P0, (wdays(d, exp) if exp != d else 0)

def legs_now(t):
    m0 = 556 if t['src'] == 'MAGNET' else t['m']
    x = t['exit']; half = [e for e in t['ev'] if e['kind'] == 'half']
    if half: return (m0, t['e']), [(0.5, half[0]['m'], half[0]['px']), (0.5, x['m'], x['px'])]
    return (m0, t['e']), [(1.0, x['m'], x['px'])]

def trades(kind):
    """Taken trades with their option legs under an exit rule ('now', 'BE trail', '3R')."""
    ob, om = A.run_breakout, A.run_magnet
    if kind != 'now':
        def run(c1, side, e, start, stp, R, edge):
            q = e + side * 0.25 * R
            r = walk_be(c1, side, e, start, stp, q, edge, None if edge else R) if kind == 'BE trail' else \
                walk_be(c1, side, e, start, stp, None, e + side * 3 * R)
            return dict(ev=[], stp=stp, exit=A.done(r[1], r[2], r[3], r[0]))
        A.run_breakout = lambda c1, side, e, start, stp, over, cost, R=None: run(c1, side, e, start, stp, side * (e - stp) if R is None else R, None)
        A.run_magnet = lambda c1, side, e, edge, over, cost, risk=None, R=None, start=556: run(c1, side, e, start, e - side * 0.003 * e, 0.003 * e, edge if kind == 'BE trail' else None)
    out = []
    for d in D26:
        for t in A.day_trades(CX[d], Y.one[d], 929, True, False, 'classic'):
            if t['taken']: out.append(dict(d=d, src=t['src'], side=t['side'], pts=t['exit']['pnl'], legs=legs_now(t), m=t['m']))
    A.run_breakout, A.run_magnet = ob, om
    return out

def summary(label, rows, extra=''):
    n = len(rows); rs = [r['rs'] for r in rows]; a = sum(r['rs'] for r in rows if r['d'] in H1)
    eq = pk = dd = 0
    for v in rs: eq += v; pk = max(pk, eq); dd = min(dd, eq - pk)
    print(f"  {label:44} {n:3} tr, {100 * sum(v > 0 for v in rs) / max(1, n):3.0f}% won, Rs {sum(rs):+10,.0f} (Jan-Jun {a:+9,.0f}, "
          f"Jul-Oct {sum(rs) - a:+9,.0f}), worst fall Rs {dd:9,.0f}{extra}")

if __name__ == '__main__':
    A.RULES, A.SWEEP, A.VOLCHECK = 'classic', False, True
    RS_OLD = {'nifty': 32.5, 'sensex': 10.0}[NM] * 5
    print(f"{NM.upper()} 2026, 5 lots, option prices with time decay (Black-Scholes, the day's implied volatility)")
    base = trades('now')
    for kind, ts in (('now', base), ('BE trail', trades('BE trail')), ('3R', trades('3R'))):
        print(f"\nEXIT: {kind}")
        old = [dict(d=t['d'], rs=t['pts'] * RS_OLD) for t in ts]
        summary('old estimate (half the index points)', old)
        for sk in ('ATM', 'ITM', 'OTM'):
            for ek in ('near', 'next', 'skip0'):
                rows = []
                for t in ts:
                    r = option_trade(t['d'], t['side'], t['legs'], sk, ek)
                    if r: rows.append(dict(d=t['d'], rs=r[0], dte=r[3], src=t['src'], prem=r[2], m=t['m']))
                summary(f"{sk} strike, {'nearest expiry' if ek == 'near' else 'next expiry' if ek == 'next' else 'nearest, next on expiry day'}", rows,
                        f" | premium paid avg {sum(r['prem'] for r in rows) / max(1, len(rows)):5.0f}")
                if kind == 'now' and sk == 'ATM' and ek == 'near':
                    by = collections.defaultdict(list)
                    for r in rows: by[min(r['dte'], 4)].append(r['rs'])
                    print("     by days to expiry: " + ', '.join(f"{'expiry day' if k == 0 else str(k) + ('+' if k == 4 else '') + ' d'}: {len(v)} tr Rs {sum(v):+,.0f}"
                                                         for k, v in sorted(by.items())))
                    bys = collections.defaultdict(list)
                    for r in rows: bys[r['src']].append(r['rs'])
                    print("     by setup: " + ', '.join(f"{k.lower()}: {len(v)} tr Rs {sum(v):+,.0f}" for k, v in bys.items()))

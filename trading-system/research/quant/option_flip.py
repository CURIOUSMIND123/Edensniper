"""The indicator on the OPTION charts (asked on 19 October 2026): the user put the CPR Breakout indicator on the call and
the put of the same strike and saw a SELL on one while the other went up. The idea: a SELL on one option -> BUY the
other one. Tested on the last 3 months with real 1-minute option candles.

    python option_flip.py nifty        (or sensex)

Data: Upstox's free 1-minute candles of option contracts still trading (expired weeklies need a paid login), so each
day uses the nearest expiry after it that is still listed and has the at-the-money strike traded through the day
(strike nearest the 9:15 open); on most days that is the October / November monthly, 1-3 months away, not the weekly.
Volume for the volume profile: NIFTYBEES, as the indicator uses on any chart.
Signals: the indicator's original rules on each option's own chart, as TradingView runs it there (an option's price
is under 50,000, so it takes the Nifty settings: yesterday's POC, no volume check, stops at most 55 points): CPR
Magnet, the 15-minute breakout (+ one reversal), the 3-day volume lines; one trade at a time per chart.
The user's trade: a SELL on the put -> buy the call (a SELL on the call -> buy the put) at the close of the signal's
candle. Exits tried: when the SELL trade on the other chart closes (mirror); +20% / -10% of the premium; +30% / -15%;
held to 3:15. Costs 2 (Nifty) / 5 (Sensex) premium points a trade; a candle reaching both counts as the stop.
For comparison: a BUY on an option -> buy that option, same exits.

    python option_flip.py nifty synthetic

The same on the NEAREST WEEKLY (what the user watched; expired weeklies have no free 1-minute data): each minute's
call / put price worked out from the index's 1-minute candle (Black-Scholes, rate 6.5%), the time left to expiry and
that day's implied volatility from the exchange's daily option prices of the day before (fetch_options.py), so time
decay is in; the volatility moves only from day to day. The strike nearest the 9:15 open; the nearest expiry on or
after the day (expiry day included).
"""
import collections, datetime as dt, gzip, json, math, os, sys, time, urllib.request
sys.path.insert(0, '../../alerts')
import cprb_alerts as A

NM = sys.argv[1] if len(sys.argv) > 1 else 'nifty'
SYN = 'synthetic' in sys.argv[2:]
SPEC = A.SPEC[NM]
EXCH = 'NSE' if NM == 'nifty' else 'BSE'
LOT = SPEC['lot']
COST = 2.0 if NM == 'nifty' else 5.0
START, END = dt.date(2026, 7, 20), dt.date(2026, 10, 19)
TODAY = dt.date(2026, 10, 19)
RAW = '../.cache/optflip_raw'
os.makedirs(RAW, exist_ok=True)
A.RULES, A.SWEEP, A.CPR_CALLS, A.LADDER = 'classic', False, False, False
A.POC_DAYS, A.VOLCHECK, A.STOP_MAX = {'nifty': 1}, {'nifty': False}, {'nifty': 55}
OSPEC = dict(A.SPEC['nifty'])                 # the indicator on an option chart takes the Nifty settings

def instruments():
    p = f'../.cache/upstox_{EXCH}.json.gz'
    if not os.path.exists(p) or time.time() - os.path.getmtime(p) > 86400:
        urllib.request.urlretrieve(f'https://assets.upstox.com/market-quote/instruments/exchange/{EXCH}.json.gz', p)
    seg, name = (EXCH + '_FO'), NM.upper()
    out = collections.defaultdict(dict)       # expiry date -> {(strike, 'CE'/'PE'): key}
    for x in json.load(gzip.open(p)):
        if x.get('segment') == seg and x.get('name') == name and x.get('instrument_type') in ('CE', 'PE'):
            e = dt.datetime.fromtimestamp(x['expiry'] / 1000, A.IST).date()
            out[e][(x['strike_price'], x['instrument_type'])] = x['instrument_key']
    return out

def candles(key, a=START - dt.timedelta(days=12), b=END):
    """{date: [(minute, o, h, l, c)]} for one instrument (cached)."""
    p = os.path.join(RAW, key.replace('|', '_') + '.json')
    if os.path.exists(p):
        return json.load(open(p))
    try:
        raw = A.fetch_range(key, a, b)
    except Exception as e:
        print('  (no data', key, e, ')')
        raw = {}
    if str(TODAY) not in raw:
        try:
            raw.update(A.fetch_today(key))
        except Exception:
            pass
    out = {d: [[m] + list(mm[m][:4]) for m in sorted(mm)] for d, mm in raw.items()}
    json.dump(out, open(p, 'w'))
    return out

def opt_context(sess, vol, d):
    """The indicator's daily context on an option chart (like cprb_alerts.context, from the days the contract has)."""
    days = sorted(x for x in sess if x < d and len(sess[x]) >= 100)
    if len(days) < 3:
        return None
    D = {x: (sess[x][0][1], max(r[2] for r in sess[x]), min(r[3] for r in sess[x]), sess[x][-1][4]) for x in days}
    lv = A.levels(*D[days[-1]][1:])
    past = [A.levels(*D[x][1:])['w'] for x in days[-21:-1]]
    rank = sum(w < lv['w'] for w in past) / len(past) if len(past) >= 5 else 0.5
    ylv = A.levels(*D[days[-2]][1:])
    H = {x: A.day_hist([tuple(r) for r in sess[x]], vol.get(x, {}), OSPEC['bin']) for x in days[-3:]}
    poc, vah, val = A.poc_va(*A.combine([H[days[-1]]]), OSPEC['bin'])
    return dict(OSPEC, today=d, prev=days[-1], lv=lv, rank=rank, narrow=rank < 1 / 3,
                rel=1 if lv['bot'] > ylv['top'] else -1 if lv['top'] < ylv['bot'] else 0,
                yc=D[days[-1]][3], yh=D[days[-1]][1], yl=D[days[-1]][2], poc=poc, vah=vah, val=val, pocn=1,
                yday=[tuple(r) for r in sess[days[-1]]], yvol=vol.get(days[-1], {}), c5h=[],
                lines=A.vol_lines(*A.combine([H[x] for x in days[-3:]]), OSPEC['bin']), tvol=vol.get(d, {}))

def px_at(c1, m):
    """The option's last price at the close of minute m (or the latest before it)."""
    p = None
    for r in c1:
        if r[0] > m:
            break
        p = r[4]
    return p

def exit_fixed(c1, e, start, up, dn, last=A.OUT):
    """Bought at e: out at +up / -dn (fractions of e; the stop first in a candle reaching both) or at `last`."""
    tg, st = e * (1 + up), e * (1 - dn)
    for m, o, h, l, c in c1:
        if m < start:
            continue
        if o <= st:
            return o
        if l <= st:
            return st
        if h >= tg:
            return tg
        if m >= last:
            return c
    return c1[-1][4] if c1 else e

# ---------------- the synthetic weekly ----------------
R_ = 0.065
def ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))

def bs(S, K, T, v, typ):
    T = max(T, 1 / (365 * 1440))
    d1 = (math.log(S / K) + (R_ + v * v / 2) * T) / (v * math.sqrt(T))
    d2 = d1 - v * math.sqrt(T)
    if typ == 'CE':
        return S * ncdf(d1) - K * math.exp(-R_ * T) * ncdf(d2)
    return K * math.exp(-R_ * T) * ncdf(-d2) - S * ncdf(-d1)

def implied(price, S, K, T, typ):
    lo, hi = 0.01, 2.0
    if price <= bs(S, K, T, lo, typ) or price >= bs(S, K, T, hi, typ):
        return None
    for _ in range(60):
        mid = (lo + hi) / 2
        if bs(S, K, T, mid, typ) > price:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2

def tleft(d, m, e):
    return ((dt.date.fromisoformat(e) - dt.date.fromisoformat(d)).days * 1440 + (930 - m)) / (365 * 1440)

def synthetic(idx):
    """rows like main(): the nearest weekly, priced from the index (see the top)."""
    opt = json.load(open(f'../.cache/opt_{NM}.json'))
    vol = {}
    bees = A.fetch_range(A.BEES, START - dt.timedelta(days=12), END)
    if str(TODAY) not in bees:
        bees.update(A.fetch_today(A.BEES))
    vol = {d: {m: v[4] for m, v in mm.items()} for d, mm in bees.items()}
    alld = sorted(d for d in idx if len(idx[d]) >= 300 or d == str(TODAY))
    od = sorted(opt)
    IV = {}
    def iv_for(d, e):
        """Implied volatility for day d, expiry e: the day before's settlement prices at the strike nearest its close."""
        if (d, e) in IV:
            return IV[(d, e)]
        prev = [x for x in od if x < d]
        v = None
        if prev and e in opt[prev[-1]]:
            p = prev[-1]
            S = idx[p][max(idx[p])][3] if p in idx else None
            if S:
                ks = sorted(opt[p][e], key=lambda k: abs(float(k) - S))[:1]
                ivs = [implied(opt[p][e][k][typ][3], S, float(k), tleft(p, 930, e), typ)
                       for k in ks for typ in ('CE', 'PE') if typ in opt[p][e][k] and opt[p][e][k][typ][3] > 0]
                ivs = [x for x in ivs if x]
                v = sum(ivs) / len(ivs) if ivs else None
        IV[(d, e)] = v
        return v
    rows, used = [], []
    for d in alld:
        if not (START <= dt.date.fromisoformat(d) <= END):
            continue
        prevs = [x for x in od if x < d]
        if not prevs:
            continue
        exps = sorted(e for e in opt[prevs[-1]] if e >= d)
        if not exps:
            continue
        e = exps[0]
        s0 = idx[d][min(idx[d])][0]
        K = round(s0 / SPEC['step']) * SPEC['step']
        win = [x for x in alld if x <= d][-4:]
        sess = {'CE': {}, 'PE': {}}
        ok = True
        for x in win:
            v = iv_for(x, e) or iv_for(x, min(opt[[y for y in od if y < x][-1]]) if [y for y in od if y < x] else e)
            if not v:
                ok = False
                break
            for typ in ('CE', 'PE'):
                rs = []
                for m in sorted(idx[x]):
                    o, h, l, c = idx[x][m][:4]
                    T = tleft(x, m, e)
                    po, ph, pl, pc = (bs(y, K, T, v, typ) for y in (o, h, l, c))
                    rs.append([m, po, max(ph, pl, po, pc), min(ph, pl, po, pc), pc])
                sess[typ][x] = rs
        if not ok:
            continue
        dte = (dt.date.fromisoformat(e) - dt.date.fromisoformat(d)).days
        used.append((d, K, e, dte))
        rows += flips(d, sess, vol, dte)
    return rows, used

def flips(d, charts, vol, dte):
    """The indicator on each option's chart; a SELL on one -> buy the other (a BUY -> buy that one)."""
    rows = []
    for typ, sess in charts.items():
        other = 'PE' if typ == 'CE' else 'CE'
        cx = opt_context(sess, vol, d)
        if not cx:
            continue
        c1 = [tuple(r) for r in sess[d]]
        o1 = [tuple(r) for r in charts[other][d]]
        for t in A.day_trades(cx, c1, A.CLOSE - 1, True, False, 'classic'):
            if not t['taken'] or not t['exit']:
                continue
            buy, bc = (other, o1) if t['side'] < 0 else (typ, c1)
            em = t['known'] - 1
            ep = px_at(bc, em)
            if not ep:
                continue
            res = {}
            xm = min(t['exit']['m'], A.OUT)
            res['mirror'] = (px_at(bc, xm) or ep) - ep - COST
            res['+20/-10%'] = exit_fixed(bc, ep, em + 1, 0.20, 0.10) - ep - COST
            res['+30/-15%'] = exit_fixed(bc, ep, em + 1, 0.30, 0.15) - ep - COST
            res['3:15'] = (px_at(bc, A.OUT) or ep) - ep - COST
            rows.append(dict(d=d, m=em, chart=typ, sig='SELL' if t['side'] < 0 else 'BUY', src=t['src'], bought=buy,
                             ep=ep, dte=dte, res=res))
    return rows

def main():
    if SYN:
        idx = A.fetch_range(SPEC['key'], START - dt.timedelta(days=12), END)
        if str(TODAY) not in idx:
            idx.update(A.fetch_today(SPEC['key']))
        return synthetic(idx)
    ins = instruments()
    idx = A.fetch_range(SPEC['key'], START, END)
    if str(TODAY) not in idx:
        idx.update(A.fetch_today(SPEC['key']))
    bees = A.fetch_range(A.BEES, START - dt.timedelta(days=12), END)
    if str(TODAY) not in bees:
        bees.update(A.fetch_today(A.BEES))
    vol = {d: {m: v[4] for m, v in mm.items()} for d, mm in bees.items()}
    days = sorted(d for d in idx if START <= dt.date.fromisoformat(d) <= END and len(idx[d]) >= 300 or d == str(TODAY))
    rows, used = [], []
    for d in days:
        dd = dt.date.fromisoformat(d)
        s0 = idx[d][min(idx[d])][0]
        K = round(s0 / SPEC['step']) * SPEC['step']
        pick = None
        for e in sorted(x for x in ins if x > dd):
            near = sorted({k for k, _ in ins[e] if (k, 'CE') in ins[e] and (k, 'PE') in ins[e]}, key=lambda k: abs(k - s0))[:2]
            for k in near:                            # the listed strike nearest the open (or the next one)
                if abs(k - s0) > 2 * SPEC['step']:
                    break
                sc, sp = candles(ins[e][(k, 'CE')]), candles(ins[e][(k, 'PE')])
                need = 100 if d == str(TODAY) else 300
                if len(sc.get(d, [])) >= need and len(sp.get(d, [])) >= need:
                    pick, K = (e, sc, sp), int(k)
                    break
            if pick:
                break
        if not pick:
            print('  no option data for', d, 'strike', K)
            continue
        e, sc, sp = pick
        used.append((d, K, str(e), (e - dd).days))
        rows += flips(d, {'CE': sc, 'PE': sp}, vol, (e - dd).days)
    return rows, used

def report(rows, used):
    print(f"{NM.upper()} {'SYNTHETIC NEAREST WEEKLY' if SYN else 'REAL'} options, {used[0][0]} - {used[-1][0]}: {len(used)} days; expiry used: "
          + ', '.join(f"{k} ({v} days)" for k, v in collections.Counter(u[2] for u in used).items())
          + f"; days to expiry: median {sorted(u[3] for u in used)[len(used) // 2]}")
    print(f"Costs {COST:g} premium points a trade; 1 lot = {LOT}; per exit: trades, won %, average and total premium points, "
          "rupees for 1 lot")
    def show(label, rs):
        if not rs:
            print(f"  {label:44} none"); return
        out = []
        for k in ('mirror', '+20/-10%', '+30/-15%', '3:15'):
            v = [r['res'][k] for r in rs]
            out.append(f"{k} {100 * sum(x > 0 for x in v) / len(v):3.0f}% {sum(v) / len(v):+6.1f} {sum(v):+7.0f} (Rs {sum(v) * LOT:+,.0f})")
        print(f"  {label:44} {len(rs):3} tr | " + ' | '.join(out))
    sells = [r for r in rows if r['sig'] == 'SELL']
    buys = [r for r in rows if r['sig'] == 'BUY']
    print("\nTHE IDEA: a SELL on one option -> buy the other")
    show('all', sells)
    show('SELL on the put -> buy the call', [r for r in sells if r['chart'] == 'PE'])
    show('SELL on the call -> buy the put', [r for r in sells if r['chart'] == 'CE'])
    for src in sorted({r['src'] for r in sells}):
        show(f'  signal: {src.lower()}', [r for r in sells if r['src'] == src])
    for lab, f in (('  expiry within 7 days', lambda r: r['dte'] <= 7), ('  expiry 8-30 days', lambda r: 8 <= r['dte'] <= 30),
                   ('  expiry over 30 days', lambda r: r['dte'] > 30)):
        show(lab, [r for r in sells if f(r)])
    for mth in sorted({r['d'][:7] for r in sells}):
        show(f'  month {mth}', [r for r in sells if r['d'][:7] == mth])
    print("\nFOR COMPARISON: a BUY on an option -> buy that option")
    show('all', buys)
    print("\nTODAY")
    for r in rows:
        if r['d'] == str(TODAY):
            print(f"  {A.hhmm(r['m'])} {r['sig']} on the {r['chart']} ({r['src'].lower()}) -> bought the {r['bought']} at "
                  f"{r['ep']:.2f}: " + ', '.join(f"{k} {v:+.1f}" for k, v in r['res'].items()))

if __name__ == '__main__':
    rows, used = main()
    json.dump(dict(rows=rows, used=used), open(f'../.cache/optflip_{NM}{"_syn" if SYN else ""}.json', 'w'))
    report(rows, used)

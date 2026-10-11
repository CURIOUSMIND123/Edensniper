"""2026 only: trading only on expiry days and the day before (Nifty Monday + Tuesday, Sensex Wednesday + Thursday),
buying a slightly out-of-the-money option of the nearest expiry with as many lots as Rs 30,000 buys.

    python y2026_expiry.py dump nifty       (and: dump sensex; needs fetch_options.py first)
    python y2026_expiry.py                  the report

The trades are the alert program's with its default settings (Nifty: yesterday's POC, no volume check; Sensex: the
volume check, no POC filter). Each one is priced as the option you would buy, with y2026_options.py's model:
Black-Scholes on the index price at the entry, book-half and exit minutes, with that day's implied volatility of the
option solved from the exchange's real prices (F&O bhavcopy) and the time left to expiry, so time decay and the speed
of expiry day are in. Costs: slippage 1 Nifty / 2 Sensex premium points, 0.13% of the selling price, Rs 20 an order.
Strike: at the money, 1 strike (Nifty 50 / Sensex 100 points) or 2 strikes out of the money; nearest expiry (on
expiry day the one expiring that afternoon). Lots: as many as Rs 30,000 buys at the entry premium (Nifty 65, Sensex
20 a lot). One account: a trade is taken only when no other trade is open (Sensex first when both come together).
"""
import collections, json, math, sys

CAPITAL = 30000
LOT = {'nifty': 65, 'sensex': 20}
START30 = '2026-09-10'                                   # the last 30 days of data: 10 September - 9 October 2026

def dump(nm):
    sys.argv = [sys.argv[0], nm]
    import y2026_options as OP
    A, Y = OP.A, OP.Y
    A.RULES, A.SWEEP, A.VOLCHECK = 'classic', False, {'nifty': False, 'sensex': True}   # the defaults
    days = sorted(OP.OPT)
    nxt = {d: days[i + 1] for i, d in enumerate(days[:-1])}
    out, nofit = [], 0
    for d in OP.D26:
        exps = sorted(OP.OPT.get(d, {}))
        if not exps: continue
        kind = 'expiry' if exps[0] == d else 'day before' if nxt.get(d) == exps[0] else 'other'
        for t in A.day_trades(OP.CX[d], Y.one[d], 929, True, False, 'classic'):
            if not t['taken']: continue
            (m0, S0), exits = OP.legs_now(t)
            row = dict(d=d, nm=nm, kind=kind, src=t['src'], side=t['side'], m=t['m'], x=t['exit']['m'], ipts=t['exit']['pnl'])
            typ = 'CE' if t['side'] > 0 else 'PE'
            for k in (0, 1, 2):
                K = round(S0 / OP.STEP) * OP.STEP + t['side'] * k * OP.STEP
                iv = OP.day_iv(d, exps[0], K, typ)
                if iv is None:
                    row[f'k{k}'] = None; nofit += 1; continue
                P0 = OP.bs(S0, K, OP.T_of(d, exps[0], m0), iv, typ)
                outs = [(w, OP.bs(S1, K, OP.T_of(d, exps[0], m1), iv, typ)) for w, m1, S1 in exits]
                pts = sum(w * (P1 - P0) for w, P1 in outs) - OP.SLIP - 0.0013 * sum(w * P1 for w, P1 in outs)
                row[f'k{k}'] = dict(K=K, P0=P0, out=[P1 for _, P1 in outs], pts=pts, orders=1 + len(exits), buy=P0 + OP.SLIP / 2)
            out.append(row)
    json.dump(out, open(f'../.cache/expiry_trades_{nm}.json', 'w'))
    print(nm, len(out), 'trades,', round(sum(r['ipts'] for r in out)), 'index points;', nofit, 'option prices missing')

def lots_for(money, r, k):
    o = r[f'k{k}']
    return int(money // (o['buy'] * LOT[r['nm']])) if o else 0

def rupees(r, k, lots):
    o = r[f'k{k}']
    return o['pts'] * lots * LOT[r['nm']] - 20 * o['orders'] if lots else 0.0

def one_account(rows):
    took, day, free = [], None, 0
    for r in sorted(rows, key=lambda r: (r['d'], r['m'], r['nm'] != 'sensex')):
        if r['d'] != day: day, free = r['d'], 0
        if r['m'] >= free:
            took.append(r); free = r['x'] + 1
    return took

def report(label, rows, k, show=False):
    rs, lots = [], []
    bal, broke = CAPITAL, None
    for r in rows:
        n = lots_for(CAPITAL, r, k); lots.append(n)
        rs.append(rupees(r, k, n))
        nb = lots_for(bal, r, k)                         # the account: all of the balance into each trade
        bal += rupees(r, k, nb)
        if broke is None and bal < CAPITAL / 10: broke = r['d']
    eq = pk = dd = 0
    for v in rs: eq += v; pk = max(pk, eq); dd = min(dd, eq - pk)
    w = [v for v in rs if v > 0]; l = [v for v in rs if v <= 0]
    print(f"  {label:34} {len(rs):3} trades, {len(w):3} won / {len(l):3} lost | Rs {sum(rs):+10,.0f} | biggest win Rs {max(rs, default=0):+9,.0f}, "
          f"biggest loss Rs {min(rs, default=0):+9,.0f} | worst fall Rs {dd:9,.0f} | lots avg {sum(lots) / max(1, len(lots)):4.1f} max {max(lots, default=0):3} | "
          f"account all-in from Rs 30,000: Rs {bal:,.0f}" + (f" (below Rs 3,000 on {broke})" if broke else ''))
    if show:
        for r, v, n in zip(rows, rs, lots):
            o = r[f'k{k}']
            print(f"     {r['d']} {r['nm']:6} {r['kind']:10} {r['src'].lower():11} {'BUY ' if r['side'] > 0 else 'SELL'} {r['m'] // 60:02d}:{r['m'] % 60:02d} "
                  f"{o['K']:>7.0f} {'CE' if r['side'] > 0 else 'PE'} {n:3} lots, premium {o['P0']:6.1f} -> {', '.join(f'{p:.1f}' for p in o['out'])} "
                  f"| index {r['ipts']:+6.0f} pts | Rs {v:+9,.0f}")

if __name__ == '__main__':
    if sys.argv[1:2] == ['dump']:
        dump(sys.argv[2]); sys.exit()
    rows = [r for nm in ('nifty', 'sensex') for r in json.load(open(f'../.cache/expiry_trades_{nm}.json'))]
    exp = one_account([r for r in rows if r['kind'] != 'other'])
    alld = one_account(rows)
    for title, lo in (('LAST 30 DAYS (10 Sep - 9 Oct 2026)', START30), ('ALL OF 2026 (1 Jan - 9 Oct)', '2026-01-01')):
        print(f"\n{title}: Rs 30,000 into each trade (as many lots as it buys), one trade at a time, time decay and costs included")
        for k, kl in ((1, '1 strike out of the money'), (2, '2 strikes out of the money'), (0, 'at the money')):
            e = [r for r in exp if r['d'] >= lo and r[f'k{k}']]
            report(f"expiry + day before, {kl}", e, k, show=(k == 1 and lo == START30))
            report(f"  every day, {kl}", [r for r in alld if r['d'] >= lo and r[f'k{k}']], k)
        e = [r for r in exp if r['d'] >= lo and r['k1']]
        for kind in ('expiry', 'day before'):
            report(f"  only {kind} days, 1 strike OTM", [r for r in e if r['kind'] == kind], 1)
        for nm in ('nifty', 'sensex'):
            report(f"  only {nm.capitalize()}, 1 strike OTM", [r for r in e if r['nm'] == nm], 1)

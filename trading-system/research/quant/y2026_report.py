"""2026 only: the full report of what the indicator / phone alerts trade with their current settings, from the
alert program's own trade logic (alerts/cprb_alerts.py, checked trade for trade against the backtest).

    python y2026_report.py nifty        then  python y2026_report.py sensex   then  python y2026_report.py both

Rules compared: default (original rules + the volume check), original rules without it, original rules + liquidity
sweeps, 1:4 targets, small stops (60 minutes). For each index: trades, won / lost, points won / lost / net, average win / loss, biggest win,
worst trade, worst fall from a high, longest losing run, January-June / July-October, by setup and by exit. Both
indices together: by month in points and rupees, and what Rs 30,000 becomes trading 2 or 5 lots (also with the
trades in random order, 10,000 times). Rupees: an at-the-money option moves about half the index, so one index point
is Rs 32.5 per Nifty lot (65) and Rs 10 per Sensex lot (20); costs (4 Nifty / 12 Sensex points a trade) are already
in the points; time decay is left out.
"""
import collections, json, random, sys

RULES = {'default (original + volume check)': ('classic', False, True), 'original, no volume check': ('classic', False, False),
         'original + sweeps': ('classic', True, False), '1:4 targets': ('rr', False, False), 'small stops, 60 min': ('small', False, False)}
RS = {'nifty': 32.5, 'sensex': 10.0}
CACHE = '../.cache/report_{}.json'

def dump(nm):
    import y2026 as Y
    sys.path.insert(0, '../../alerts')
    import cprb_alerts as A
    spec = A.SPEC[nm]; sess = {d: Y.one[d] for d in Y.days}
    vol = collections.defaultdict(dict)
    for k, v in Y.bees.items(): vol[k[:10]][int(k[11:13]) * 60 + int(k[14:16])] = v[4]
    daily = {d: Y.DAY[d] for d in Y.days}
    cx = {d: A.context(spec, sess, vol, d, daily) for d in Y.D26}
    for d in Y.D26: cx[d]['tvol'] = vol.get(d, {})
    out = {}
    for lab, (rules, sweep, vcheck) in RULES.items():
        A.SWEEP, A.VOLCHECK = sweep, vcheck
        out[lab] = [dict(d=d, m=t['m'], mx=t['exit']['m'], src=t['src'], side=t['side'], pnl=t['exit']['pnl'], why=t['exit']['why'])
                    for d in Y.D26 for t in A.day_trades(cx[d], Y.one[d], 929, True, False, rules) if t['taken']]
    json.dump(dict(days=Y.D26, h1=sorted(Y.H1), trades=out), open(CACHE.format(nm), 'w'))

def stats(ts, h1):
    p = [t['pnl'] for t in ts]; w = [v for v in p if v > 0]; l = [v for v in p if v <= 0]
    eq = pk = dd = 0; run = worst_run = 0
    for v in p:
        eq += v; pk = max(pk, eq); dd = min(dd, eq - pk)
        run = run + 1 if v <= 0 else 0; worst_run = max(worst_run, run)
    a = sum(t['pnl'] for t in ts if t['d'] in h1)
    return dict(n=len(p), w=len(w), l=len(l), won=sum(w), lost=sum(l), net=sum(p), avg_w=sum(w) / max(1, len(w)),
                avg_l=sum(l) / max(1, len(l)), best=max(p, default=0), worst=min(p, default=0), dd=dd, run=worst_run,
                a=a, b=sum(p) - a, days=len({t['d'] for t in ts}))

def line(s):
    return (f"{s['n']:4} trades on {s['days']:3} days ({s['n'] / 9.3:4.1f} a month) | {s['w']:3} won / {s['l']:3} lost "
            f"({100 * s['w'] / max(1, s['n']):3.0f}%) | won {s['won']:+8,.0f} lost {s['lost']:+8,.0f} net {s['net']:+8,.0f} pts")

def account(ts, lots, start=30000.0):
    eq, pk, dd, low = start, start, 0.0, start
    for t in ts:
        eq += t['pnl'] * RS[t['nm']] * lots(eq); pk = max(pk, eq); dd = min(dd, eq - pk); low = min(low, eq)
    return eq, dd, low

def report():
    data = {nm: json.load(open(CACHE.format(nm))) for nm in RS}
    h1 = set(data['nifty']['h1'])
    for lab in RULES:
        print(f"\n==================== {lab.upper()} ====================")
        allts = []
        for nm in RS:
            ts = data[nm]['trades'][lab]
            for t in ts: t['nm'] = nm
            allts += ts
            s = stats(ts, h1)
            print(f"{nm.upper():7} {line(s)}")
            print(f"        average win {s['avg_w']:+.0f}, average loss {s['avg_l']:+.0f}, biggest win {s['best']:+.0f}, worst trade "
                  f"{s['worst']:+.0f}, worst fall from a high {s['dd']:,.0f}, longest losing run {s['run']} trades")
            print(f"        Jan-Jun {s['a']:+,.0f}, Jul-Oct {s['b']:+,.0f} pts | at 5 lots about Rs {s['net'] * RS[nm] * 5:+,.0f} "
                  f"(worst fall Rs {s['dd'] * RS[nm] * 5:,.0f})")
            if lab.startswith('default'):
                by = collections.defaultdict(list)
                for t in ts: by[t['src']].append(t)
                for src, xs in sorted(by.items(), key=lambda kv: -len(kv[1])):
                    ss = stats(xs, h1)
                    print(f"          {src:12} {ss['n']:4} trades, {ss['w']:3} won ({100 * ss['w'] / ss['n']:3.0f}%), net {ss['net']:+7,.0f} pts, "
                          f"avg win {ss['avg_w']:+.0f} / loss {ss['avg_l']:+.0f}")
                ex = collections.Counter(('target' if t['why'].startswith('target') else 'stop at entry' if 'entry' in t['why']
                                          else 'stop' if t['why'] == 'stop' else 'trailing stop' if 'trail' in t['why'] else '3:15 / time')
                                         for t in ts)
                print("          exits: " + ', '.join(f"{k} {v}" for k, v in ex.most_common()))
        allts.sort(key=lambda t: (t['d'], t['m']))
        mo = collections.defaultdict(lambda: [0, 0.0, 0.0])
        for t in allts:
            r = mo[t['d'][:7]]; r[0] += 1; r[1] += t['pnl'] * RS[t['nm']] * 5; r[2] += t['pnl'] * RS[t['nm']] * 2
        tot5 = sum(r[1] for r in mo.values())
        print(f"BOTH    {len(allts)} trades, {sum(t['pnl'] > 0 for t in allts)} won ({100 * sum(t['pnl'] > 0 for t in allts) / len(allts):.0f}%). "
              f"At 5 lots on every trade: Rs {tot5:+,.0f} in 9.3 months, about Rs {tot5 / 9.3:,.0f} a month, Rs {tot5 / 9.3 * 12:,.0f} a year at this pace")
        print("        by month (5 lots / 2 lots): " + ', '.join(f"{k[5:]}: {r[0]} tr {r[1] / 1000:+.0f}k / {r[2] / 1000:+.0f}k" for k, r in sorted(mo.items())))
        dd = collections.defaultdict(float)
        for t in allts: dd[t['d']] += t['pnl'] * RS[t['nm']] * 5
        print(f"        days with trades {len(dd)}: {sum(v > 0 for v in dd.values())} up, {sum(v <= 0 for v in dd.values())} down; best day "
              f"Rs {max(dd.values()):+,.0f}, worst day Rs {min(dd.values()):+,.0f} (5 lots)")
        for nm_l, rule in (('5 lots', lambda eq: 5), ('2 lots', lambda eq: 2), ('2 lots, 5 from Rs 75,000', lambda eq: 5 if eq >= 75000 else 2)):
            eq, dd_, low = account(allts, rule)
            random.seed(1); half = bust = 0
            for _ in range(10000):
                sh = allts[:]; random.shuffle(sh)
                _, _, lo = account(sh, rule); half += lo < 15000; bust += lo <= 0
            print(f"        Rs 30,000, {nm_l:25}: -> Rs {eq:,.0f}; biggest fall Rs {-dd_:,.0f}; lowest Rs {low:,.0f}; random order: "
                  f"below Rs 15,000 in {half / 100:.1f}% of runs, below zero in {bust / 100:.1f}%")

if __name__ == '__main__':
    if sys.argv[1] == 'both': report()
    else: dump(sys.argv[1])

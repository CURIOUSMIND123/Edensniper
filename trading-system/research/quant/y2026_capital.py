"""2026 only: one account for both indices. All the money goes into each trade, so while a Nifty trade is open a
Sensex signal is missed, and the other way round. How many trades would have been missed, and what it costs.

    python y2026_capital.py dump nifty      (and: dump sensex) the default trades of each index (as the alert program
                                            takes them) to ../.cache/default_trades_{index}.json
    python y2026_capital.py                 both together

Each index's trades are the alert program's with its default settings (Nifty: yesterday's POC, no volume check;
Sensex: the volume check, no POC filter). Merged by time: a trade is taken only if no trade on the other index is
open (from its entry minute to its exit minute, as within one index). When both give a signal in the same minute,
one of them has to be picked: Nifty first, Sensex first, or the one with the smaller stop in rupees.
Rupees: the old estimate (an at-the-money option moves about half the index), 3 lots (about what Rs 30,000 buys:
Nifty 65 and Sensex 20 a lot), costs included in the points.
"""
import collections, json, sys

LOTS = 3
RS = {'nifty': 65 / 2 * LOTS, 'sensex': 20 / 2 * LOTS}     # rupees per index point
H1_END = '2026-07-01'

def dump(nm):
    sys.argv = [sys.argv[0], nm]                         # the backtest modules read the index from the command line
    import y2026 as Y
    sys.path.insert(0, '../../alerts')
    import cprb_alerts as A
    spec = A.SPEC[nm]; sess = {d: Y.one[d] for d in Y.days}
    vol = collections.defaultdict(dict)
    for k, v in Y.bees.items(): vol[k[:10]][int(k[11:13]) * 60 + int(k[14:16])] = v[4]
    daily = {d: Y.DAY[d] for d in Y.days}
    A.RULES, A.SWEEP = 'classic', False
    out = []
    for d in Y.D26:
        cx = A.context(spec, sess, vol, d, daily); cx['tvol'] = vol.get(d, {})
        for t in A.day_trades(cx, Y.one[d], 929, True, False, 'classic'):
            if t['taken']:
                out.append(dict(d=d, nm=nm, src=t['src'], side=t['side'], m=t['m'], x=t['exit']['m'], pnl=t['exit']['pnl'],
                                risk=abs(t['e'] - t['stp0'])))
    json.dump(out, open(f'../.cache/default_trades_{nm}.json', 'w'))
    print(nm, len(out), 'trades', round(sum(t['pnl'] for t in out)))

def one_account(ts, first):
    """Trades in time order; a trade is taken only when the money is free. first: which of two same-minute signals."""
    order = {'nifty': 0, 'sensex': 1} if first == 'nifty' else {'nifty': 1, 'sensex': 0}
    def key(t):
        if first == 'small stop': return (t['d'], t['m'], t['risk'] * RS[t['nm']])
        return (t['d'], t['m'], order[t['nm']])
    took, missed = [], []
    day, free = None, 0
    for t in sorted(ts, key=key):
        if t['d'] != day: day, free = t['d'], 0
        if t['m'] >= free:
            took.append(t); free = t['x'] + 1
        else:
            missed.append(t)
    return took, missed

def rs(ts): return sum(t['pnl'] * RS[t['nm']] for t in ts)

def line(label, ts):
    a = sum(t['pnl'] * RS[t['nm']] for t in ts if t['d'] < H1_END)
    eq = pk = dd = 0
    for t in sorted(ts, key=lambda t: (t['d'], t['m'])):
        eq += t['pnl'] * RS[t['nm']]; pk = max(pk, eq); dd = min(dd, eq - pk)
    n = collections.Counter(t['nm'] for t in ts)
    print(f"  {label:44} {len(ts):3} trades (Nifty {n['nifty']:3}, Sensex {n['sensex']:3}), {100 * sum(t['pnl'] > 0 for t in ts) / max(1, len(ts)):3.0f}% won, "
          f"Rs {rs(ts):+10,.0f} (Jan-Jun {a:+9,.0f}, Jul-Oct {rs(ts) - a:+9,.0f}), worst fall Rs {dd:8,.0f}")

if __name__ == '__main__':
    if sys.argv[1:2] == ['dump']:
        dump(sys.argv[2]); sys.exit()
    ts = [t for nm in ('nifty', 'sensex') for t in json.load(open(f'../.cache/default_trades_{nm}.json'))]
    print(f"2026, default settings, {LOTS} lots, rupees = half the index points after costs")
    line('two accounts (both indices always)', ts)
    line('Sensex only (all the money)', [t for t in ts if t['nm'] == 'sensex'])
    line('Nifty only (all the money)', [t for t in ts if t['nm'] == 'nifty'])
    print(f"  half the money on each index (half the lots in every trade): Rs {rs(ts) / 2:+,.0f}")
    for first in ('nifty', 'sensex', 'small stop'):
        took, missed = one_account(ts, first)
        print(f"\nONE ACCOUNT, same-minute signals: {first + ' first' if first != 'small stop' else 'the smaller stop first'}")
        line('taken', took)
        line('missed', missed)
        same = [t for t in missed if any(o['d'] == t['d'] and o['m'] == t['m'] for o in took)]
        print(f"  missed because both came in the same minute: {len(same)}; the other index's trade was still open: {len(missed) - len(same)}")
        by = collections.defaultdict(list)
        for t in missed: by[(t['nm'], t['src'])].append(t)
        print("  missed by setup: " + ', '.join(f"{nm} {src.lower()} {len(v)} (Rs {rs(v):+,.0f})" for (nm, src), v in sorted(by.items())))
        print(f"  missed: {sum(t['pnl'] > 0 for t in missed)} winners, {sum(t['pnl'] <= 0 for t in missed)} losers; "
              f"days with a missed trade: {len({t['d'] for t in missed})}")

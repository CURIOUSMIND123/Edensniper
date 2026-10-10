"""2026 only: every trade the indicator took (default: original rules + the volume check), replayed as if we had
waited for a retest or a small pullback before entering. Same stop price, same exit rules, from the new entry.

    python y2026_retest.py nifty        (or sensex; then: python y2026_retest.py both  -> research/RETEST_TRADES.md)

retest    breakout: after price goes 0.1% beyond the broken 15-minute high / low, a limit order back at it (+0.05%),
          valid 60 minutes; volume line: a limit order back at the broken line, valid 60 minutes; CPR Magnet: no level
          to retest (kept as it was)
pullback  a limit order k points better than the actual entry (Nifty 10 / 20 / 30, Sensex 30 / 60 / 100), valid
          15 / 30 / 60 minutes after the signal
If price reaches the stop before the order fills, there is no trade. If the order never fills, the trade is missed.
Each trade is replayed on its own (the trades after it are left as they were).
"""
import collections, json, sys

RS = {'nifty': 32.5, 'sensex': 10.0}
PULL = {'nifty': (10, 20, 30), 'sensex': (30, 60, 100)}
WAIT = (15, 30, 60)

def summary_both():
    out = ["# 2026: what waiting for a retest or a small pullback would have changed", "",
           "Every trade the indicator took in 2026 (default: original rules + the volume check), replayed as if we had waited "
           "for a retest of the broken level or a small pullback before entering. Same stop price and exit rules. "
           "`research/quant/y2026_retest.py`. Points after costs; rupees at 5 lots (delta 0.5).", ""]
    for nm in ('nifty', 'sensex'):
        D = json.load(open(f'../.cache/retest_{nm}.json'))
        out += [f"## {nm.capitalize()}", "", "| Waiting for | Filled | Missed (were winners / losers) | Stop reached first | Net points | Change | Rs at 5 lots |",
                "|---|---|---|---|---|---|---|"]
        base = sum(t['pnl'] for t in D['trades'])
        out.append(f"| nothing (as traded) | {len(D['trades'])} | - | - | {base:+,.0f} | - | {base * RS[nm] * 5:+,.0f} |")
        for v in D['variants']:
            rs = [t['alt'][v] for t in D['trades']]
            net = sum(r['pnl'] for r in rs)
            filled = sum(r['kind'] == 'filled' for r in rs)
            missed = [t for t in D['trades'] if t['alt'][v]['kind'] == 'missed']
            first = [t for t in D['trades'] if t['alt'][v]['kind'] == 'stop first']
            out.append(f"| {v} | {filled} | {len(missed)} ({sum(t['pnl'] > 0 for t in missed)} / {sum(t['pnl'] <= 0 for t in missed)}) | "
                       f"{len(first)} | {net:+,.0f} | {net - base:+,.0f} | {net * RS[nm] * 5:+,.0f} |")
        out += ["", f"### {nm.capitalize()}: trade by trade (retest, and a {PULL[nm][1]}-point pullback within 30 minutes)", "",
                "| Date | Time | Setup | Side | Entry | Result as traded | With a retest | With a pullback |", "|---|---|---|---|---|---|---|---|"]
        def cell(r, orig):
            if r['kind'] == 'missed': return f"missed (never came back): {-orig:+.0f}"
            if r['kind'] == 'stop first': return f"no trade (stop first): {-orig:+.0f}"
            if r['kind'] == 'same': return "same (no level to retest)"
            return f"in at {r['e']:,.2f}: {r['pnl']:+.0f} ({r['pnl'] - orig:+.0f})"
        for t in D['trades']:
            out.append(f"| {t['d']} | {t['time']} | {t['src'].lower()} | {'BUY' if t['side'] > 0 else 'SELL'} | {t['e']:,.2f} | "
                       f"{t['why']}: {t['pnl']:+.0f} | {cell(t['alt']['retest'], t['pnl'])} | {cell(t['alt'][f'pullback {PULL[nm][1]} pts, 30 min'], t['pnl'])} |")
        out.append("")
    open('../RETEST_TRADES.md', 'w').write('\n'.join(out) + '\n')
    print('\n'.join(l for l in out if not l.startswith('| 2026')))

if __name__ == '__main__' and sys.argv[1:2] == ['both']:
    summary_both(); sys.exit()

import y2026 as Y
sys.path.insert(0, '../../alerts')
import cprb_alerts as A

NM, D26 = Y.B.name, Y.D26
spec = A.SPEC[NM]; sess = {d: Y.one[d] for d in Y.days}
vol = collections.defaultdict(dict)
for k, v in Y.bees.items(): vol[k[:10]][int(k[11:13]) * 60 + int(k[14:16])] = v[4]
daily = {d: Y.DAY[d] for d in Y.days}
CX = {d: A.context(spec, sess, vol, d, daily) for d in D26}
for d in D26: CX[d]['tvol'] = vol.get(d, {})
COST = spec['cost']

def fill(c1, side, px, stp, after, until):
    """The first minute from `after` to `until` that trades at px: ('filled', minute, price, stopped in that minute),
    ('stop first', ...) if the stop comes first, else ('missed', ...)."""
    for m, o, h, l, c in c1:
        if m < after: continue
        if m > until: break
        if (l <= stp) if side > 0 else (h >= stp):
            # inside this minute: does the limit price come before the stop? (green: open-low-high-close)
            if (o <= px) if side > 0 else (o >= px):
                return 'filled', m, o, True
            return ('filled', m, px, True) if (px > stp if side > 0 else px < stp) else ('stop first', m, None, True)
        if (l <= px) if side > 0 else (h >= px):
            return 'filled', m, (min(o, px) if side > 0 else max(o, px)), False
    return 'missed', None, None, False

def replay(t, c1, e, mf, hit):
    """The trade from a new entry e filled at minute mf (stopped in that minute if hit), same stop and exit rules."""
    side, stp = t['side'], t['stp0']
    if hit: return side * (stp - e) - COST
    if t['src'] in ('BREAKOUT', 'REVERSAL'): r = A.run_breakout(c1, side, e, mf + 1, stp, True, COST)
    elif t['src'] == 'VOLUME LINE': r = A.run_vol(c1, side, e, mf + 1, stp, t['tgt'], t['x'], None, True, COST)
    else: r = A.run_magnet(c1, side, e, t['edge'], True, COST, side * (e - stp), side * (e - stp), mf + 1)
    return r['exit']['pnl']

def alternatives(d, t):
    c1 = Y.one[d]; side, e, stp = t['side'], t['e'], t['stp0']
    start = t['known'] if t['src'] != 'MAGNET' else 556
    out = {}
    # retest of the broken level
    if t['src'] in ('BREAKOUT', 'REVERSAL', 'VOLUME LINE'):
        if t['src'] == 'VOLUME LINE':
            lvl = t['x']; px = lvl; armed = start
        else:
            first = [x for x in c1 if x[0] < A.RANGE_END]
            lvl = max(x[2] for x in first) if side > 0 else min(x[3] for x in first)
            px = lvl + side * 0.0005 * lvl
            armed = next((m for m, o, h, l, c in c1 if m >= start and side * ((h if side > 0 else l) - lvl) >= 0.001 * lvl), None)
            stop_at = next((m for m, o, h, l, c in c1 if m >= start and ((l <= stp) if side > 0 else (h >= stp))), 10 ** 9)
            if armed is not None and stop_at <= armed: armed = 'stop'
        if armed is None:
            out['retest'] = dict(kind='missed', pnl=0.0)
        elif armed == 'stop':
            out['retest'] = dict(kind='stop first', pnl=0.0)
        else:
            k, mf, ef, hit = fill(c1, side, px, stp, armed + 1, start + 59)
            out['retest'] = dict(kind=k, pnl=0.0) if k != 'filled' else dict(kind=k, e=ef, pnl=replay(t, c1, ef, mf, hit))
    else:
        out['retest'] = dict(kind='same', e=e, pnl=t['exit']['pnl'])
    # a small pullback
    for k_pts in PULL[NM]:
        for w in WAIT:
            k, mf, ef, hit = fill(c1, side, e - side * k_pts, stp, start, start + w - 1)
            out[f'pullback {k_pts} pts, {w} min'] = dict(kind=k, pnl=0.0) if k != 'filled' else dict(kind=k, e=ef, pnl=replay(t, c1, ef, mf, hit))
    return out

if __name__ == '__main__':
    A.RULES, A.SWEEP, A.VOLCHECK = 'classic', False, True
    trades = []
    for d in D26:
        for t in A.day_trades(CX[d], Y.one[d], 929, True, False, 'classic'):
            if not t['taken']: continue
            alt = alternatives(d, t)
            trades.append(dict(d=d, time=A.hhmm(556 if t['src'] == 'MAGNET' else t['m']), src=t['src'], side=t['side'], e=t['e'],
                               pnl=t['exit']['pnl'], why=t['exit']['why'], alt=alt))
    variants = list(trades[0]['alt'])
    json.dump(dict(trades=trades, variants=variants), open(f'../.cache/retest_{NM}.json', 'w'))
    base = sum(t['pnl'] for t in trades)
    print(f"{NM.upper()} 2026: {len(trades)} trades as traded, net {base:+,.0f}")
    for v in variants:
        rs = [t['alt'][v] for t in trades]; net = sum(r['pnl'] for r in rs)
        print(f"  {v:26} filled {sum(r['kind'] == 'filled' for r in rs):3}, missed {sum(r['kind'] == 'missed' for r in rs):3}, stop first "
              f"{sum(r['kind'] == 'stop first' for r in rs):3} | net {net:+7,.0f} ({net - base:+6,.0f})")

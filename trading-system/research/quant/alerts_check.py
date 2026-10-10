"""Check that alerts/cprb_alerts.py trades exactly like the 2026 backtest (y2026_combo.py / y2026_improve.py).

    python alerts_check.py nifty        (or sensex)

1. Levels: CPR, narrow rank, CPR vs yesterday's, 30-day POC and 3-day volume lines match y2026.py for every 2026 day.
2. Trades on whole days: same trades (start minute and points) as the backtest, one book, with and without the ladder.
3. Minute by minute (as it runs live) on every 2026 day: nothing it already said changes later, and at the end of the
   day it has the same trades as on the whole day.
"""
import collections, sys
import y2026 as Y, y2026_combo as K, y2026_improve as I, y2026_vol_lines as V, cpr_orb as C
sys.path.insert(0, '../../alerts')
import cprb_alerts as A

spec = A.SPEC[Y.B.name]
sess = {d: Y.one[d] for d in Y.days}
vol = collections.defaultdict(dict)
for k, v in Y.bees.items(): vol[k[:10]][int(k[11:13]) * 60 + int(k[14:16])] = v[4]
daily = {d: Y.DAY[d] for d in Y.days}                 # official daily high / low / close, as the backtest uses
CX = {d: A.context(spec, sess, vol, d, daily) for d in Y.D26}

bad = collections.Counter()
for d in Y.D26:
    cx, lv = CX[d], Y.LV[d]
    bad['cpr'] += abs(cx['lv']['top'] - lv['top']) > 1e-9 or abs(cx['lv']['bot'] - lv['bot']) > 1e-9
    bad['narrow'] += cx['narrow'] != (lv['rank'] < 1 / 3)
    bad['rel'] += cx['rel'] != C.REL[d]
    bad['poc'] += abs(cx['poc'] - Y.PROF30[d]['poc']) > 1e-9
    L = V.LINES[(d, 3)]
    bad['lines'] += len(L) != len(cx['lines']) or any(abs(a - b) > 1e-9 for a, b in zip(L, cx['lines']))
print(f"{Y.B.name.upper()} levels on {len(Y.D26)} days, mismatches: {dict(bad) or 'none'}")

def mine(ladder):
    out = collections.defaultdict(list)
    for d in Y.D26:
        for t in A.day_trades(CX[d], Y.one[d], 929, True, ladder):
            if t['taken']: out[d].append((t['m'], round(t['exit']['pnl'], 6)))
    return out

ref = collections.defaultdict(list)
for t in K.one_book(K.plan_trades() + K.vol_trades(1.5)): ref[t[0]].append((t[2], round(t[1], 6)))
ref_l = collections.defaultdict(list)
for t in I.one_book([x for d in Y.D26 for x in I.plan(d, 'edge', 1.0)] + [x for d in Y.D26 for x in I.vol(d, 'ladder')]):
    ref_l[t['d']].append((t['m'], round(t['pnl'], 6)))
for label, a, b in (('default', mine(False), ref), ('ladder', mine(True), ref_l)):
    diff = [d for d in Y.D26 if sorted(a[d]) != sorted(b[d])]
    n = sum(len(v) for v in a.values()); net = sum(p for v in a.values() for _, p in v)
    print(f"  {label:8} alerts: {n} trades, net {net:+,.0f} | backtest: {sum(len(v) for v in b.values())} trades, "
          f"net {sum(p for v in b.values() for _, p in v):+,.0f} | days that differ: {len(diff)} {diff[:5]}")
    for d in diff[:3]: print(f"     {d} alerts {a[d]} backtest {b[d]}")

changed = 0
for d in Y.D26:
    cx, said = CX[d], {}
    for upto in range(555, 930):
        c1 = [x for x in Y.one[d] if x[0] <= upto]
        for mid, mk, text, push in A.messages(cx, A.day_trades(cx, c1, upto, upto == 929, False), c1, upto, 5):
            if mid in said and said[mid] != text: changed += 1
            said[mid] = text
    full = A.messages(cx, A.day_trades(cx, Y.one[d], 929, True, False), Y.one[d], 929, 5)
    changed += {m: t for m, _, t, _ in full} != said
print(f"  minute by minute: days where something already said changed later: {changed}")

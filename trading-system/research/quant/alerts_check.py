"""Check that alerts/cprb_alerts.py trades exactly like the 2026 backtest (y2026_combo.py / y2026_improve.py for the
classic rules, y2026_volume.py for the classic rules with the volume check, y2026_sweep.py for the classic rules with
liquidity sweeps, y2026_short.py + y2026_reversal.py for the
small-stop rules, y2026_rr.py for the 1:4 rules).

    python alerts_check.py nifty        (or sensex)

1. Levels: CPR, narrow rank, CPR vs yesterday's, 30-day POC and 3-day volume lines match y2026.py for every 2026 day.
2. Trades on whole days: same trades (start minute and points) as the backtest, one book, with and without the ladder.
3. Minute by minute (as it runs live) on every 2026 day: nothing it already said changes later, and at the end of the
   day it has the same trades as on the whole day.
"""
import collections, sys
import y2026 as Y, y2026_combo as K, y2026_improve as I, y2026_vol_lines as V, cpr_orb as C, y2026_short as S, y2026_reversal as RV
import y2026_rr as RR, y2026_smc as M, y2026_sweep as SW
sys.path.insert(0, '../../alerts')
import cprb_alerts as A

spec = A.SPEC[Y.B.name]
sess = {d: Y.one[d] for d in Y.days}
vol = collections.defaultdict(dict)
for k, v in Y.bees.items(): vol[k[:10]][int(k[11:13]) * 60 + int(k[14:16])] = v[4]
daily = {d: Y.DAY[d] for d in Y.days}                 # official daily high / low / close, as the backtest uses
CX = {d: A.context(spec, sess, vol, d, daily) for d in Y.D26}
for d in Y.D26: CX[d]['tvol'] = vol.get(d, {})        # today's NIFTYBEES volume (the volume check reads it minute by minute)

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

def mine(ladder, rules='classic', sweep=False, vcheck=False):
    A.SWEEP, A.VOLCHECK = sweep, vcheck
    out = collections.defaultdict(list)
    for d in Y.D26:
        for t in A.day_trades(CX[d], Y.one[d], 929, True, ladder, rules):
            if t['taken']: out[d].append((t['m'], round(t['exit']['pnl'], 6)))
    return out

ref = collections.defaultdict(list)
for t in K.one_book(K.plan_trades() + K.vol_trades(1.5)): ref[t[0]].append((t[2], round(t[1], 6)))
ref_l = collections.defaultdict(list)
for t in I.one_book([x for d in Y.D26 for x in I.plan(d, 'edge', 1.0)] + [x for d in Y.D26 for x in I.vol(d, 'ladder')]):
    ref_l[t['d']].append((t['m'], round(t['pnl'], 6)))
CAP = spec['cap']
P = (CAP, 'tighten', A.HOLD_MIN, 'target', False)
PB = dict(fam='B', entry='limit', target=f"{A.PULLBACK_R:g}R", hold=A.HOLD_MIN, cap=CAP, mode='tighten')
ref_s = collections.defaultdict(list)
for t in S.one_book([dict(t, src='BO') for d in Y.D26 for t in RV.pullback(d, PB)] + [t for d in Y.D26 for t in (S.magnet(d, P) or [])] +
                    [t for d in Y.D26 for t in S.vol(d, P)]):
    ref_s[t['d']].append((t['m'], round(t['pnl'], 6)))
ref_r = collections.defaultdict(list)
RP = dict(cap=A.STOP_PCT / 100, mode='tighten', target=f"{A.RR_TARGET:g}R", hold=0)
for t in S.one_book([t for d in Y.D26 for f in ('PB', 'MAG') for t in RR.FAMS[f](d, dict(RP, fam=f))]):
    ref_r[t['d']].append((t['m'], round(t['pnl'], 6)))
SWC = [t for d in Y.D26 for t in SW.sweeps(d)]
ref_w = collections.defaultdict(list)
for t in M.one_book(M.BASE_RAW, SWC, A.SWEEP_MAX): ref_w[t['d']].append((t['m'], round(t['pnl'], 6)))
LAD = [dict(d=t['d'], pnl=t['pnl'], m=t['m'], mx=t['mx'], src='plan' if t['src'] in ('MAG', 'BO') else 'vol')
       for t in [x for d in Y.D26 for x in I.plan(d, 'edge', 1.0)] + [x for d in Y.D26 for x in I.vol(d, 'ladder')]]
ref_lw = collections.defaultdict(list)
for t in M.one_book(LAD, SWC, A.SWEEP_MAX): ref_lw[t['d']].append((t['m'], round(t['pnl'], 6)))
import y2026_volume as VV
VC = VV.check(dict(mode='sum', w=A.VOL_WINDOW, k=1.0))
ref_v = collections.defaultdict(list)
A.SWEEP, A.VOLCHECK = False, False
for d in Y.D26:
    CX[d]['vf'] = lambda side, m, src, d=d: VC(d, side, m)
    for t in A.day_trades(CX[d], Y.one[d], 929, True, False, 'classic'):
        if t['taken']: ref_v[d].append((t['m'], round(t['exit']['pnl'], 6)))
    CX[d]['vf'] = None
for label, a, b in (('volume', mine(False, vcheck=True), ref_v), ('classic', mine(False), ref), ('ladder', mine(True), ref_l), ('sweep', mine(False, sweep=True), ref_w),
                    ('ladder+sw', mine(True, sweep=True), ref_lw), ('small', mine(False, 'small'), ref_s),
                    ('rr', mine(False, 'rr'), ref_r)):
    diff = [d for d in Y.D26 if sorted(a[d]) != sorted(b[d])]
    n = sum(len(v) for v in a.values()); net = sum(p for v in a.values() for _, p in v)
    print(f"  {label:8} alerts: {n} trades, net {net:+,.0f} | backtest: {sum(len(v) for v in b.values())} trades, "
          f"net {sum(p for v in b.values() for _, p in v):+,.0f} | days that differ: {len(diff)} {diff[:5]}")
    for d in diff[:3]: print(f"     {d} alerts {a[d]} backtest {b[d]}")

for rules, sweep, vcheck in (('classic', False, True), ('classic', False, False), ('classic', True, False), ('small', False, False), ('rr', False, False)):
    A.SWEEP, A.VOLCHECK = sweep, vcheck
    changed = 0
    for d in Y.D26:
        cx, said = CX[d], {}
        for upto in range(555, 930):
            c1 = [x for x in Y.one[d] if x[0] <= upto]
            for mid, mk, text, push in A.messages(cx, A.day_trades(cx, c1, upto, upto == 929, False, rules), c1, upto, 5):
                if mid in said and said[mid] != text: changed += 1
                said[mid] = text
        full = A.messages(cx, A.day_trades(cx, Y.one[d], 929, True, False, rules), Y.one[d], 929, 5)
        changed += {m: t for m, _, t, _ in full} != said
    print(f"  {rules}{' + sweeps' if sweep else ''}{' + volume check' if vcheck else ''} rules, minute by minute: days where something already said changed later: {changed}")

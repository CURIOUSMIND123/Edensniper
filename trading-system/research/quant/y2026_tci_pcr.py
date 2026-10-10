"""2026 only: would TCI (the Trading Cafe zone breakout) or the put-call ratio (PCR) catch days like 9 October?

    python y2026_tci_pcr.py nifty        (or sensex)

TCI   tci/rules.py on 5-minute candles: zones = yesterday's high / low / close and last-hour high / low, plus the
      15-minute range; a candle closes through a zone, the next candle must break its high (low) -> buy (sell);
      stop at the breakout candle's other end, target the next zone (at least 2x the risk), stop to entry at +1R,
      at most 3 trades / 2 losses a day, 9:25-14:30, out by 15:15. Sensex: point settings x 3.2.
      Also with a 2x wider stop (the setting that helped on his own calls).
PCR   put open interest / call open interest from the exchange's daily F&O file (fetch_pcr.py), known after the
      close, used for the next session: nearest expiry or all expiries, and the ratio of the day's fresh puts to
      fresh calls. Bullish when above `hi`, bearish below `lo`.
      a. Does it say which way the next day goes (close vs open, close vs yesterday's close)?
      b. As a filter on the indicator's trades (drop trades against it).
      c. As the direction for the 9:30 breakout instead of the CPR-vs-yesterday and POC filters.
      d. Its own trade: at 9:20 in its direction, stop 0.3%, trail 1R after +1R, out at 15:15.
Costs 4 Nifty / 12 Sensex points a trade. January-June and July-9 October 2026 separately.
"""
import collections, datetime as dt, json, os, sys
import y2026 as Y, y2026_improve as I, y2026_pivots as PV, cpr_orb as C, cpr_orb_winrate as W
sys.path.insert(0, '../..')
from tci.rules import Bar, Params, run_day

one, five, LV, DAY, COST, D26, H1 = Y.one, Y.five, Y.LV, Y.DAY, Y.COST, Y.D26, Y.H1
NM = Y.B.name
K = 1.0 if NM == 'nifty' else 3.2

def bars(d):
    y, m, dd = map(int, d.split('-'))
    return [Bar(dt.datetime(y, m, dd, x[0] // 60, x[0] % 60), *x[1:]) for x in five[d]]

def tci_day(d, stop_mult=1.0):
    p = Params(zone_merge_pts=10 * K, trigger_buffer=1 * K, stop_buffer=1 * K, min_risk_pts=6 * K, max_risk_pts=35 * K, stop_mult=stop_mult)
    s = run_day(bars(Y.days[Y.IDX[d] - 1]), bars(d), p)
    return [dict(d=d, src='TCI', side=1 if t.side == 'CE' else -1, m=t.opened.hour * 60 + t.opened.minute,
                 mx=t.closed.hour * 60 + t.closed.minute + 4, pnl=t.points - COST) for t in s.trades]

def book(ts, order):
    out = []; free = collections.defaultdict(int)
    for t in sorted(ts, key=lambda t: (t['d'], t['m'], order[t['src']])):
        if t['m'] >= free[t['d']]: out.append(t); free[t['d']] = t['mx'] + 1
    return out

ORDER = {'MAG': 0, 'BO': 0, 'VOL': 1, 'TCI': 2, 'PCR': 2}
PLAN = {d: PV.plan(d) for d in D26}
VOL = {d: I.vol(d, 'fixed') for d in D26}
NOW = book([t for d in D26 for t in PLAN[d] + VOL[d]], ORDER)

# ---------------- PCR ----------------
PCR = json.load(open(f'../.cache/pcr_{NM}.json')) if os.path.exists(f'../.cache/pcr_{NM}.json') else {}

def prev(d): return Y.days[Y.IDX[d] - 1]

def bias(d, kind, hi, lo):
    r = PCR.get(prev(d))
    if not r or r.get(kind) is None: return None
    v = r[kind]
    return 1 if v > hi else -1 if v < lo else 0

def pcr_breakout(d, kind, hi, lo):
    """The 9:30 breakout with the PCR direction in place of the gap, CPR-vs-yesterday and POC filters."""
    b = bias(d, kind, hi, lo)
    if not b: return []
    first = [x for x in one[d] if x[0] < 570]; orh, orl = max(x[2] for x in first), min(x[3] for x in first)
    for side, e, start, m in C.candidates(d, 'touch', orh, orl, 570):
        if m >= 600: break
        if side != b: continue
        stp = orl if side > 0 else orh; R = side * (e - stp)
        if R <= 0: continue
        pnl, mx = I.walk(d, side, e, start, stp, e + side * 0.25 * R, None, 1.0)
        return [dict(d=d, src='BO', side=side, m=m, mx=mx, pnl=pnl)]
    return []

def pcr_trade(d, kind, hi, lo):
    b = bias(d, kind, hi, lo)
    if not b: return []
    x = [c for c in one[d] if c[0] == 559]
    if not x: return []
    e = x[0][4]; R = 0.003 * e
    pnl, mx = I.walk(d, b, e, 560, e - b * R, e + b * 0.25 * R, None, 1.0)
    return [dict(d=d, src='PCR', side=b, m=560, mx=mx, pnl=pnl)]

if __name__ == '__main__':
    print(f"{NM.upper()} 2026 ({len(D26)} sessions)")
    PV.show('indicator now', NOW)
    for sm in (1.0, 2.0):
        T = {d: tci_day(d, sm) for d in D26}
        PV.show(f'TCI alone (stop x{sm:g})', [t for d in D26 for t in T[d]])
        PV.show(f'indicator + TCI (stop x{sm:g}), one book', book([t for d in D26 for t in PLAN[d] + VOL[d] + T[d]], ORDER))
        print(f"     TCI on the last 7 sessions: {[round(sum(t['pnl'] for t in T[d])) for d in D26[-7:]]}")
    if not PCR:
        print("no PCR data yet: run fetch_pcr.py"); sys.exit()
    days = [d for d in D26 if prev(d) in PCR]
    print(f"\nPCR on {len(days)} days. Last 8 days' values (for the next session):")
    for d in Y.days[-8:]:
        r = PCR.get(d)
        if r: print(f"  {d}: nearest expiry {r['pcr_near']:.2f}, all expiries {r['pcr_all']:.2f}, fresh puts / calls "
                    f"{r['chg_near'] if r['chg_near'] is None else round(r['chg_near'], 2)}, most call OI {r['ce_max']:,.0f}, most put OI {r['pe_max']:,.0f}")
    print(" a. does it say which way the next day goes?")
    for kind in ('pcr_near', 'pcr_all', 'chg_near'):
        vals = sorted(PCR[prev(d)][kind] for d in days if PCR[prev(d)][kind] is not None)
        med = vals[len(vals) // 2]
        for hi, lo in ((med, med), (vals[len(vals) * 2 // 3], vals[len(vals) // 3])):
            n = right = right2 = 0
            for d in days:
                b = bias(d, kind, hi, lo)
                if not b: continue
                n += 1; right += b * (DAY[d][3] - DAY[d][0]) > 0; right2 += b * (DAY[d][3] - DAY[prev(d)][3]) > 0
            print(f"   {kind:8} bullish above {hi:.2f} / bearish below {lo:.2f}: {n:3} days, right about close vs open "
                  f"{100 * right / max(1, n):3.0f}%, close vs yesterday's close {100 * right2 / max(1, n):3.0f}%")
    print(" b-d. trading it (thresholds: bullish above the upper third, bearish below the lower third; and the median)")
    for kind in ('pcr_near', 'pcr_all', 'chg_near'):
        vals = sorted(PCR[prev(d)][kind] for d in days if PCR[prev(d)][kind] is not None)
        for hi, lo, lab in ((vals[len(vals) * 2 // 3], vals[len(vals) // 3], 'thirds'), (vals[len(vals) // 2], vals[len(vals) // 2], 'median')):
            keep = [t for t in NOW if bias(t['d'], kind, hi, lo) != -t['side']]
            PV.show(f"{kind} {lab}: indicator, trades against PCR dropped", keep)
            PV.show(f"{kind} {lab}: breakout in the PCR direction (no other filter)", [t for d in D26 for t in pcr_breakout(d, kind, hi, lo)])
            PV.show(f"{kind} {lab}: 9:20 trade in the PCR direction", [t for d in D26 for t in pcr_trade(d, kind, hi, lo)])
    print(" 9 October: PCR the evening before ->", {k: (round(v, 2) if isinstance(v, float) else v) for k, v in PCR.get(prev(D26[-1]), {}).items()})

"""CPR Magnet over the last N sessions, day by day: why there was or wasn't a trade, and how each trade ended.

    python cpr_magnet_lastn.py nifty 30        (index, number of sessions)

Same rules as cpr_magnet_check.py and tradingview/cpr_magnet.pine. Points are index points, before and after
costs (4 Nifty / 12 Sensex points a trade).
"""
import sys
N = int(sys.argv[2]) if len(sys.argv) > 2 else 30
sys.argv = sys.argv[:2]
import cpr_backtest as B

GAP, STOP = 0.2, 0.3
days = B.TEST[-N:]
rows = []
print(f"{B.name.upper()}, last {N} sessions: {days[0]} to {days[-1]}")
for d in days:
    lv = B.LV[d]; o, e = B.one[d][0][1], B.one[d][0][4]
    cpr = f"CPR {lv['bot']:,.1f}-{lv['top']:,.1f}"
    if lv['rank'] < 1 / 3:
        print(f"  {d}  {cpr}  no trade: narrow CPR"); continue
    side = -1 if o > lv['top'] else 1 if o < lv['bot'] else 0
    edge = lv['top'] if side < 0 else lv['bot']
    if not side or side * (edge - e) < GAP / 100 * e:
        print(f"  {d}  {cpr}  no trade: 9:15 candle opened {o:,.1f}, closed {e:,.1f}, not 0.2% beyond the CPR"); continue
    stp = e - side * STOP / 100 * e
    pnl, m = B.sim(d, side, 556, e, stp, edge)
    gross = pnl + B.COST; ex = e + side * gross
    why = 'STOP' if abs(ex - stp) < 1e-6 else 'TARGET' if abs(ex - edge) < 1e-6 else '3:15 exit'
    rows.append((gross, pnl))
    print(f"  {d}  {cpr}  {'SELL' if side < 0 else 'BUY '} at {e:,.1f}, target {edge:,.1f}, stop {stp:,.1f} -> {why} {m//60}:{m%60:02d}, "
          f"{gross:+.1f} pts ({pnl:+.1f} after costs)")
won = [r for r in rows if r[1] > 0]; lost = [r for r in rows if r[1] <= 0]
print(f"  trades {len(rows)}: won {len(won)}, lost {len(lost)}")
for i, lab in ((0, 'before costs'), (1, 'after costs')):
    print(f"  {lab}: points won {sum(r[i] for r in won):+,.1f}, points lost {sum(r[i] for r in lost):+,.1f}, net {sum(r[i] for r in rows):+,.1f}")

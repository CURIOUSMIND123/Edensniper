"""The chosen CPR Breakout version over the last N sessions, trade by trade (same rules as tradingview/cpr_breakout.pine).

    python cpr_orb_lastn.py nifty 90        (index, number of sessions)

Narrow-CPR days only. No sells when today's CPR sits wholly above yesterday's (higher value), no buys when wholly
below. Buy / sell when price touches the first 15-minute candle's high / low (9:30-13:00). Stop at the other side of
that range; once +1R, the stop trails 1R behind the best price; out by 15:15. If the first trade loses, take the
break of the other side once.
"""
import sys, statistics as st
N = int(sys.argv[2]) if len(sys.argv) > 2 else 90
sys.argv = sys.argv[:2]
import cpr_orb as C

P = ('none', 'none', 'none', 'notagainst', 'narrow', 'touch', 'range', 'trail', 'yes')
days = C.TEST[-N:]
ts = []
print(f"{C.B.name.upper()}, last {N} sessions: {days[0]} to {days[-1]}; narrow-CPR days: {sum(C.LV[d]['rank'] < 1/3 for d in days)}")
for d in days:
    for t in C.day(d, P):
        ts.append(t)
        print(f"  {t[0]}  {'BUY ' if t[2] > 0 else 'SELL'}  risk {t[3]:6.1f}  result {t[1]:+7.1f} pts after costs")
won = [t[1] for t in ts if t[1] > 0]; lost = [t[1] for t in ts if t[1] <= 0]
print(f"  trades {len(ts)}: won {len(won)}, lost {len(lost)}; points won {sum(won):+,.1f}, points lost {sum(lost):+,.1f}, net {sum(won) + sum(lost):+,.1f}")
if ts: print(f"  average risk (entry to stop) {st.mean(t[3] for t in ts):.0f} pts; average win {st.mean(won) if won else 0:+.0f}, average loss {st.mean(lost) if lost else 0:+.0f}")

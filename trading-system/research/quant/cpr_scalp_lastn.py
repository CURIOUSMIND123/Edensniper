"""The high-win-rate CPR Breakout scalp, trade by trade over the last N sessions.

    python cpr_scalp_lastn.py nifty 90        (index, number of sessions)

Narrow-CPR days only; trade only in the direction of the opening gap (open vs yesterday's close); no trade against
today's CPR vs yesterday's. Buy / sell on a touch of the first 15-minute candle's high / low (9:30-13:00), stop at
the other side of that range. Book half at 0.25 x the risk, move the stop to entry, trail the rest 1R behind the
best price after +1R; out by 15:15. One reversal trade after a loss. Same rules as the "Scalp" exit in
tradingview/cpr_breakout.pine with "Only in the direction of the opening gap" on.
"""
import sys
N = int(sys.argv[2]) if len(sys.argv) > 2 else 90
sys.argv = sys.argv[:2]
import cpr_orb_winrate as W

days = W.TEST[-N:]
ts = [t for d in days for t in W.day(d, 'narrow', ('half', 0.25), True, ('gap',))]
for d, p in ts: print(f"  {d}  {p:+7.1f} pts after costs")
won = [p for _, p in ts if p > 0]; lost = [p for _, p in ts if p <= 0]
print(f"{W.B.name.upper()} last {N} sessions ({days[0]} to {days[-1]}): {len(ts)} trades, won {len(won)}, lost {len(lost)}; "
      f"points won {sum(won):+,.1f}, points lost {sum(lost):+,.1f}, net {sum(won) + sum(lost):+,.1f}")

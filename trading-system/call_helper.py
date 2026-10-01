"""Follow a live call (his, or your own) with a wider stop, and size it.

All prices are OPTION premiums, so the same command works for a call (CE) or a put (PE):

    python call_helper.py --index NIFTY --entry 172 --sl 160 --target 200 --capital 100000
    python call_helper.py --index SENSEX --entry 300 --sl 275 --target 360 --mult 2

Why: on his 80 checkable calls (Aug-Oct 2026), keeping his entry and first target but
using twice his stop distance turned a ~40% win rate into ~60%. That's one sample, so
treat it as something to paper-test, not a guarantee (see README).
"""
import argparse
import math

LOTS = {"NIFTY": 65, "SENSEX": 20}
CHARGES = {"NIFTY": 65.0, "SENSEX": 58.0}  # approx. round-trip charges per lot at ~Rs 150 / ~Rs 300 premium


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--index", choices=list(LOTS), default="NIFTY")
    ap.add_argument("--entry", type=float, required=True, help="option entry price he gave")
    ap.add_argument("--sl", type=float, required=True, help="his stop-loss price on the option")
    ap.add_argument("--target", type=float, help="his first target on the option")
    ap.add_argument("--mult", type=float, default=2.0, help="your stop = this many times his stop distance")
    ap.add_argument("--capital", type=float, default=100000)
    ap.add_argument("--risk-pct", type=float, default=1.0)
    ap.add_argument("--slippage", type=float, default=1.0, help="points lost on each fill")
    a = ap.parse_args()

    lot = LOTS[a.index]
    his = a.entry - a.sl
    if his <= 0:
        raise SystemExit("stop must be below entry (you are buying the option)")
    dist = a.mult * his
    stop = max(0.05, a.entry - dist)
    per_lot = (dist + 2 * a.slippage) * lot + CHARGES[a.index]
    budget = a.capital * a.risk_pct / 100
    lots = math.floor(budget / per_lot)

    print(f"{a.index} option bought at {a.entry:g}")
    print(f"  his stop  {a.sl:g}  ({his:g} pts)")
    print(f"  YOUR STOP {stop:.2f}  ({dist:g} pts = {a.mult:g} x his)")
    if a.target:
        rew = a.target - a.entry
        print(f"  first target {a.target:g}  (+{rew:g} pts): reward/risk {rew / his:.1f} with his stop, {rew / dist:.1f} with yours")
    print(f"  move your stop to {a.entry:g} (break-even) once the option trades at {a.entry + his:g} (entry + his stop distance)")
    print(f"  loss if your stop hits: about Rs {per_lot:,.0f} per lot (incl. charges and slippage)")
    print(f"  your budget at {a.risk_pct:g}% of Rs {a.capital:,.0f} = Rs {budget:,.0f} -> {lots} lot(s)")
    if lots == 0:
        print("  SKIP: one lot risks more than your budget. Don't shrink the stop to make it fit;"
              " that's the stop that got hit 60% of the time.")


if __name__ == "__main__":
    main()

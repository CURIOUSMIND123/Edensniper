"""Option-chain numbers for the TCI All-in-One indicator's "smart money" inputs.

    python smart_money.py                 # NIFTY, nearest weekly expiry
    python smart_money.py --underlying SENSEX

Prints PCR, the CALL and PUT OI walls and max pain from Groww's option chain. Type them into the
indicator's "Smart money context" settings each morning (and again after lunch if you like).
Without the Groww API you can read the same numbers off the option-chain screen in the Groww app:
PCR = total put OI / total call OI; call wall = strike with the most call OI; put wall = most put OI.
"""
import argparse
from datetime import datetime, timedelta

from tci.groww_client import GrowwClient, login


def analyse(chain: dict, spot: float, step: int, near: int = 10) -> dict:
    rows = []
    for k_str, legs in (chain.get("strikes") or {}).items():
        ce, pe = legs.get("CE") or {}, legs.get("PE") or {}
        rows.append((float(k_str), float(ce.get("open_interest") or 0), float(pe.get("open_interest") or 0)))
    rows.sort()
    if not rows:
        raise SystemExit("empty option chain")
    tot_ce = sum(r[1] for r in rows)
    tot_pe = sum(r[2] for r in rows)
    atm = round(spot / step) * step
    near_rows = [r for r in rows if abs(r[0] - atm) <= near * step]
    n_ce = sum(r[1] for r in near_rows)
    n_pe = sum(r[2] for r in near_rows)
    above = [r for r in rows if r[0] >= atm] or rows
    below = [r for r in rows if r[0] <= atm] or rows
    ce_wall = max(above, key=lambda r: r[1])[0]
    pe_wall = max(below, key=lambda r: r[2])[0]
    pain = min(rows, key=lambda x: sum(r[1] * max(0.0, x[0] - r[0]) + r[2] * max(0.0, r[0] - x[0]) for r in rows))[0]
    return {"spot": spot, "pcr": tot_pe / tot_ce if tot_ce else 0.0, "pcr_near_atm": n_pe / n_ce if n_ce else 0.0,
            "ce_wall": ce_wall, "pe_wall": pe_wall, "max_pain": pain}


def reading(pcr: float) -> str:
    if pcr >= 1.7:
        return "very high: heavy put writing, market may be stretched up"
    if pcr >= 1.3:
        return "high: put writers active, supports the downside"
    if pcr <= 0.5:
        return "very low: heavy call writing, market may be stretched down"
    if pcr <= 0.7:
        return "low: call writers active, caps the upside"
    return "neutral"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--underlying", default="NIFTY", choices=["NIFTY", "SENSEX"])
    a = ap.parse_args()
    client = GrowwClient(login(), a.underlying)
    now = datetime.utcnow() + timedelta(hours=5, minutes=30)
    expiry = client.nearest_expiry(now.date())
    chain = client.g.get_option_chain(exchange=client.exchange, underlying=client.underlying, expiry_date=expiry)
    spot = float(chain.get("underlying_ltp") or client.index_ltp())
    r = analyse(chain, spot, client.step)
    print(f"{a.underlying} {spot:,.1f} | expiry {expiry} | {now:%H:%M} IST")
    print(f"  PCR (all strikes)      {r['pcr']:.2f}  -> {reading(r['pcr'])}")
    print(f"  PCR (near the money)   {r['pcr_near_atm']:.2f}")
    print(f"  CALL OI wall           {r['ce_wall']:,.0f}  (resistance, {r['ce_wall'] - spot:+,.0f} pts)")
    print(f"  PUT OI wall            {r['pe_wall']:,.0f}  (support, {r['pe_wall'] - spot:+,.0f} pts)")
    print(f"  Max pain               {r['max_pain']:,.0f}")
    print(f"\nType into the indicator: PCR {r['pcr']:.2f} | CALL OI wall {r['ce_wall']:.0f} | PUT OI wall {r['pe_wall']:.0f}")


if __name__ == "__main__":
    main()

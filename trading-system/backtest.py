"""Backtest the rules on Groww's historical data, with REAL option prices.

    python backtest.py --start 2025-10-01 --end 2026-09-30

Index candles drive the rules exactly as in live trading. For every trade, the
option bought is the first strike (from at-the-money, moving in-the-money) whose
premium is at least the target premium, and its own 1-minute candles price the entry and
exit. Downloads are cached in data/cache so re-runs are fast.

The report includes a "random direction" baseline: the same entry times, stops and
targets with a coin-flip side. If the rules don't beat that, their signals add nothing.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import statistics
import time as _time
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from live import load_config, params_from
from tci import costs
from tci.rules import Bar, bar_path, run_day

CACHE = os.path.join("data", "cache")


class GrowwData:
    def __init__(self, client):
        self.c = client
        os.makedirs(CACHE, exist_ok=True)

    def _cached(self, key: str, fetch):
        p = os.path.join(CACHE, key.replace("/", "_") + ".json")
        if os.path.exists(p):
            return json.load(open(p))
        data = fetch()
        json.dump(data, open(p, "w"))
        _time.sleep(0.12)  # stay well inside Groww's rate limits
        return data

    def bars(self, groww_symbol: str, segment: str, start: date, end: date, minutes: int) -> List[Bar]:
        out: List[Bar] = []
        d = start
        while d <= end:  # Groww allows 30 days per request for 1-5 minute candles
            e = min(end, d + timedelta(days=29))
            key = f"{groww_symbol}_{minutes}_{d}_{e}"
            rows = self._cached(key, lambda: [[b.t.isoformat(), b.o, b.h, b.l, b.c] for b in self.c.candles(
                groww_symbol, segment, datetime.combine(d, datetime.min.time()).replace(hour=9, minute=15),
                datetime.combine(e, datetime.min.time()).replace(hour=15, minute=30), minutes)])
            out += [Bar(datetime.fromisoformat(r[0]), *r[1:]) for r in rows]
            d = e + timedelta(days=1)
        return out

    def expiries(self, y: int, m: int) -> List[str]:
        return self._cached(f"exp_{self.c.underlying}_{y}_{m}", lambda: self.c.g.get_expiries(
            exchange=self.c.exchange, underlying_symbol=self.c.underlying, year=y, month=m).get("expiries", []))

    def contracts(self, expiry: str) -> List[str]:
        return self._cached(f"con_{self.c.underlying}_{expiry}", lambda: self.c.g.get_contracts(
            exchange=self.c.exchange, underlying_symbol=self.c.underlying, expiry_date=expiry).get("contracts", []))

    def option_minutes(self, groww_symbol: str, day: date) -> Dict[str, List[float]]:
        bars = self.bars(groww_symbol, self.c.g.SEGMENT_FNO, day, day, 1)
        return {b.t.strftime("%H:%M"): [b.o, b.h, b.l, b.c] for b in bars}


def nearest_expiry(data: GrowwData, day: date) -> Optional[str]:
    nxt = day + timedelta(days=32)
    ex = sorted(set(data.expiries(day.year, day.month) + data.expiries(nxt.year, nxt.month)))
    return next((e for e in ex if e >= day.isoformat()), None)


def strike_symbol(contracts: List[str], strike: float, side: str) -> Optional[str]:
    k = str(int(strike))
    return next((c for c in contracts if c.endswith(f"-{k}-{side}")), None)


def minute_of(idx1: List[Bar], start: datetime, end: datetime, level: float, up: bool) -> datetime:
    """First 1-minute candle inside [start, end) that reaches `level`; falls back to `start`."""
    for b in idx1:
        if start <= b.t < end and ((b.h >= level) if up else (b.l <= level)):
            return b.t
    return start


def price_at(opt: Dict[str, List[float]], t: datetime) -> Optional[float]:
    for k in range(0, 6):  # this minute or up to 5 minutes later if the strike didn't trade
        key = (t + timedelta(minutes=k)).strftime("%H:%M")
        if key in opt:
            return opt[key][3]
    return None


def main() -> None:
    from tci.groww_client import GrowwClient, login

    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--slippage", type=float, default=1.0, help="option points lost on each fill")
    ap.add_argument("--out", default="backtest_trades.csv")
    a = ap.parse_args()
    cfg = load_config(a.config)
    tf, lot = cfg["timeframe_min"], cfg["risk"]["lot_size"]
    client = GrowwClient(login(), cfg["underlying"])
    data = GrowwData(client)
    start, end = date.fromisoformat(a.start), date.fromisoformat(a.end)
    seg = client.g.SEGMENT_CASH
    idx = data.bars(client.index_groww_symbol, seg, start - timedelta(days=7), end, tf)
    idx1 = data.bars(client.index_groww_symbol, seg, start, end, 1)
    by_day: Dict[str, List[Bar]] = {}
    for b in idx:
        by_day.setdefault(b.t.date().isoformat(), []).append(b)
    one: Dict[str, List[Bar]] = {}
    for b in idx1:
        one.setdefault(b.t.date().isoformat(), []).append(b)
    days = sorted(by_day)
    rows = []
    for i, d in enumerate(days[1:], 1):
        if d < a.start:
            continue
        s = run_day(by_day[days[i - 1]], by_day[d], params_from(cfg))
        if not s.trades:
            continue
        day = date.fromisoformat(d)
        expiry = nearest_expiry(data, day)
        con = data.contracts(expiry) if expiry else []
        for tr in s.trades:
            bar_end = tr.opened + timedelta(minutes=tf)
            t_in = minute_of(one.get(d, []), tr.opened, bar_end, tr.entry, tr.side == "CE")
            t_out = tr.closed if tr.reason == "square-off" else minute_of(
                one.get(d, []), tr.closed, tr.closed + timedelta(minutes=tf), tr.exit,
                (tr.side == "CE") == (tr.reason == "target"))
            step = client.step
            atm = round(tr.entry / step) * step
            pick = None
            for j in range(0, 7):  # walk from ATM into the money until premium >= target
                k = atm - j * step if tr.side == "CE" else atm + j * step
                sym = strike_symbol(con, k, tr.side)
                if not sym:
                    continue
                opt = data.option_minutes(sym, day)
                p_in = price_at(opt, t_in)
                if p_in and (p_in >= cfg["target_premium"] or j == 6):
                    pick = (sym, opt, p_in)
                    break
            if not pick:
                continue
            sym, opt, p_in = pick
            p_out = price_at(opt, t_out) or p_in
            buy, sell = p_in + a.slippage, max(0.05, p_out - a.slippage)
            gross = (sell - buy) * lot
            ch = costs.round_trip(buy * lot, sell * lot, client.exchange)
            rows.append(dict(day=d, side=tr.side, zone=tr.zone, entry_time=t_in.strftime("%H:%M"), exit_time=t_out.strftime("%H:%M"),
                             reason=tr.reason, index_entry=round(tr.entry, 1), index_stop=round(tr.initial_stop, 1),
                             index_target=round(tr.target, 1), index_exit=round(tr.exit, 1), index_R=round(tr.r, 2),
                             option=sym, opt_buy=round(buy, 2), opt_sell=round(sell, 2), gross=round(gross), charges=ch,
                             net=round(gross - ch)))
    if not rows:
        print("no trades")
        return
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    report(rows, by_day, tf)
    print(f"trades written to {a.out}")


def report(rows: List[dict], by_day: Dict[str, List[Bar]], tf: int) -> None:
    net = [r["net"] for r in rows]
    cum, peak, dd = 0.0, 0.0, 0.0
    for x in net:
        cum += x
        peak = max(peak, cum)
        dd = min(dd, cum - peak)
    ir = [r["index_R"] for r in rows]
    print(f"trades {len(rows)} on {len({r['day'] for r in rows})} days | win% {100 * sum(n > 0 for n in net) / len(net):.0f} "
          f"| net Rs {sum(net):+,.0f} per lot | avg {statistics.mean(net):+.0f}/trade | worst drawdown Rs {dd:,.0f}")
    print("exits:", {k: sum(1 for r in rows if r["reason"] == k) for k in sorted({r["reason"] for r in rows})})
    real = statistics.mean(ir)
    base = random_baseline(rows, by_day, tf)
    beat = 100 * sum(b >= real for b in base) / len(base)
    print(f"signal check: rules average {real:+.2f}R in index terms; random direction averages {statistics.mean(base):+.2f}R; "
          f"{beat:.0f}% of random runs did at least as well (below 5% would suggest a real edge)")


def random_baseline(rows: List[dict], by_day: Dict[str, List[Bar]], tf: int, runs: int = 500) -> List[float]:
    rng = random.Random(7)
    res = []
    for _ in range(runs):
        tot = []
        for r in rows:
            bars = by_day[r["day"]]
            t0 = datetime.fromisoformat(f"{r['day']}T{r['entry_time']}")
            e = r["index_entry"]
            risk, rew = abs(e - r["index_stop"]), abs(r["index_target"] - e)
            sgn = rng.choice((1, -1))
            stop, tgt, out = e - sgn * risk, e + sgn * rew, None
            for b in bars:
                if b.t + timedelta(minutes=tf) <= t0:
                    continue
                for px in bar_path(b):
                    if sgn * (px - stop) <= 0:
                        out = stop
                        break
                    if sgn * (px - tgt) >= 0:
                        out = tgt
                        break
                if out is not None:
                    break
                if sgn * ((b.h if sgn > 0 else b.l) - e) >= risk:
                    stop = e
                if b.t.time() >= datetime.strptime("15:10", "%H:%M").time():
                    out = b.c
                    break
            tot.append(sgn * ((out if out is not None else bars[-1].c) - e) / risk)
        res.append(statistics.mean(tot))
    return res


if __name__ == "__main__":
    main()

"""Re-run the Fair Price test on Nifty / Sensex 1-minute data from Upstox's public candle API.

    python research/fair_price_backtest.py                 # tested version, Nifty and Sensex, 2023 to today
    python research/fair_price_backtest.py --rules his     # his rules as given (opening candle + BOS, 20 / 30)

Candles are cached in research/.cache/ (about 25 MB per index). Results are in R: one R is the stop
distance, and every trade pays a cost of 4 Nifty points or 12 Sensex points (an option round trip at
delta 0.5, charges plus spread).
"""
import argparse
import calendar
import collections
import datetime as dt
import json
import os
import statistics as st
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tci.fairprice import FPParams, run_day, tested_params, usual_range  # noqa: E402
from tci.rules import Bar  # noqa: E402

KEYS = {"nifty": "NSE_INDEX|Nifty 50", "sensex": "BSE_INDEX|SENSEX"}
COST = {"nifty": 4.0, "sensex": 12.0}
CACHE = os.path.join(os.path.dirname(__file__), ".cache")


def fetch(name, start, end):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"{name}_1m.json")
    out = json.load(open(path)) if os.path.exists(path) else {}
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        a = dt.date(y, m, 1)
        b = min(dt.date(y, m, calendar.monthrange(y, m)[1]), end)
        if not any(k.startswith(a.strftime("%Y-%m")) for k in out) or b >= end - dt.timedelta(days=31):
            url = (f"https://api.upstox.com/v3/historical-candle/{urllib.parse.quote(KEYS[name], safe='')}"
                   f"/minutes/1/{b}/{a}")
            req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "curl/8.5.0"})
            for k in range(5):
                try:
                    rows = json.load(urllib.request.urlopen(req, timeout=60))["data"]["candles"]
                    break
                except Exception as e:  # network hiccup: back off and retry
                    print("retry", name, a, e)
                    time.sleep(2 ** (k + 1))
            else:
                rows = []
            for r in rows:
                out[r[0][:16].replace("T", " ")] = r[1:5]
            time.sleep(0.4)
        m += 1
        if m == 13:
            y, m = y + 1, 1
    json.dump(out, open(path, "w"))
    return out


def days(raw):
    by = collections.defaultdict(list)
    for k in sorted(raw):
        t = dt.datetime.strptime(k, "%Y-%m-%d %H:%M")
        if dt.time(9, 15) <= t.time() < dt.time(15, 30):
            by[k[:10]].append(Bar(t, *raw[k]))
    return [(d, by[d]) for d in sorted(by) if len(by[d]) >= 300]   # skip special short sessions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rules", choices=["tested", "his"], default="tested")
    ap.add_argument("--start", default="2023-01-01")
    ap.add_argument("--end", default=dt.date.today().isoformat())
    a = ap.parse_args()
    start, end = dt.date.fromisoformat(a.start), dt.date.fromisoformat(a.end)
    for name in KEYS:
        ds = days(fetch(name, start, end))
        ranges, prev, per_year, all_r = [], None, collections.defaultdict(list), []
        for d, bars in ds:
            rng = usual_range(ranges)
            if rng is not None and len(ranges) >= 10 and prev:
                if a.rules == "tested":
                    p = tested_params(rng)
                else:
                    sl = 20.0 if name == "nifty" else 60.0
                    p = FPParams(sl=sl, tp=1.5 * sl, big_open=sl, use_displacement=False, max_losses=2)
                for t in run_day([prev[0]], bars, p).trades:
                    r = (t.points - COST[name]) / t.risk0
                    per_year[d[:4]].append(r)
                    all_r.append(r)
            am = [b for b in bars if b.t.time() < dt.time(10, 45)]
            ranges.append(max(b.h for b in am) - min(b.l for b in am))
            prev = bars
        print(f"{name}: {len(all_r)} trades in {len(ds)} days, won {100 * sum(r > 0 for r in all_r) / max(1, len(all_r)):.0f}%, "
              f"total {sum(all_r):+.1f}R, average {st.mean(all_r) if all_r else 0:+.3f}R per trade")
        for y in sorted(per_year):
            rs = per_year[y]
            print(f"   {y}: {len(rs):4d} trades  {sum(rs):+7.1f}R  won {100 * sum(r > 0 for r in rs) / len(rs):.0f}%")


if __name__ == "__main__":
    main()

"""Run the TCI zone-breakout system for today's session.

Paper trading (default, no real orders):
    python live.py
Real orders (only after the paper gate is passed, see README):
    TCI_LIVE_CONFIRM=YES python live.py --mode live
Offline logic check on a saved day of index candles (no Groww account needed):
    python live.py --replay data/2026-09-15.csv --prev data/2026-09-14.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time as _time
from datetime import date, datetime, time, timedelta

from tci.journal import Journal
from tci.risk import RiskConfig, RiskManager
from tci.rules import Bar, Params, Strategy, bar_path
from tci.session import GrowwBroker, PaperBroker, Session, warm_up

DEFAULTS = {
    "underlying": "NIFTY",
    "timeframe_min": 5,
    "target_premium": 150,
    "paper_slippage": 1.0,
    "poll_seconds": 1.0,
    "protect_mult": 2.0,
    "journal_dir": "journal",
    "risk": {"capital": 50000, "risk_per_trade_pct": 1.0, "max_daily_loss_pct": 2.0, "max_lots": 1, "lot_size": 65},
    "rules": {},
    "go_live_gate": {"min_paper_trades": 40, "min_paper_days": 20},
}


def load_config(path: str) -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))
    if path and os.path.exists(path):
        user = json.load(open(path))
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    return cfg


def params_from(cfg: dict) -> Params:
    p = Params(timeframe_min=cfg["timeframe_min"])
    for k, v in cfg["rules"].items():
        cur = getattr(p, k)
        setattr(p, k, time.fromisoformat(v) if isinstance(cur, time) else type(cur)(v))
    return p


def ist_now() -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)
    except Exception:
        return datetime.utcnow() + timedelta(hours=5, minutes=30)


def log_to(path: str):
    def log(msg: str) -> None:
        print(msg, flush=True)
        with open(path, "a") as f:
            f.write(msg + "\n")
    return log


def check_gate(journal: Journal, cfg: dict, skip: bool) -> None:
    st = journal.stats("paper")
    g = cfg["go_live_gate"]
    print(f"Paper record so far: {st}")
    if os.getenv("TCI_LIVE_CONFIRM") != "YES":
        sys.exit("Live mode needs TCI_LIVE_CONFIRM=YES in the environment.")
    if skip:
        print("WARNING: paper gate skipped by --skip-gate.")
        return
    if st["trades"] < g["min_paper_trades"] or st["days"] < g["min_paper_days"] or st["avg"] <= 0:
        sys.exit(f"Paper gate not passed: need >= {g['min_paper_trades']} paper trades over >= {g['min_paper_days']} "
                 f"days with positive average net P&L after costs. Keep paper trading.")


# ---------------------------------------------------------------- live / paper
def run_live(args, cfg) -> None:
    from tci.groww_client import GrowwClient, login

    tf = cfg["timeframe_min"]
    journal = Journal(cfg["journal_dir"])
    if args.mode == "live":
        check_gate(journal, cfg, args.skip_gate)
    client = GrowwClient(login(), cfg["underlying"])
    today = ist_now().date()
    prev_day, prev_bars = client.previous_session(today, tf)
    strat = Strategy(prev_bars, params_from(cfg))
    risk = RiskManager(RiskConfig(**cfg["risk"]))
    expiry = client.nearest_expiry(today)
    os.makedirs("logs", exist_ok=True)
    log = log_to(f"logs/{today}.log")
    log(f"{ist_now():%H:%M:%S} start {args.mode.upper()} | {cfg['underlying']} {tf}-min | prev session {prev_day} | "
        f"expiry {expiry} | zones: " + ", ".join(f"{z.name} {z.level:.0f}" for z in strat.zones))
    if args.mode == "live":
        if client.open_fno_positions():
            sys.exit("You already have open F&O positions. Close them or run in paper mode.")
        broker = GrowwBroker(client)
    else:
        broker = PaperBroker(client.option_ltp, cfg["paper_slippage"])
    sess = Session(today.isoformat(), strat, broker, risk, journal, args.mode,
                   pick_option=lambda side, spot: client.pick_option(side, spot, expiry, cfg["target_premium"]),
                   option_quote=client.option_ltp, exchange=client.exchange, protect_mult=cfg["protect_mult"], log=log)

    open_t = datetime.combine(today, time(9, 15))
    while ist_now() < open_t:
        _time.sleep(5)
    now = ist_now()
    done = [b for b in client.index_candles(today, tf, until=now) if b.t + timedelta(minutes=tf) <= now]
    if done:
        warm_up(strat, done)
        log(f"{now:%H:%M:%S} caught up on {len(done)} finished candles; trades so far today: {len(strat.trades)}")
    last_bar = done[-1].t if done else None
    sess.show_plan(done[-1].c if done else client.index_ltp(), now)
    errors = 0
    while True:
        now = ist_now()
        if now.time() >= time(15, 20):
            sess.end_of_day(now, client.index_ltp())
            break
        try:
            sess.on_tick(now, client.index_ltp())
            due = (last_bar + timedelta(minutes=2 * tf) if last_bar else open_t + timedelta(minutes=tf)) + timedelta(seconds=3)
            if now >= due:
                for b in client.index_candles(today, tf, until=now):
                    if (last_bar is None or b.t > last_bar) and b.t + timedelta(minutes=tf) <= now:
                        sess.on_bar(b)
                        last_bar = b.t
            errors = 0
        except Exception as e:  # network or API error: keep going, but never sit blind in a position
            errors += 1
            log(f"{now:%H:%M:%S} ERROR {type(e).__name__}: {e}")
            if errors >= 30 and strat.position is not None:
                log("30 errors in a row while in a position: trying to exit")
                try:
                    sess.end_of_day(now, client.index_ltp())
                except Exception as e2:
                    log(f"EXIT FAILED ({e2}). CLOSE THE POSITION IN THE GROWW APP NOW.")
                break
            _time.sleep(2)
        _time.sleep(cfg["poll_seconds"])
    log(f"{ist_now():%H:%M:%S} session over | trades {len(strat.trades)} | day P&L Rs {risk.realised:+.0f} | "
        f"paper record: {journal.stats('paper')}")


# ---------------------------------------------------------------- offline replay
def read_bars(path: str):
    out = []
    with open(path) as f:
        for r in csv.DictReader(f):
            out.append(Bar(datetime.fromisoformat(r["time"]), float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"])))
    return out


def run_replay(args, cfg) -> None:
    """Drives the same Session with a saved day of index candles. Option prices are a crude
    delta-0.55 approximation, so this checks the plumbing and the rules, not the P&L."""
    tf = cfg["timeframe_min"]
    prev, today = read_bars(args.prev), read_bars(args.replay)
    day = today[0].t.date().isoformat()
    strat = Strategy(prev, params_from(cfg))
    risk = RiskManager(RiskConfig(**cfg["risk"]))
    journal = Journal(os.path.join(cfg["journal_dir"], "replay"))
    state = {"index": today[0].o}
    bases = {}

    def pick(side, spot):
        sym = f"SIM-{side}-{len(bases) + 1}"
        bases[sym] = (side, spot)
        return {"trading_symbol": sym, "strike": round(spot / 50) * 50, "ltp": cfg["target_premium"], "delta": 0.55, "expiry": ""}

    def quote(sym):
        side, base = bases[sym]
        move = state["index"] - base if side == "CE" else base - state["index"]
        return max(1.0, cfg["target_premium"] + 0.55 * move)

    sess = Session(day, strat, PaperBroker(quote, cfg["paper_slippage"]), risk, journal, "replay",
                   pick_option=pick, option_quote=quote, protect_mult=cfg["protect_mult"])
    print(f"replay {day} | zones: " + ", ".join(f"{z.name} {z.level:.0f}" for z in strat.zones))
    sess.log = print
    sess.show_plan(today[0].o, today[0].t)
    for b in today:
        for k, px in enumerate(bar_path(b)):
            state["index"] = px
            sess.on_tick(b.t, px, first_of_bar=(k == 0))
        state["index"] = b.c
        sess.on_bar(b)
    sess.end_of_day(today[-1].t, today[-1].c)
    print(f"replay done | trades {len(strat.trades)} | P&L Rs {risk.realised:+.0f} (approximate option prices)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["paper", "live"], default="paper")
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--skip-gate", action="store_true", help="go live without the paper record (not recommended)")
    ap.add_argument("--replay", help="CSV of one day's index candles (time,open,high,low,close)")
    ap.add_argument("--prev", help="CSV of the previous day's candles (for --replay)")
    a = ap.parse_args()
    c = load_config(a.config)
    if a.replay:
        run_replay(a, c)
    else:
        run_live(a, c)

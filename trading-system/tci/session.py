"""Connects the rules engine to a broker: picks the option, sizes it, places and exits orders,
enforces risk limits, and journals every closed trade. Used by both paper and live mode."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, List, Optional

from . import costs
from .journal import Journal
from .risk import RiskManager
from .rules import Bar, Event, Strategy, bar_path


@dataclass
class OpenTrade:
    symbol: str
    qty: int
    lots: int
    opt_entry: float
    protect_id: Optional[str]
    opened: datetime


class PaperBroker:
    """Fills at the current option price plus/minus slippage. No orders leave this machine."""

    def __init__(self, quote: Callable[[str], float], slippage: float = 1.0):
        self.quote = quote
        self.slippage = slippage

    def buy(self, symbol: str, qty: int, ref: str):
        return qty, round(self.quote(symbol) + self.slippage, 2)

    def sell(self, symbol: str, qty: int, ref: str):
        return qty, round(max(0.05, self.quote(symbol) - self.slippage), 2)

    def protect(self, symbol: str, qty: int, trigger: float, ref: str):
        return None

    def unprotect(self, order_id: Optional[str]) -> bool:
        """Cancel the protective stop. Returns True if it had already executed."""
        return False


class GrowwBroker:
    """Real orders through Groww: marketable LIMIT orders plus an exchange-held SL-M safety stop."""

    def __init__(self, client, buffer_pct: float = 1.0):
        self.c = client
        self.buffer = buffer_pct / 100

    def buy(self, symbol: str, qty: int, ref: str):
        ltp = self.c.option_ltp(symbol)
        oid = self.c.place_limit(symbol, qty, True, ltp * (1 + self.buffer) + 0.5, ref)
        st, filled, avg = self.c.wait_fill(oid)
        if filled < qty:
            self.c.cancel(oid)
        return filled, avg

    def sell(self, symbol: str, qty: int, ref: str):
        left, value = qty, 0.0
        for attempt in range(4):  # must get out: widen the price each try
            ltp = self.c.option_ltp(symbol)
            px = max(0.05, ltp * (1 - self.buffer * (attempt + 1)) - 0.5)
            oid = self.c.place_limit(symbol, left, False, px, f"{ref}x{attempt}")
            st, filled, avg = self.c.wait_fill(oid)
            if filled < left:
                self.c.cancel(oid)
            value += filled * avg
            left -= filled
            if left == 0:
                break
        if left:
            raise RuntimeError(f"could not fully exit {symbol}: {left} still open. EXIT MANUALLY IN THE GROWW APP.")
        return qty, value / qty

    def protect(self, symbol: str, qty: int, trigger: float, ref: str):
        try:
            return self.c.place_stop_market(symbol, qty, max(0.05, trigger), ref)
        except Exception as e:
            print(f"WARNING: protective stop rejected ({e}); the program's own exit is the only stop.")
            return None

    def unprotect(self, order_id: Optional[str]) -> bool:
        if not order_id:
            return False
        st = self.c.order(order_id).get("order_status", "")
        if st in ("EXECUTED", "COMPLETED"):
            return True
        self.c.cancel(order_id)
        return False


class Session:
    def __init__(self, day: str, strategy: Strategy, broker, risk: RiskManager, journal: Journal, mode: str,
                 pick_option: Callable[[str, float], Dict], option_quote: Callable[[str], float],
                 exchange: str = "NSE", protect_mult: float = 2.0, log: Callable[[str], None] = print):
        self.day, self.s, self.broker, self.risk, self.journal, self.mode = day, strategy, broker, risk, journal, mode
        self.pick_option, self.option_quote, self.exchange = pick_option, option_quote, exchange
        self.protect_mult, self.log = protect_mult, log
        self.open: Optional[OpenTrade] = None
        self.seq = 0

    # ---- inputs ----------------------------------------------------------------
    def on_tick(self, now: datetime, index_price: float, first_of_bar: bool = False) -> None:
        why = self.risk.blocked()
        if why:
            if not self.s.halted:
                self.log(f"{now:%H:%M:%S} HALT: {why}")
            self.s.halted = True
            self.s.pending = None
            if self.risk.kill_switch() and self.s.position is not None:
                self.handle(self.s.force_exit(now, index_price, "kill switch"), index_price)
        ev = self.s.on_price(index_price, now, gap_open=first_of_bar)
        if ev:
            self.handle(ev, index_price)

    def on_bar(self, bar: Bar) -> None:
        for ev in self.s.on_bar_close(bar):
            self.handle(ev, bar.c)
        self.show_plan(bar.c, bar.t)

    def show_plan(self, price: float, t: datetime) -> None:
        """Log both directions (CALL above / PUT below) whenever the nearest zones change."""
        plan = self.s.plan(price)
        key = tuple((k, v["level"], v["target"]) for k, v in sorted(plan.items()))
        if key != getattr(self, "_plan_key", None):
            self._plan_key = key
            for side in ("CE", "PE"):
                if side in plan:
                    self.log(f"{t:%H:%M} PLAN   {plan[side]['text']}")

    def end_of_day(self, now: datetime, index_price: float) -> None:
        if self.s.position is not None:
            self.handle(self.s.force_exit(now, index_price, "end of session"), index_price)

    # ---- events -> orders ------------------------------------------------------
    def handle(self, ev: Optional[Event], index_price: float) -> None:
        if ev is None:
            return
        t = f"{ev.t:%H:%M}"
        if ev.kind in ("setup", "skip", "cancel"):
            self.log(f"{t} {ev.kind.upper():6s} {ev.side} {ev.detail}")
        elif ev.kind == "entry":
            self._enter(ev)
        elif ev.kind == "exit":
            self._exit(ev)

    def _enter(self, ev: Event) -> None:
        pos = self.s.position
        try:
            opt = self.pick_option(ev.side, ev.price)
        except Exception as e:
            self.log(f"{ev.t:%H:%M} no option found ({e}); entry cancelled")
            self.s.cancel_position(ev.t, "no option")
            return
        est_risk = max(0.5, opt["delta"] * pos.risk)
        lots = self.risk.lots_for(est_risk)
        if lots == 0:
            self.log(f"{ev.t:%H:%M} SKIP   {ev.side} one lot risks Rs {est_risk * self.risk.cfg.lot_size:.0f} "
                     f"> budget Rs {self.risk.risk_budget:.0f}")
            self.s.cancel_position(ev.t, "size 0")
            return
        qty = lots * self.risk.cfg.lot_size
        self.seq += 1
        ref = f"TCI{self.day.replace('-', '')[2:]}{self.seq:02d}"
        filled, px = self.broker.buy(opt["trading_symbol"], qty, ref + "B")
        if filled == 0:
            self.log(f"{ev.t:%H:%M} buy order not filled; entry cancelled")
            self.s.cancel_position(ev.t, "not filled")
            return
        pid = self.broker.protect(opt["trading_symbol"], filled, px - self.protect_mult * est_risk, ref + "S")
        self.open = OpenTrade(opt["trading_symbol"], filled, filled // self.risk.cfg.lot_size, px, pid, ev.t)
        self.log(f"{ev.t:%H:%M} ENTRY  BUY {filled} {opt['trading_symbol']} @ {px:.2f} | index {ev.price:.1f} "
                 f"stop {pos.stop:.1f} target {pos.target:.1f} | est. risk Rs {est_risk * filled:.0f}")

    def _exit(self, ev: Event) -> None:
        tr = ev.trade
        o = self.open
        if o is None:
            return
        self.seq += 1
        already = self.broker.unprotect(o.protect_id)
        if already:
            px = self.option_quote(o.symbol)
            self.log("protective stop had already executed at the exchange")
        else:
            _, px = self.broker.sell(o.symbol, o.qty, f"TCI{self.day.replace('-', '')[2:]}{self.seq:02d}X")
        gross = (px - o.opt_entry) * o.qty
        ch = costs.round_trip(o.opt_entry * o.qty, px * o.qty, self.exchange)
        net = gross - ch
        self.risk.record(net)
        self.journal.add(dict(date=self.day, mode=self.mode, side=tr.side, zone=tr.zone, symbol=o.symbol, lots=o.lots,
                              qty=o.qty, index_entry=round(tr.entry, 2), index_stop=round(tr.initial_stop, 2),
                              index_target=round(tr.target, 2), index_exit=round(tr.exit, 2), reason=tr.reason,
                              opt_entry=o.opt_entry, opt_exit=round(px, 2), gross=round(gross, 2), charges=ch,
                              net=round(net, 2), opened=f"{o.opened:%H:%M}", closed=f"{ev.t:%H:%M}"))
        self.log(f"{ev.t:%H:%M} EXIT   {tr.reason} | SELL {o.qty} {o.symbol} @ {px:.2f} | net Rs {net:+.0f} "
                 f"| day Rs {self.risk.realised:+.0f}")
        self.open = None


def warm_up(strategy: Strategy, bars: List[Bar]) -> None:
    """Bring a strategy up to date with bars that finished before the program started (no orders)."""
    for b in bars:
        for k, px in enumerate(bar_path(b)):
            strategy.on_price(px, b.t, gap_open=(k == 0))
        strategy.on_bar_close(b)
    if strategy.position is not None:
        strategy.cancel_position(bars[-1].t, "position from before start-up ignored")
    strategy.pending = None

"""Mechanical version of the TRADING CAFE INDIA "zone breakout + follow-up candle" setup.

Everything that decides a trade lives here, with no broker or data code, so the
backtest, the paper trader and the live bot all run exactly the same logic.

How a trade happens (long side; the short side is the mirror image and buys a PE):

1. Zones for the day: previous day's high / low / close, the previous day's
   last-90-minute ("distribution") high / low, and today's opening-range
   high / low once the first 15 minutes are over.
2. Breakout candle: a completed green candle that closes above a zone it
   opened (or the previous candle closed) at or below.
3. Follow-up: the very next candle must trade above the breakout candle's high
   (+ buffer). Only then do we buy. If it doesn't, the setup is cancelled.
4. Stop: breakout candle's low (- buffer). Target: the next zone above the
   entry. If that zone is closer than `min_rr` x risk, the trade is skipped.
   With no zone above, the target is `blue_sky_rr` x risk.
5. Management: stop moves to entry once price has gone 1R in our favour; exit
   at stop, target, or the square-off time.
6. Day limits: max trades, stop after N losses, max two attempts per zone,
   no entries before `first_entry` or after `last_entry`.

All prices are in index points. The option bought is chosen elsewhere.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import List, Optional


@dataclass
class Bar:
    t: datetime  # bar start time (exchange time, IST)
    o: float
    h: float
    l: float
    c: float


@dataclass
class Params:
    timeframe_min: int = 5
    or_minutes: int = 15
    distribution_from: time = time(14, 0)
    zone_merge_pts: float = 10.0
    trigger_buffer: float = 1.0
    stop_buffer: float = 1.0
    min_risk_pts: float = 6.0
    max_risk_pts: float = 35.0
    min_rr: float = 2.0
    blue_sky_rr: float = 3.0
    breakeven_at_r: float = 1.0
    first_entry: time = time(9, 25)
    last_entry: time = time(14, 30)
    square_off: time = time(15, 15)
    max_trades: int = 3
    max_losses: int = 2
    max_attempts_per_zone: int = 2


@dataclass
class Zone:
    level: float
    name: str


@dataclass
class Pending:
    side: str  # "CE" (long index) or "PE" (short index)
    trigger: float
    stop: float
    target: float
    zone: Zone
    valid_for: datetime  # start time of the follow-up bar


@dataclass
class Position:
    side: str
    entry: float
    stop: float
    target: float
    risk: float
    zone: Zone
    opened: datetime
    at_breakeven: bool = False


@dataclass
class Trade:
    side: str
    zone: str
    opened: datetime
    entry: float
    initial_stop: float
    target: float
    closed: datetime
    exit: float
    reason: str  # "target" | "stop" | "breakeven" | "square-off"

    @property
    def risk(self) -> float:
        return abs(self.entry - self.initial_stop)

    @property
    def points(self) -> float:
        return (self.exit - self.entry) if self.side == "CE" else (self.entry - self.exit)

    @property
    def r(self) -> float:
        return self.points / self.risk if self.risk else 0.0


@dataclass
class Event:
    kind: str  # "entry" | "exit" | "setup" | "cancel" | "skip"
    t: datetime
    side: str = ""
    price: float = 0.0
    detail: str = ""
    trade: Optional[Trade] = None


def prior_day_zones(prev: List[Bar], p: Params) -> List[Zone]:
    if not prev:
        return []
    z = [
        Zone(max(b.h for b in prev), "PDH"),
        Zone(min(b.l for b in prev), "PDL"),
        Zone(prev[-1].c, "PDC"),
    ]
    late = [b for b in prev if b.t.time() >= p.distribution_from]
    if late:
        z.append(Zone(max(b.h for b in late), "prev last-hour high"))
        z.append(Zone(min(b.l for b in late), "prev last-hour low"))
    return z


def merge_zones(zones: List[Zone], merge_pts: float) -> List[Zone]:
    out: List[Zone] = []
    for z in sorted(zones, key=lambda z: z.level):
        if out and z.level - out[-1].level <= merge_pts:
            last = out[-1]
            out[-1] = Zone((last.level + z.level) / 2, f"{last.name}/{z.name}")
        else:
            out.append(z)
    return out


class Strategy:
    """One instance per trading day. Feed it prices in time order.

    - `on_price(price, now)` for every tick / intrabar price (fills entries and exits).
    - `on_bar_close(bar)` once per completed bar (zones, setups, breakeven, square-off).
    """

    def __init__(self, prev_day: List[Bar], p: Optional[Params] = None):
        self.p = p or Params()
        self.base_zones = prior_day_zones(prev_day, self.p)
        self.zones = merge_zones(self.base_zones, self.p.zone_merge_pts)
        self.or_bars: List[Bar] = []
        self.or_done = False
        self.prev_bar: Optional[Bar] = None
        self.pending: Optional[Pending] = None
        self.position: Optional[Position] = None
        self.trades: List[Trade] = []
        self.attempts: dict = {}
        self.events: List[Event] = []
        self.halted = False

    # ---- day limits -------------------------------------------------------
    @property
    def losses(self) -> int:
        return sum(1 for t in self.trades if t.points < 0)

    def can_open(self, now: datetime) -> bool:
        tt = now.time()
        return (
            not self.halted
            and self.position is None
            and self.p.first_entry <= tt <= self.p.last_entry
            and len(self.trades) < self.p.max_trades
            and self.losses < self.p.max_losses
        )

    # ---- intrabar ---------------------------------------------------------
    def on_price(self, price: float, now: datetime, gap_open: bool = False) -> Optional[Event]:
        """Process one price. `gap_open=True` means this is the first price of a bar,
        so a level that was jumped over fills at this price instead of at the level."""
        if self.position is not None:
            return self._check_exit(price, now, gap_open)
        if self.pending is not None and now >= self.pending.valid_for:
            return self._check_trigger(price, now, gap_open)
        return None

    def _check_trigger(self, price: float, now: datetime, gap_open: bool) -> Optional[Event]:
        pd = self.pending
        hit = price >= pd.trigger if pd.side == "CE" else price <= pd.trigger
        if not hit or not self.can_open(now):
            return None
        fill = price if gap_open else pd.trigger
        risk = (fill - pd.stop) if pd.side == "CE" else (pd.stop - fill)
        reward = (pd.target - fill) if pd.side == "CE" else (fill - pd.target)
        self.pending = None
        if risk <= 0 or reward < self.p.min_rr * risk * 0.999:
            return self._emit(Event("skip", now, pd.side, fill, "gap made R:R too poor"))
        self.position = Position(pd.side, fill, pd.stop, pd.target, risk, pd.zone, now)
        key = (pd.zone.name, pd.side)
        self.attempts[key] = self.attempts.get(key, 0) + 1
        return self._emit(Event("entry", now, pd.side, fill,
                                f"{pd.zone.name} {pd.zone.level:.0f} | stop {pd.stop:.1f} | target {pd.target:.1f}"))

    def _check_exit(self, price: float, now: datetime, gap_open: bool) -> Optional[Event]:
        pos = self.position
        long = pos.side == "CE"
        if (price <= pos.stop) if long else (price >= pos.stop):
            reason = "breakeven" if pos.at_breakeven else "stop"
            return self._close(now, price if gap_open else pos.stop, reason)
        if (price >= pos.target) if long else (price <= pos.target):
            return self._close(now, price if gap_open else pos.target, "target")
        return None

    def cancel_position(self, now: datetime, why: str) -> Event:
        """Forget an entry that could not be executed (no fill, size 0, risk block). Not counted as a trade."""
        pos = self.position
        self.position = None
        if pos is not None:
            key = (pos.zone.name, pos.side)
            self.attempts[key] = max(0, self.attempts.get(key, 1) - 1)
        return self._emit(Event("cancel", now, pos.side if pos else "", pos.entry if pos else 0.0, why))

    def force_exit(self, now: datetime, px: float, reason: str) -> Optional[Event]:
        """Close the open position at `px` now (kill switch, day loss limit, end of session)."""
        if self.position is None:
            return None
        return self._close(now, px, reason)

    def _close(self, now: datetime, px: float, reason: str) -> Event:
        pos = self.position
        initial_stop = pos.entry - pos.risk if pos.side == "CE" else pos.entry + pos.risk
        tr = Trade(pos.side, pos.zone.name, pos.opened, pos.entry, initial_stop, pos.target, now, px, reason)
        self.trades.append(tr)
        self.position = None
        return self._emit(Event("exit", now, tr.side, px, f"{reason} ({tr.r:+.2f}R)", tr))

    # ---- bar close --------------------------------------------------------
    def on_bar_close(self, bar: Bar) -> List[Event]:
        out: List[Event] = []
        end_min = bar.t.hour * 60 + bar.t.minute + self.p.timeframe_min
        end_time = time(min(end_min // 60, 23), end_min % 60)

        # opening range
        if not self.or_done:
            self.or_bars.append(bar)
            if end_min >= 9 * 60 + 15 + self.p.or_minutes:
                self.or_done = True
                self.zones = merge_zones(
                    self.base_zones + [Zone(max(b.h for b in self.or_bars), "ORH"),
                                       Zone(min(b.l for b in self.or_bars), "ORL")],
                    self.p.zone_merge_pts)

        # position management
        if self.position is not None:
            pos = self.position
            if end_time >= self.p.square_off:
                out.append(self._close(bar.t, bar.c, "square-off"))
            elif not pos.at_breakeven:
                move = (bar.h - pos.entry) if pos.side == "CE" else (pos.entry - bar.l)
                if move >= self.p.breakeven_at_r * pos.risk:
                    pos.stop = pos.entry
                    pos.at_breakeven = True

        # an unfilled follow-up expires after its one bar
        if self.pending is not None and bar.t >= self.pending.valid_for:
            out.append(self._emit(Event("cancel", bar.t, self.pending.side, self.pending.trigger,
                                        "follow-up candle did not confirm")))
            self.pending = None

        # new breakout?
        if self.position is None and self.pending is None:
            nxt = _add_minutes(bar.t, self.p.timeframe_min)
            if self.can_open(nxt):
                ev = self._detect(bar, nxt)
                if ev:
                    out.append(self._emit(ev))

        self.prev_bar = bar
        return out

    def _emit(self, ev: Event) -> Event:
        self.events.append(ev)
        return ev

    def _detect(self, bar: Bar, follow_up_start: datetime) -> Optional[Event]:
        p = self.p
        ref = min(bar.o, self.prev_bar.c) if self.prev_bar else bar.o
        ref_hi = max(bar.o, self.prev_bar.c) if self.prev_bar else bar.o
        levels = [z.level for z in self.zones]
        if bar.c > bar.o:
            crossed = [z for z in self.zones if ref <= z.level < bar.c]
            if not crossed:
                return None
            zone = max(crossed, key=lambda z: z.level)
            side, trigger, stop = "CE", bar.h + p.trigger_buffer, bar.l - p.stop_buffer
            above = [lv for lv in levels if lv > trigger]
            risk = trigger - stop
            target = min(above) if above else trigger + p.blue_sky_rr * risk
        elif bar.c < bar.o:
            crossed = [z for z in self.zones if bar.c < z.level <= ref_hi]
            if not crossed:
                return None
            zone = min(crossed, key=lambda z: z.level)
            side, trigger, stop = "PE", bar.l - p.trigger_buffer, bar.h + p.stop_buffer
            below = [lv for lv in levels if lv < trigger]
            risk = stop - trigger
            target = max(below) if below else trigger - p.blue_sky_rr * risk
        else:
            return None
        if self.attempts.get((zone.name, side), 0) >= p.max_attempts_per_zone:
            return self._skip(bar, side, trigger, f"third attempt at {zone.name}")
        if not (p.min_risk_pts <= risk <= p.max_risk_pts):
            return self._skip(bar, side, trigger, f"risk {risk:.1f} pts outside {p.min_risk_pts:g}-{p.max_risk_pts:g}")
        reward = abs(target - trigger)
        if reward < p.min_rr * risk:
            return self._skip(bar, side, trigger, f"next zone only {reward / risk:.1f}R away")
        self.pending = Pending(side, trigger, stop, target, zone, follow_up_start)
        return Event("setup", bar.t, side, trigger,
                     f"breakout of {zone.name} {zone.level:.0f}; buy {side} if index "
                     f"{'>=' if side == 'CE' else '<='} {trigger:.1f} next candle; stop {stop:.1f}; target {target:.1f}")

    def _skip(self, bar: Bar, side: str, trigger: float, why: str) -> Event:
        return Event("skip", bar.t, side, trigger, why)


def _add_minutes(t: datetime, m: int) -> datetime:
    from datetime import timedelta
    return t + timedelta(minutes=m)


def bar_path(b: Bar) -> List[float]:
    """Standard OHLC path assumption: green bar goes O-L-H-C, red bar O-H-L-C."""
    return [b.o, b.l, b.h, b.c] if b.c >= b.o else [b.o, b.h, b.l, b.c]


def run_day(prev_day: List[Bar], today: List[Bar], p: Optional[Params] = None) -> Strategy:
    """Backtest one day on completed bars. Entries/exits fill inside the bar using `bar_path`."""
    s = Strategy(prev_day, p)
    for b in today:
        for k, px in enumerate(bar_path(b)):
            s.on_price(px, b.t, gap_open=(k == 0))
        s.on_bar_close(b)
    if s.position is not None and today:
        s._close(today[-1].t, today[-1].c, "square-off")
    return s

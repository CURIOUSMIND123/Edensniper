"""Fair Price engine: JJ Simon's "fair pricing theory" adapted to Nifty and Sensex.

The idea, as he explains it: the session's opening price is the fair price. The
rush of orders at the open pushes price away from it (an "unfair" move), and
over the next 90 minutes price tends to come back. So:

1. First trade of the session: follow the opening 1-minute candle's colour, but
   only when it agrees with the higher-timeframe bias. That bias is the opposite
   of what happened over the previous session (he inverts the last 6-12 hours).
2. After that, only trade back toward the fair price. Enter on a candle close
   that shows one of two signals:
     - displacement: its body is bigger than the previous body, it closes
       beyond the previous candle's wick, and the previous candle was the
       opposite colour;
     - break of structure: it closes beyond the latest swing low (for a short)
       or swing high (for a long). A swing low is a wick lower than the candle
       before and after it.
3. Fixed stop and fixed target (1 : 1.5). If the opening candle is bigger than
   the stop, use double the stop and target at half the size.
4. Only take a reversion trade when price has room to travel toward fair price
   (at least 80% of the target).
5. Three losses in a row ends the session.
6. New entries only in the first 90 minutes (9:15-10:45). An optional second
   session (his 2 pm session) trades the same way back toward the 9:15 open:
   its first candle is a continuation trade only if it points toward the open.

Points are index points. Defaults are for Nifty; scale them for Sensex
(about 3.1x). Everything here works on finished 1-minute candles.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import List, Optional

from .rules import Bar, bar_path


@dataclass
class FPParams:
    sl: float = 20.0                 # stop, index points
    tp: float = 30.0                 # target, index points (1 : 1.5)
    big_open: float = 20.0           # opening candle range above this -> 2x stop/target, half size
    target: str = "static"           # "static" = fixed tp; "fair" = exit at the fair price
    min_room: float = 0.8            # need |price - fair| >= min_room * tp before a reversion entry
    start: time = time(9, 15)
    end: time = time(10, 45)         # no new entries after this
    pm_start: Optional[time] = None  # optional second session (his 2 pm session), e.g. 13:30
    pm_end: Optional[time] = None    # trades back toward the morning fair price
    exit_by: time = time(15, 15)     # close anything still open
    max_losses: int = 3              # losses in a row that end the session
    use_continuation: bool = True
    use_bias: bool = True            # continuation must agree with the higher-timeframe bias
    use_displacement: bool = True
    use_bos: bool = True


@dataclass
class FPTrade:
    side: str                        # "BUY" or "SELL"
    setup: str                       # "CONT", "DISP" or "BOS"
    opened: datetime
    entry: float
    sl: float
    tp: float
    size: float = 1.0                # 0.5 when the opening candle was big
    closed: Optional[datetime] = None
    exit: Optional[float] = None
    reason: str = ""

    @property
    def sign(self) -> int:
        return 1 if self.side == "BUY" else -1

    @property
    def points(self) -> float:
        return 0.0 if self.exit is None else self.sign * (self.exit - self.entry)

    @property
    def risk(self) -> float:
        return abs(self.entry - self.sl)

    @property
    def r(self) -> float:
        return self.points / self.risk if self.risk else 0.0


def htf_bias(prev_day: List[Bar], today_open: float) -> int:
    """+1 = look for longs, -1 = look for shorts, 0 = none.

    The bias inverts the last session: if price rose from yesterday's open to
    today's open, the bias is down, and the other way round.
    """
    if not prev_day:
        return 0
    move = today_open - prev_day[0].o
    return 0 if move == 0 else (-1 if move > 0 else 1)


@dataclass
class FairPriceDay:
    prev_day: List[Bar]
    p: FPParams = field(default_factory=FPParams)

    def __post_init__(self):
        self.fair: Optional[float] = None
        self.bias = 0
        self.bars: List[Bar] = []
        self.trades: List[FPTrade] = []
        self.position: Optional[FPTrade] = None
        self.losses_in_row = 0
        self.stopped = False
        self.swing_low: Optional[float] = None
        self.swing_high: Optional[float] = None
        self.in_pm = False

    # ---- signals on a finished candle -------------------------------------------------
    def _displacement(self, d: int) -> bool:
        if len(self.bars) < 2:
            return False
        b, pb = self.bars[-1], self.bars[-2]
        body, pbody = abs(b.c - b.o), abs(pb.c - pb.o)
        if d < 0:
            return b.c < b.o and pb.c > pb.o and body > pbody and b.c < pb.l
        return b.c > b.o and pb.c < pb.o and body > pbody and b.c > pb.h

    def _bos(self, d: int) -> bool:
        if len(self.bars) < 2:
            return False
        b, pb = self.bars[-1], self.bars[-2]
        if d < 0:
            return self.swing_low is not None and b.c < self.swing_low <= pb.c
        return self.swing_high is not None and b.c > self.swing_high >= pb.c

    def _update_swings(self):
        """A swing low is a wick lower than the candle before and after it (needs the next candle)."""
        if len(self.bars) < 3:
            return
        a, m, z = self.bars[-3], self.bars[-2], self.bars[-1]
        if m.l < a.l and m.l < z.l:
            self.swing_low = m.l
        if m.h > a.h and m.h > z.h:
            self.swing_high = m.h

    # ---- orders -----------------------------------------------------------------------
    def _open(self, t: datetime, side: str, setup: str, px: float, sl: float, tp: float, size: float = 1.0):
        s = 1 if side == "BUY" else -1
        self.position = FPTrade(side, setup, t, px, px - s * sl, px + s * tp, size)
        self.trades.append(self.position)

    def _close(self, t: datetime, px: float, reason: str):
        tr = self.position
        tr.closed, tr.exit, tr.reason = t, px, reason
        self.position = None
        if tr.points < 0:
            self.losses_in_row += 1
            if self.losses_in_row >= self.p.max_losses:
                self.stopped = True
        elif tr.points > 0:
            self.losses_in_row = 0

    def on_price(self, px: float, t: datetime):
        tr = self.position
        if tr is None:
            return
        if tr.sign * (px - tr.sl) <= 0:
            self._close(t, tr.sl, "SL")
        elif tr.sign * (px - tr.tp) >= 0:
            self._close(t, tr.tp, "TP")

    def on_bar_close(self, b: Bar):
        p = self.p
        self.bars.append(b)
        if self.fair is None:
            self.fair = b.o
            self.bias = htf_bias(self.prev_day, b.o)
        if self.position is not None and b.t.time() >= p.exit_by:
            self._close(b.t, b.c, "time")
        if len(self.bars) == 1:
            self._continuation(b)
            return
        self._update_swings()
        now = b.t.time()
        pm = p.pm_start is not None and p.pm_end is not None and p.pm_start <= now < p.pm_end
        if pm and not self.in_pm:
            self.in_pm = True                   # a new session: fresh loss count, first candle may continue
            self.losses_in_row, self.stopped = 0, False
            if self.position is None and p.use_continuation:
                d = 1 if b.c > b.o else -1 if b.c < b.o else 0
                if d and d == (1 if self.fair > b.c else -1) and abs(self.fair - b.c) >= p.min_room * p.tp:
                    self._open(b.t, "BUY" if d > 0 else "SELL", "CONT", b.c, p.sl, p.tp)
            return
        if self.position is not None or self.stopped:
            return
        if not (p.start <= now < p.end or pm):
            return
        self._reversion(b)

    def _continuation(self, b: Bar):
        p = self.p
        colour = 1 if b.c > b.o else -1 if b.c < b.o else 0
        if not p.use_continuation or colour == 0:
            return
        if p.use_bias and colour != self.bias:
            return
        big = (b.h - b.l) > p.big_open
        sl, tp, size = (2 * p.sl, 2 * p.tp, 0.5) if big else (p.sl, p.tp, 1.0)
        self._open(b.t, "BUY" if colour > 0 else "SELL", "CONT", b.c, sl, tp, size)

    def _reversion(self, b: Bar):
        p = self.p
        gap = self.fair - b.c                   # >0 means fair price is above -> buy
        d = 1 if gap > 0 else -1
        room = abs(gap)
        if p.target == "fair":
            if room < 1.5 * p.sl:               # still want at least 1 : 1.5 to fair price
                return
            tp = room
        else:
            if room < p.min_room * p.tp:
                return
            tp = p.tp
        setup = None
        if p.use_bos and self._bos(d):
            setup = "BOS"
        elif p.use_displacement and self._displacement(d):
            setup = "DISP"
        if setup:
            self._open(b.t, "BUY" if d > 0 else "SELL", setup, b.c, p.sl, tp)


def run_day(prev_day: List[Bar], today: List[Bar], p: Optional[FPParams] = None) -> FairPriceDay:
    """Backtest one day of finished 1-minute candles. Stops and targets fill inside the candle."""
    s = FairPriceDay(prev_day, p or FPParams())
    for b in today:
        if s.position is not None:
            for px in bar_path(b):
                s.on_price(px, b.t)
                if s.position is None:
                    break
        s.on_bar_close(b)
    if s.position is not None and today:
        s._close(today[-1].t, today[-1].c, "end")
    return s

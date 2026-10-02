"""TCI All-in-One: his whole price-action method as one signal engine for the index.

This is the reference version of tradingview/tci_all_in_one.pine. Same rules, so it can be backtested.

What it tracks (on completed candles):
  * Key levels: previous day high / low / close, previous day's last hour high / low
    ("distribution"), today's opening range (first 15 min).
  * Liquidity: confirmed swing highs (buy-side liquidity: stops of sellers sit above them)
    and swing lows (sell-side liquidity), marked "equal" when two are almost the same price.
  * Demand / supply zones: the last opposite candle before a strong "displacement" candle
    (his "base where the strong rally started" / "zone the fall came from"). Only the first
    touch counts ("take the first bounce, avoid the second").
  * Market structure: up after a close above the last swing high, down after a close below
    the last swing low.
  * Candles: pin bars and engulfing candles.

Signals (BUY = buy a call on the index, SELL = buy a put), checked in this order:
  1. SWEEP (the trap): price runs below a sell-side level (taking the stops), then the candle
     closes back above it as a bullish pin bar or engulfing candle -> BUY. Mirror -> SELL.
     This is the "everyone is long, he says short" trade.
  2. ZONE: first touch of a fresh demand zone with a bullish pin / engulfing candle, while
     structure is not down -> BUY. Mirror at supply -> SELL.
  3. BREAKOUT: a strong-bodied candle closes through a key level -> BUY / SELL.
Every signal needs his follow-up: the next candle must break the signal candle's high (low
for SELL) before entry. Stop: beyond the signal candle (or the swept low / the zone).
Skip if the nearest opposing level is closer than `min_room_r` x risk (no room to target).
Targets: T1 = nearest opposing level (or 2R), T2 = the next one (or 3R), T3 = 4R.
After T1: stop to entry. Day limits: entry window, max trades, stop after 2 losses.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Tuple

from .rules import Bar, bar_path


@dataclass
class AIParams:
    timeframe_min: int = 5
    atr_len: int = 14
    pivot_len: int = 3            # bars on each side of a swing high / low
    max_swings: int = 8           # unswept swings kept per side
    eq_tol_atr: float = 0.15      # two swings this close (x ATR) are "equal highs / lows"
    disp_atr: float = 1.5         # displacement candle: body >= this x ATR creates a demand / supply zone
    max_zones: int = 6
    pin_wick_body: float = 2.0    # pin bar: rejection wick >= 2 x body ...
    pin_wick_range: float = 0.5   # ... and >= 50% of the candle range
    breakout_body: float = 0.5    # breakout candle body >= 50% of its range
    sweep_min_pts: float = 1.0
    trigger_buffer: float = 1.0
    sl_buffer: float = 2.0
    min_sl_pts: float = 5.0
    max_sl_pts: float = 40.0
    min_room_r: float = 1.5
    t1_max_r: float = 3.0         # use the nearest level as T1 only if it is within this many R
    confirm_bars: int = 1         # bars the follow-up has to break the signal candle
    or_minutes: int = 15
    distribution_from: time = time(14, 0)
    first_entry: time = time(9, 20)
    last_entry: time = time(14, 30)
    square_off: time = time(15, 15)
    max_trades: int = 4
    max_losses: int = 2
    use_bias_filter: bool = False  # trade only in the direction of the bias score
    exit_mode: str = "T1"          # "T1": full exit at T1 | "split": half at T1, rest to T2 / entry


@dataclass
class Level:
    price: float
    name: str
    side: str            # "high" (resistance / buy-side liquidity) or "low" (support / sell-side liquidity)
    swing: bool = False
    t: Optional[datetime] = None


@dataclass
class ZoneBox:
    lo: float
    hi: float
    kind: str            # "demand" or "supply"
    t: datetime
    touched: bool = False


@dataclass
class Signal:
    t: datetime
    side: str            # "BUY" or "SELL"
    setup: str           # "SWEEP" | "ZONE" | "BREAKOUT"
    detail: str
    trigger: float
    sl: float
    valid_until: datetime  # follow-up window ends here (exclusive)


@dataclass
class AITrade:
    side: str
    setup: str
    detail: str
    signal_t: datetime
    opened: datetime
    entry: float
    sl: float
    t1: float
    t2: float
    t3: float
    sl0: float = 0.0           # initial stop (risk is measured on this)
    closed: Optional[datetime] = None
    exit: float = 0.0          # average exit (split mode averages the two halves)
    reason: str = ""
    half_done: bool = False
    half_exit: float = 0.0
    half_t: Optional[datetime] = None

    @property
    def risk(self) -> float:
        return abs(self.entry - self.sl0)

    @property
    def points(self) -> float:
        return (self.exit - self.entry) if self.side == "BUY" else (self.entry - self.exit)

    @property
    def r(self) -> float:
        return self.points / self.risk if self.risk else 0.0


class AllInOne:
    """Feed completed candles of ONE index in time order with `on_bar`; intrabar prices with `on_price`.
    State (swings, zones, ATR) carries across days; day counters reset on a new date."""

    def __init__(self, p: Optional[AIParams] = None):
        self.p = p or AIParams()
        self.bars: List[Bar] = []
        self.atr: Optional[float] = None
        self.swings_hi: List[Level] = []
        self.swings_lo: List[Level] = []
        self.zones: List[ZoneBox] = []
        self.trend = 0                     # +1 up, -1 down, 0 unknown
        self.last_sh: Optional[float] = None
        self.last_sl: Optional[float] = None
        self.day: Optional[str] = None
        self.prev_day_bars: List[Bar] = []
        self.today: List[Bar] = []
        self.daily: List[Level] = []
        self.or_hi = self.or_lo = None
        self.or_done = False
        self.pending: Optional[Signal] = None
        self.position: Optional[AITrade] = None
        self.trades: List[AITrade] = []
        self.day_trades: List[AITrade] = []
        self.events: List[Tuple[datetime, str, str]] = []
        self.halted = False

    # ------------------------------------------------------------------ helpers
    def log(self, t: datetime, kind: str, text: str) -> None:
        self.events.append((t, kind, text))

    def _new_day(self, d: str) -> None:
        if self.today:
            self.prev_day_bars = self.today
        self.today = []
        self.day = d
        self.or_hi = self.or_lo = None
        self.or_done = False
        self.day_trades = []
        self.pending = None
        self.halted = False
        self.daily = []
        pv = self.prev_day_bars
        if pv:
            self.daily += [Level(max(b.h for b in pv), "PDH", "high"), Level(min(b.l for b in pv), "PDL", "low"),
                           Level(pv[-1].c, "PDC", "mid")]
            late = [b for b in pv if b.t.time() >= self.p.distribution_from]
            if late:
                self.daily += [Level(max(b.h for b in late), "Prev last-hour high", "high"),
                               Level(min(b.l for b in late), "Prev last-hour low", "low")]

    def levels(self) -> List[Level]:
        out = list(self.daily)
        if self.or_done:
            out += [Level(self.or_hi, "ORH", "high"), Level(self.or_lo, "ORL", "low")]
        out += self.swings_hi + self.swings_lo
        return out

    def bias(self, price: float) -> int:
        """Score from -4 (strongly bearish) to +4 (strongly bullish)."""
        s = self.trend
        pdc = next((l.price for l in self.daily if l.name == "PDC"), None)
        if pdc is not None:
            s += 1 if price > pdc else -1
        if self.today:
            s += 1 if price > self.today[0].o else -1
        if self.or_done:
            s += 1 if price > (self.or_hi + self.or_lo) / 2 else -1
        return s

    def can_open(self, now: datetime) -> bool:
        p = self.p
        losses = sum(1 for t in self.day_trades if t.points < 0)
        return (not self.halted and self.position is None and p.first_entry <= now.time() <= p.last_entry
                and len(self.day_trades) < p.max_trades and losses < p.max_losses)

    # ------------------------------------------------------------------ intrabar
    def on_price(self, price: float, now: datetime, gap_open: bool = False) -> None:
        if self.position is not None:
            self._manage(price, now, gap_open)
            return
        sig = self.pending
        if sig is None or now <= sig.t or now >= sig.valid_until:
            return
        hit = price >= sig.trigger if sig.side == "BUY" else price <= sig.trigger
        if not hit or not self.can_open(now):
            return
        fill = price if gap_open else sig.trigger
        self.pending = None
        risk = (fill - sig.sl) if sig.side == "BUY" else (sig.sl - fill)
        if not (self.p.min_sl_pts <= risk <= self.p.max_sl_pts):
            self.log(now, "skip", f"{sig.side} gap made the stop {risk:.0f} pts")
            return
        t1, t2, t3, room = self._targets(sig.side, fill, risk)
        if room is not None and room < self.p.min_room_r * risk:
            self.log(now, "skip", f"{sig.side} no room: next level only {room / risk:.1f}R away")
            return
        tr = AITrade(sig.side, sig.setup, sig.detail, sig.t, now, fill, sig.sl, t1, t2, t3, sl0=sig.sl)
        self.position = tr
        self.day_trades.append(tr)
        self.log(now, "entry", f"{tr.side} {tr.setup} @ {fill:.1f} | SL {tr.sl:.1f} | T1 {t1:.1f} T2 {t2:.1f} T3 {t3:.1f} | {tr.detail}")

    def _targets(self, side: str, fill: float, risk: float):
        lv = sorted({round(l.price, 1) for l in self.levels()} | {round(z.lo if z.kind == "supply" else z.hi, 1) for z in self.zones
                    if (z.kind == "supply") == (side == "BUY")})
        if side == "BUY":
            opp = [x for x in lv if x > fill + 0.5]
            sgn = 1
        else:
            opp = sorted([x for x in lv if x < fill - 0.5], reverse=True)
            sgn = -1
        room = abs(opp[0] - fill) if opp else None
        if opp and self.p.min_room_r * risk <= abs(opp[0] - fill) <= self.p.t1_max_r * risk:
            t1 = opp[0]
        else:
            t1 = fill + sgn * 2 * risk
        beyond = [x for x in opp if sgn * (x - t1) >= 0.5 * risk]
        t2 = beyond[0] if beyond and abs(beyond[0] - fill) <= 5 * risk else t1 + sgn * risk
        t3 = fill + sgn * max(4 * risk, abs(t2 - fill) + risk)
        return t1, t2, t3, room

    def _manage(self, price: float, now: datetime, gap_open: bool) -> None:
        tr = self.position
        buy = tr.side == "BUY"
        stop_hit = price <= tr.sl if buy else price >= tr.sl
        if stop_hit:
            px = price if gap_open else tr.sl
            return self._close(now, px, "stop" if tr.sl == tr.sl0 else "breakeven")
        tgt = tr.t2 if tr.half_done else tr.t1
        if (price >= tgt) if buy else (price <= tgt):
            px = price if gap_open else tgt
            if self.p.exit_mode == "split" and not tr.half_done:
                tr.half_done, tr.half_exit, tr.half_t, tr.sl = True, px, now, tr.entry
                self.log(now, "t1", f"{tr.side} T1 {px:.1f}: half booked, stop to entry")
            else:
                self._close(now, px, "T2" if tr.half_done else "T1")

    def _close(self, now: datetime, px: float, reason: str) -> None:
        tr = self.position
        tr.closed, tr.reason = now, reason
        tr.exit = (tr.half_exit + px) / 2 if tr.half_done else px
        self.trades.append(tr)
        self.position = None
        self.log(now, "exit", f"{tr.side} {reason} @ {px:.1f} ({tr.r:+.2f}R)")

    def force_exit(self, now: datetime, px: float, reason: str) -> None:
        if self.position is not None:
            self._close(now, px, reason)

    # ------------------------------------------------------------------ bar close
    def on_bar(self, b: Bar) -> None:
        p = self.p
        d = b.t.date().isoformat()
        if d != self.day:
            if self.position is not None and self.bars:
                self._close(self.bars[-1].t, self.bars[-1].c, "square-off")
            self._new_day(d)
        prev = self.bars[-1] if self.bars else None
        atr_prev = self.atr
        self.bars.append(b)
        self.today.append(b)
        tr = max(b.h - b.l, abs(b.h - prev.c), abs(b.l - prev.c)) if prev else b.h - b.l
        self.atr = tr if self.atr is None else self.atr + (tr - self.atr) / p.atr_len
        atr = atr_prev or self.atr
        end = b.t + timedelta(minutes=p.timeframe_min)

        # opening range
        if not self.or_done:
            self.or_hi = b.h if self.or_hi is None else max(self.or_hi, b.h)
            self.or_lo = b.l if self.or_lo is None else min(self.or_lo, b.l)
            if (end.hour * 60 + end.minute) >= 9 * 60 + 15 + p.or_minutes:
                self.or_done = True

        # position housekeeping
        if self.position is not None:
            tr_ = self.position
            if end.time() >= p.square_off:
                self._close(b.t, b.c, "square-off")
            elif not tr_.half_done and p.exit_mode == "T1":
                move = (b.h - tr_.entry) if tr_.side == "BUY" else (tr_.entry - b.l)
                if move >= tr_.risk and tr_.sl == tr_.sl0:
                    tr_.sl = tr_.entry  # his rule: once it has moved one stop-distance, stop to entry

        if self.pending is not None and end >= self.pending.valid_until:
            self.pending = None

        # signal detection uses the structure as it was BEFORE this candle
        sig = self._detect(b, prev, atr, end)

        # update liquidity (sweeps), structure, zones, swings with this candle
        self._update_structure(b, atr)

        if sig and self.position is None and self.pending is None and self.can_open(end):
            if self.p.use_bias_filter:
                sc = self.bias(b.c)
                if (sig.side == "BUY" and sc < 0) or (sig.side == "SELL" and sc > 0):
                    self.log(b.t, "skip", f"{sig.side} {sig.setup} against bias {sc:+d}")
                    sig = None
            if sig:
                self.pending = sig
                self.log(b.t, "signal", f"{sig.side} {sig.setup}: {sig.detail}; enter if next candle breaks "
                                        f"{sig.trigger:.1f}; SL {sig.sl:.1f}")

    def _candle(self, b: Bar, prev: Optional[Bar]) -> Dict[str, bool]:
        rng = b.h - b.l
        body = abs(b.c - b.o)
        up_w = b.h - max(b.o, b.c)
        lo_w = min(b.o, b.c) - b.l
        p = self.p
        bull_pin = rng > 0 and lo_w >= p.pin_wick_body * body and lo_w >= p.pin_wick_range * rng
        bear_pin = rng > 0 and up_w >= p.pin_wick_body * body and up_w >= p.pin_wick_range * rng
        bull_eng = bool(prev) and b.c > b.o and prev.c < prev.o and b.c >= prev.o and b.o <= prev.c
        bear_eng = bool(prev) and b.c < b.o and prev.c > prev.o and b.c <= prev.o and b.o >= prev.c
        return dict(bull_pin=bull_pin, bear_pin=bear_pin, bull_eng=bull_eng, bear_eng=bear_eng,
                    bull_rej=bull_pin or bull_eng, bear_rej=bear_pin or bear_eng, rng=rng, body=body)

    def _detect(self, b: Bar, prev: Optional[Bar], atr: float, end: datetime) -> Optional[Signal]:
        p = self.p
        c = self._candle(b, prev)
        valid = end + timedelta(minutes=p.timeframe_min * p.confirm_bars)
        pat_b = "pin bar" if c["bull_pin"] else "engulfing"
        pat_s = "pin bar" if c["bear_pin"] else "engulfing"
        lv = self.levels()
        # 1. liquidity sweep (trap)
        if c["bull_rej"]:
            swept = [l for l in lv if l.side == "low" and b.l < l.price - p.sweep_min_pts and b.c > l.price]
            if swept:
                l = min(swept, key=lambda x: x.price)
                return self._mk(b, "BUY", "SWEEP", f"swept {l.name} {l.price:.0f} + {pat_b}", b.l - p.sl_buffer, valid)
        if c["bear_rej"]:
            swept = [l for l in lv if l.side == "high" and b.h > l.price + p.sweep_min_pts and b.c < l.price]
            if swept:
                l = max(swept, key=lambda x: x.price)
                return self._mk(b, "SELL", "SWEEP", f"swept {l.name} {l.price:.0f} + {pat_s}", b.h + p.sl_buffer, valid)
        # 2. first touch of a fresh demand / supply zone
        if c["bull_rej"] and self.trend >= 0:
            for z in self.zones:
                if z.kind == "demand" and not z.touched and b.l <= z.hi and b.c > z.lo:
                    return self._mk(b, "BUY", "ZONE", f"first touch of demand {z.lo:.0f}-{z.hi:.0f} + {pat_b}",
                                    min(b.l, z.lo) - p.sl_buffer, valid)
        if c["bear_rej"] and self.trend <= 0:
            for z in self.zones:
                if z.kind == "supply" and not z.touched and b.h >= z.lo and b.c < z.hi:
                    return self._mk(b, "SELL", "ZONE", f"first touch of supply {z.lo:.0f}-{z.hi:.0f} + {pat_s}",
                                    max(b.h, z.hi) + p.sl_buffer, valid)
        # 3. breakout of a key level with a strong close
        if c["rng"] > 0 and c["body"] >= p.breakout_body * c["rng"]:
            ref_lo = min(b.o, prev.c) if prev else b.o
            ref_hi = max(b.o, prev.c) if prev else b.o
            if b.c > b.o:
                br = [l for l in lv if l.side in ("high", "mid") and ref_lo <= l.price < b.c]
                if br:
                    l = max(br, key=lambda x: x.price)
                    return self._mk(b, "BUY", "BREAKOUT", f"closed above {l.name} {l.price:.0f}", b.l - p.sl_buffer, valid)
            elif b.c < b.o:
                br = [l for l in lv if l.side in ("low", "mid") and b.c < l.price <= ref_hi]
                if br:
                    l = min(br, key=lambda x: x.price)
                    return self._mk(b, "SELL", "BREAKOUT", f"closed below {l.name} {l.price:.0f}", b.h + p.sl_buffer, valid)
        return None

    def _mk(self, b: Bar, side: str, setup: str, detail: str, sl: float, valid: datetime) -> Optional[Signal]:
        trig = b.h + self.p.trigger_buffer if side == "BUY" else b.l - self.p.trigger_buffer
        risk = abs(trig - sl)
        if not (self.p.min_sl_pts <= risk <= self.p.max_sl_pts):
            self.log(b.t, "skip", f"{side} {setup} ({detail}): stop {risk:.0f} pts outside "
                                  f"{self.p.min_sl_pts:g}-{self.p.max_sl_pts:g}")
            return None
        return Signal(b.t, side, setup, detail, trig, sl, valid)

    def _update_structure(self, b: Bar, atr: float) -> None:
        p = self.p
        # sweeps remove liquidity
        self.swings_hi = [l for l in self.swings_hi if b.h <= l.price + p.sweep_min_pts]
        self.swings_lo = [l for l in self.swings_lo if b.l >= l.price - p.sweep_min_pts]
        # market structure
        if self.last_sh is not None and b.c > self.last_sh:
            self.trend = 1
        if self.last_sl is not None and b.c < self.last_sl:
            self.trend = -1
        # zones: touched / invalidated
        keep = []
        for z in self.zones:
            if z.kind == "demand":
                if b.c < z.lo:
                    continue
                if b.l <= z.hi and b.t > z.t:
                    z.touched = True
            else:
                if b.c > z.hi:
                    continue
                if b.h >= z.lo and b.t > z.t:
                    z.touched = True
            keep.append(z)
        self.zones = keep
        # new zone from a displacement candle
        n = len(self.bars)
        if atr and abs(b.c - b.o) >= p.disp_atr * atr and n >= 2:
            bull = b.c > b.o
            base = None
            for k in range(n - 2, max(-1, n - 5), -1):
                x = self.bars[k]
                if (x.c < x.o) == bull:
                    base = x
                    break
            base = base or self.bars[n - 2]
            self.zones.append(ZoneBox(base.l, base.h, "demand" if bull else "supply", b.t))
            dem = [z for z in self.zones if z.kind == "demand"][-p.max_zones:]
            sup = [z for z in self.zones if z.kind == "supply"][-p.max_zones:]
            self.zones = dem + sup
        # confirmed swing high / low pivot_len bars ago
        L = p.pivot_len
        if n >= 2 * L + 1:
            mid = self.bars[n - 1 - L]
            left = self.bars[n - 1 - 2 * L:n - 1 - L]
            right = self.bars[n - L:]
            if all(mid.h > x.h for x in left) and all(mid.h >= x.h for x in right):
                eq = any(abs(s.price - mid.h) <= p.eq_tol_atr * (atr or 0) for s in self.swings_hi)
                self.swings_hi.append(Level(mid.h, "equal highs" if eq else "swing high", "high", True, mid.t))
                self.swings_hi = self.swings_hi[-p.max_swings:]
                self.last_sh = mid.h
            if all(mid.l < x.l for x in left) and all(mid.l <= x.l for x in right):
                eq = any(abs(s.price - mid.l) <= p.eq_tol_atr * (atr or 0) for s in self.swings_lo)
                self.swings_lo.append(Level(mid.l, "equal lows" if eq else "swing low", "low", True, mid.t))
                self.swings_lo = self.swings_lo[-p.max_swings:]
                self.last_sl = mid.l


def run(bars: List[Bar], p: Optional[AIParams] = None) -> AllInOne:
    """Backtest over a continuous list of completed candles (several days)."""
    e = AllInOne(p)
    for b in bars:
        if e.day is not None and b.t.date().isoformat() != e.day and e.position is not None:
            e._close(e.bars[-1].t, e.bars[-1].c, "square-off")
        for k, px in enumerate(bar_path(b)):
            if e.day == b.t.date().isoformat():
                e.on_price(px, b.t, gap_open=(k == 0))
        e.on_bar(b)
    if e.position is not None:
        e._close(e.bars[-1].t, e.bars[-1].c, "square-off")
    return e

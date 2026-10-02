"""TCI Smart Money (v2): liquidity-map signals for the 5-minute index chart.

Reference implementation of tradingview/tci_smart_money.pine (same rules, so it can be backtested).

Liquidity pool (levels where stop-losses gather, kept until price trades through them):
  * high / low of each of the last 5 sessions, previous week's high / low
  * major swing highs / lows (6 candles each side = 30 min on 5-min), "equal" when two match
  * today's opening range (first 15 min) once it is complete, previous close (gap fill)
Signals (BUY = call, SELL = put):
  * TRAP    price runs through a pool level and the candle closes back with a rejection
            (pin bar, engulfing, or a close in the far 40% of the candle) -> trade the other way
  * BREAK   a strong candle (body >= 50% of range, range >= 0.8 ATR) closes through a pool level
  * RETEST  a level broken in the last hour is retested and holds with a rejection candle
Entry only when one of the next `confirm_bars` candles breaks the signal candle (his follow-up rule).
Risk: SL beyond the signal candle / swept extreme, at least `min_sl` (25) and at most `max_sl` (60) points.
Targets: T1 = first opposing pool level at least `min_t1` (50) points away (else entry +/- max(50, 2R));
MAX = the next pool level beyond T1 (the big liquidity), else T1 + (T1 - entry).
Management: stop to entry after 1R; after T1 the stop trails `trail_atr` x ATR behind the best price
(like a Supertrend line); exit at MAX, the trailing stop, or 15:15.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Tuple

from .rules import Bar, bar_path

DAYNAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


@dataclass
class SMParams:
    timeframe_min: int = 5
    atr_len: int = 14
    major_len: int = 6
    sessions_kept: int = 5
    max_swings: int = 10
    eq_tol_atr: float = 0.25
    sweep_min: float = 2.0
    rej_frac: float = 0.4
    pin_wick_body: float = 2.0
    pin_wick_range: float = 0.5
    brk_body: float = 0.5
    brk_range_atr: float = 0.8
    retest_bars: int = 12
    retest_tol_atr: float = 0.3
    confirm_bars: int = 2
    trigger_buffer: float = 1.0
    sl_buffer: float = 2.0
    min_sl: float = 25.0
    max_sl: float = 60.0
    min_t1: float = 50.0
    be_at_r: float = 1.0
    trail_atr: float = 2.0
    exit_mode: str = "trail"     # "trail": trail after T1 to MAX | "t1": full exit at T1
    or_minutes: int = 15
    first_entry: time = time(9, 20)
    last_entry: time = time(14, 45)
    square_off: time = time(15, 15)
    max_trades: int = 4
    max_losses: int = 2
    use_trap: bool = True
    use_break: bool = True
    use_retest: bool = True


@dataclass
class PoolLevel:
    price: float
    name: str
    side: str                  # "high" | "low" | "mid"
    born: datetime
    major: bool = True


@dataclass
class SMSignal:
    t: datetime
    side: str
    setup: str
    detail: str
    trigger: float
    sl_struct: float
    valid_until: datetime


@dataclass
class SMTrade:
    side: str
    setup: str
    detail: str
    opened: datetime
    entry: float
    sl0: float
    t1: float
    tmax: float
    sl: float = 0.0
    best: float = 0.0
    t1_hit: bool = False
    closed: Optional[datetime] = None
    exit: float = 0.0
    reason: str = ""
    t1_t: Optional[datetime] = None

    @property
    def risk(self) -> float:
        return abs(self.entry - self.sl0)

    @property
    def points(self) -> float:
        return (self.exit - self.entry) if self.side == "BUY" else (self.entry - self.exit)

    @property
    def r(self) -> float:
        return self.points / self.risk if self.risk else 0.0


class SmartMoney:
    def __init__(self, p: Optional[SMParams] = None):
        self.p = p or SMParams()
        self.bars: List[Bar] = []
        self.atr: Optional[float] = None
        self.sessions: List[Tuple[str, float, float, float]] = []   # (date, high, low, close) of finished sessions
        self.day: Optional[str] = None
        self.today: List[Bar] = []
        self.pool: List[PoolLevel] = []
        self.broken: List[Tuple[PoolLevel, str, int]] = []           # (level, direction, bar number when broken)
        self.or_done = False
        self.trend = 0
        self.last_sh = self.last_sl = None
        self.pending: Optional[SMSignal] = None
        self.position: Optional[SMTrade] = None
        self.trades: List[SMTrade] = []
        self.day_trades: List[SMTrade] = []
        self.events: List[Tuple[datetime, str, str]] = []
        self.week_hl: Dict[Tuple[int, int], List[float]] = {}

    # ---------------------------------------------------------------- helpers
    def log(self, t, kind, text):
        self.events.append((t, kind, text))

    def _new_day(self, b: Bar) -> None:
        if self.today:
            d = self.today[0].t
            self.sessions.append((d.date().isoformat(), max(x.h for x in self.today), min(x.l for x in self.today), self.today[-1].c))
            self.sessions = self.sessions[-self.p.sessions_kept:]
        self.today = []
        self.day = b.t.date().isoformat()
        self.or_done = False
        self.pending = None
        self.day_trades = []
        # rebuild the session part of the pool: keep only levels not yet taken
        keep = [l for l in self.pool if "swing" in l.name or "equal" in l.name]   # intraday swings carry over
        lv: List[PoolLevel] = []
        start = datetime.combine(b.t.date(), time(9, 0))   # "born" before today's first candle
        for i, (d, h, lo, c) in enumerate(reversed(self.sessions)):
            dd = datetime.fromisoformat(d)
            tag = "PD" if i == 0 else DAYNAMES[dd.weekday()] + " "
            hi_name, lo_name = ("PDH", "PDL") if i == 0 else (tag + "high", tag + "low")
            if self._untouched_since(h, "high", d):
                lv.append(PoolLevel(h, hi_name, "high", start))
            if self._untouched_since(lo, "low", d):
                lv.append(PoolLevel(lo, lo_name, "low", start))
            if i == 0:
                lv.append(PoolLevel(c, "PDC", "mid", start))
        wk = b.t.isocalendar()[:2]
        prev = [(k, v) for k, v in sorted(self.week_hl.items()) if k < wk]
        if prev:
            (_, (wh, wl, wlast)) = prev[-1]
            if self._untouched_since(wh, "high", wlast):
                lv.append(PoolLevel(wh, "PWH", "high", start))
            if self._untouched_since(wl, "low", wlast):
                lv.append(PoolLevel(wl, "PWL", "low", start))
        self.pool = keep + lv

    def _untouched_since(self, price: float, side: str, d: str) -> bool:
        later = [x for x in self.bars if x.t.date().isoformat() > d]
        if side == "high":
            return all(x.h <= price + self.p.sweep_min for x in later)
        return all(x.l >= price - self.p.sweep_min for x in later)

    def can_open(self, now: datetime) -> bool:
        p = self.p
        losses = sum(1 for t in self.day_trades if t.points < 0)
        return (self.position is None and p.first_entry <= now.time() <= p.last_entry
                and len(self.day_trades) < p.max_trades and losses < p.max_losses)

    def levels_beyond(self, side: str, price: float) -> List[PoolLevel]:
        if side == "BUY":
            return sorted([l for l in self.pool if l.price > price + 0.5], key=lambda l: l.price)
        return sorted([l for l in self.pool if l.price < price - 0.5], key=lambda l: -l.price)

    def liquidity_map(self, price: float, n: int = 3) -> Dict[str, List[PoolLevel]]:
        """Nearest untouched liquidity above and below, including the current session's high / low
        (before the open these are the last session's high / low: the levels to watch at 9:15)."""
        lv = list(self.pool)
        if self.today:
            t0 = self.today[0].t
            lv += [PoolLevel(max(x.h for x in self.today), "day high", "high", t0),
                   PoolLevel(min(x.l for x in self.today), "day low", "low", t0)]
        def nearest(cands):
            out: List[PoolLevel] = []
            for l in cands:                       # merge levels within 3 points into one ("PDH + swing high")
                same = next((o for o in out if abs(o.price - l.price) <= 3), None)
                if same is None:
                    out.append(PoolLevel(l.price, l.name, l.side, l.born))
                elif l.name not in same.name:
                    same.name += " + " + l.name
            return out[:n]

        def fill_rounds(found, up):
            # not enough real levels on this side (e.g. at a fresh multi-day low): use round 100s beyond the last one
            base = found[-1].price if found else price
            while len(found) < n:
                base = (int(base // 100) + 1) * 100 if up else (int(-(-base // 100)) - 1) * 100
                if all(abs(base - l.price) > 3 for l in found):
                    found.append(PoolLevel(float(base), "round number", "high" if up else "low", self.bars[-1].t))
            return found
        above = fill_rounds(nearest(sorted([l for l in lv if l.price > price + 0.5], key=lambda l: l.price)), True)
        below = fill_rounds(nearest(sorted([l for l in lv if l.price < price - 0.5], key=lambda l: -l.price)), False)
        return {"above": above, "below": below}

    # ---------------------------------------------------------------- intrabar
    def on_price(self, px: float, now: datetime, gap_open: bool = False) -> None:
        if self.position is not None:
            return self._manage(px, now, gap_open)
        s = self.pending
        if s is None or now <= s.t or now >= s.valid_until:
            return
        hit = px >= s.trigger if s.side == "BUY" else px <= s.trigger
        if not hit or not self.can_open(now):
            return
        self.pending = None
        fill = px if gap_open else s.trigger
        sgn = 1 if s.side == "BUY" else -1
        dist = max(self.p.min_sl, sgn * (fill - s.sl_struct))
        if dist > self.p.max_sl:
            self.log(now, "skip", f"{s.side} {s.setup}: stop would be {dist:.0f} pts")
            return
        sl = fill - sgn * dist
        opp = self.levels_beyond(s.side, fill)
        far = [l for l in opp if abs(l.price - fill) >= self.p.min_t1]
        t1 = far[0].price if far else fill + sgn * max(self.p.min_t1, 2 * dist)
        beyond = [l for l in opp if sgn * (l.price - t1) >= 25]
        tmax = beyond[0].price if beyond else t1 + (t1 - fill)
        tr = SMTrade(s.side, s.setup, s.detail, now, fill, sl, t1, tmax, sl=sl, best=fill)
        self.position = tr
        self.day_trades.append(tr)
        self.log(now, "entry", f"{tr.side} {tr.setup} @ {fill:.1f} SL {sl:.1f} T1 {t1:.1f} MAX {tmax:.1f} | {tr.detail}")

    def _manage(self, px: float, now: datetime, gap_open: bool) -> None:
        tr = self.position
        buy = tr.side == "BUY"
        if (px <= tr.sl) if buy else (px >= tr.sl):
            out = px if gap_open else tr.sl
            reason = "stop" if tr.sl == tr.sl0 else ("trail" if tr.t1_hit else "breakeven")
            return self._close(now, out, reason)
        tgt = tr.tmax if (tr.t1_hit and self.p.exit_mode == "trail") else tr.t1
        if (px >= tgt) if buy else (px <= tgt):
            out = px if gap_open else tgt
            if self.p.exit_mode == "trail" and not tr.t1_hit:
                tr.t1_hit, tr.t1_t = True, now
                tr.sl = max(tr.sl, tr.entry) if buy else min(tr.sl, tr.entry)
                self.log(now, "t1", f"{tr.side} T1 {out:.1f}: trailing to MAX {tr.tmax:.1f}")
            else:
                self._close(now, out, "MAX" if tr.t1_hit else "T1")

    def _close(self, now, px, reason):
        tr = self.position
        tr.closed, tr.exit, tr.reason = now, px, reason
        self.trades.append(tr)
        self.position = None
        self.log(now, "exit", f"{tr.side} {reason} @ {px:.1f} ({tr.points:+.0f} pts, {tr.r:+.2f}R)")

    # ---------------------------------------------------------------- bar close
    def on_bar(self, b: Bar) -> None:
        p = self.p
        if b.t.date().isoformat() != self.day:
            if self.position is not None and self.bars:
                self._close(self.bars[-1].t, self.bars[-1].c, "square-off")
            self._new_day(b)
        prev = self.bars[-1] if self.bars else None
        atr_prev = self.atr
        self.bars.append(b)
        self.today.append(b)
        wk = b.t.isocalendar()[:2]
        w = self.week_hl.setdefault(wk, [b.h, b.l, self.day])
        w[0], w[1], w[2] = max(w[0], b.h), min(w[1], b.l), self.day   # week high, low, last date seen
        tr_ = max(b.h - b.l, abs(b.h - prev.c), abs(b.l - prev.c)) if prev else b.h - b.l
        self.atr = tr_ if self.atr is None else self.atr + (tr_ - self.atr) / p.atr_len
        atr = atr_prev or self.atr
        end = b.t + timedelta(minutes=p.timeframe_min)

        if not self.or_done and (end.hour * 60 + end.minute) >= 9 * 60 + 15 + p.or_minutes:
            self.or_done = True
            self.pool.append(PoolLevel(max(x.h for x in self.today), "ORH", "high", b.t))
            self.pool.append(PoolLevel(min(x.l for x in self.today), "ORL", "low", b.t))

        # position housekeeping
        if self.position is not None:
            tr = self.position
            buy = tr.side == "BUY"
            if end.time() >= p.square_off:
                self._close(b.t, b.c, "square-off")
            else:
                tr.best = max(tr.best, b.h) if buy else min(tr.best, b.l)
                if tr.sl == tr.sl0 and (tr.best - tr.entry if buy else tr.entry - tr.best) >= p.be_at_r * tr.risk:
                    tr.sl = tr.entry
                if tr.t1_hit and p.exit_mode == "trail":
                    trail = tr.best - p.trail_atr * self.atr if buy else tr.best + p.trail_atr * self.atr
                    tr.sl = max(tr.sl, trail) if buy else min(tr.sl, trail)
        if self.pending is not None and end >= self.pending.valid_until:
            self.pending = None

        sig = self._detect(b, prev, atr, end)
        self._update_pool(b, prev, atr)
        if sig and self.position is None and self.pending is None and self.can_open(end):
            self.pending = sig
            self.log(b.t, "signal", f"{sig.side} {sig.setup}: {sig.detail}; enter beyond {sig.trigger:.1f}")

    def _rejection(self, b: Bar, prev: Optional[Bar], bull: bool) -> str:
        rng = b.h - b.l
        if rng <= 0:
            return ""
        body = abs(b.c - b.o)
        up_w, lo_w = b.h - max(b.o, b.c), min(b.o, b.c) - b.l
        p = self.p
        if bull:
            if lo_w >= p.pin_wick_body * body and lo_w >= p.pin_wick_range * rng:
                return "pin bar"
            if prev and b.c > b.o and prev.c < prev.o and b.c >= prev.o and b.o <= prev.c:
                return "engulfing"
            if b.c >= b.h - p.rej_frac * rng:
                return "strong close"
        else:
            if up_w >= p.pin_wick_body * body and up_w >= p.pin_wick_range * rng:
                return "pin bar"
            if prev and b.c < b.o and prev.c > prev.o and b.c <= prev.o and b.o >= prev.c:
                return "engulfing"
            if b.c <= b.l + p.rej_frac * rng:
                return "strong close"
        return ""

    def _detect(self, b: Bar, prev: Optional[Bar], atr: float, end: datetime) -> Optional[SMSignal]:
        p = self.p
        valid = end + timedelta(minutes=p.timeframe_min * p.confirm_bars)
        mk = lambda side, setup, detail, sl: SMSignal(b.t, side, setup, detail,
                                                      b.h + p.trigger_buffer if side == "BUY" else b.l - p.trigger_buffer, sl, valid)
        # 1. trap: run through a pool level, close back with a rejection
        if p.use_trap:
            lows = [l for l in self.pool if l.side == "low" and b.l < l.price - p.sweep_min and b.c > l.price]
            rj = self._rejection(b, prev, True)
            if lows and rj:
                l = min(lows, key=lambda x: x.price)
                return mk("BUY", "TRAP", f"swept {l.name} {l.price:.0f}, {rj}", b.l - p.sl_buffer)
            highs = [l for l in self.pool if l.side == "high" and b.h > l.price + p.sweep_min and b.c < l.price]
            rj = self._rejection(b, prev, False)
            if highs and rj:
                l = max(highs, key=lambda x: x.price)
                return mk("SELL", "TRAP", f"swept {l.name} {l.price:.0f}, {rj}", b.h + p.sl_buffer)
        # 2. retest of a level broken in the last hour
        if p.use_retest:
            n = len(self.bars)
            tol = p.retest_tol_atr * (atr or 0)
            for lvl, direction, k in reversed(self.broken):
                if n - k > p.retest_bars or n - k < 2:
                    continue
                if direction == "up" and b.l <= lvl.price + tol and b.c > lvl.price and self._rejection(b, prev, True):
                    self.broken.remove((lvl, direction, k))
                    return mk("BUY", "RETEST", f"retest of {lvl.name} {lvl.price:.0f} held", min(b.l, lvl.price - tol) - p.sl_buffer)
                if direction == "down" and b.h >= lvl.price - tol and b.c < lvl.price and self._rejection(b, prev, False):
                    self.broken.remove((lvl, direction, k))
                    return mk("SELL", "RETEST", f"retest of {lvl.name} {lvl.price:.0f} held", max(b.h, lvl.price + tol) + p.sl_buffer)
        # 3. strong break through a pool level
        if p.use_break and prev is not None:
            rng = b.h - b.l
            if rng > 0 and abs(b.c - b.o) >= p.brk_body * rng and rng >= p.brk_range_atr * (atr or 0):
                if b.c > b.o:
                    up = [l for l in self.pool if l.side in ("high", "mid") and min(b.o, prev.c) <= l.price < b.c]
                    if up:
                        l = max(up, key=lambda x: x.price)
                        return mk("BUY", "BREAK", f"broke above {l.name} {l.price:.0f}", b.l - p.sl_buffer)
                else:
                    dn = [l for l in self.pool if l.side in ("low", "mid") and b.c < l.price <= max(b.o, prev.c)]
                    if dn:
                        l = min(dn, key=lambda x: x.price)
                        return mk("SELL", "BREAK", f"broke below {l.name} {l.price:.0f}", b.h + p.sl_buffer)
        return None

    def _update_pool(self, b: Bar, prev: Optional[Bar], atr: float) -> None:
        p = self.p
        n = len(self.bars)
        keep = []
        for l in self.pool:
            if b.t <= l.born:
                keep.append(l)
                continue
            if l.side in ("high", "mid") and b.c > l.price + p.sweep_min and (prev is None or prev.c <= l.price):
                self.broken.append((l, "up", n))
            if l.side in ("low", "mid") and b.c < l.price - p.sweep_min and (prev is None or prev.c >= l.price):
                self.broken.append((l, "down", n))
            taken = (l.side == "high" and b.h > l.price + p.sweep_min) or (l.side == "low" and b.l < l.price - p.sweep_min) \
                or (l.side == "mid" and b.l < l.price < b.h)
            if not taken:
                keep.append(l)
        self.pool = keep
        self.broken = [x for x in self.broken if n - x[2] <= p.retest_bars]
        if self.last_sh is not None and b.c > self.last_sh:
            self.trend = 1
        if self.last_sl is not None and b.c < self.last_sl:
            self.trend = -1
        L = p.major_len
        if n >= 2 * L + 1:
            mid = self.bars[n - 1 - L]
            left, right = self.bars[n - 1 - 2 * L:n - 1 - L], self.bars[n - L:]
            tol = p.eq_tol_atr * (atr or 0)
            if all(mid.h > x.h for x in left) and all(mid.h >= x.h for x in right):
                eq = any(abs(l.price - mid.h) <= tol for l in self.pool if l.side == "high")
                self.pool.append(PoolLevel(mid.h, "equal highs" if eq else "swing high", "high", b.t))
                self.last_sh = mid.h
            if all(mid.l < x.l for x in left) and all(mid.l <= x.l for x in right):
                eq = any(abs(l.price - mid.l) <= tol for l in self.pool if l.side == "low")
                self.pool.append(PoolLevel(mid.l, "equal lows" if eq else "swing low", "low", b.t))
                self.last_sl = mid.l
            sw_hi = [l for l in self.pool if l.name in ("swing high", "equal highs")]
            sw_lo = [l for l in self.pool if l.name in ("swing low", "equal lows")]
            drop = sw_hi[:-p.max_swings] + sw_lo[:-p.max_swings]
            if drop:
                self.pool = [l for l in self.pool if l not in drop]


def run(bars: List[Bar], p: Optional[SMParams] = None) -> SmartMoney:
    e = SmartMoney(p)
    for b in bars:
        same_day = e.day == b.t.date().isoformat()
        for k, px in enumerate(bar_path(b)):
            if same_day:
                e.on_price(px, b.t, gap_open=(k == 0))
        e.on_bar(b)
    if e.position is not None:
        e._close(e.bars[-1].t, e.bars[-1].c, "square-off")
    return e

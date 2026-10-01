"""Thin wrapper over Groww's official `growwapi` SDK (pip install growwapi).

Only the calls this system needs: login, index price, candles, option selection,
orders. Method names and response fields follow Groww's Python SDK docs
(https://groww.in/trade-api/docs/python-sdk); if Groww changes them, fix them here.
"""
from __future__ import annotations

import os
import time as _time
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from .rules import Bar

UNDERLYINGS = {
    # name: (exchange, index trading symbol, groww symbol, step between strikes)
    "NIFTY": ("NSE", "NIFTY", "NSE-NIFTY", 50),
    "SENSEX": ("BSE", "SENSEX", "BSE-SENSEX", 100),
}


def login():
    """Return an authenticated GrowwAPI client using environment variables.

    Either GROWW_TOTP_TOKEN + GROWW_TOTP_SECRET (TOTP flow, no daily approval), or
    GROWW_API_KEY + GROWW_API_SECRET (needs approval on the Groww Cloud API keys page each day).
    """
    from growwapi import GrowwAPI

    if os.getenv("GROWW_TOTP_TOKEN"):
        import pyotp

        totp = pyotp.TOTP(os.environ["GROWW_TOTP_SECRET"]).now()
        token = GrowwAPI.get_access_token(api_key=os.environ["GROWW_TOTP_TOKEN"], totp=totp)
    elif os.getenv("GROWW_API_KEY"):
        token = GrowwAPI.get_access_token(api_key=os.environ["GROWW_API_KEY"], secret=os.environ["GROWW_API_SECRET"])
    else:
        raise SystemExit("Set GROWW_TOTP_TOKEN/GROWW_TOTP_SECRET or GROWW_API_KEY/GROWW_API_SECRET (see README).")
    return GrowwAPI(token)


def _tick(x: float) -> float:
    return round(round(x / 0.05) * 0.05, 2)


class GrowwClient:
    def __init__(self, api, underlying: str = "NIFTY"):
        self.g = api
        self.exchange, self.index_symbol, self.index_groww_symbol, self.step = UNDERLYINGS[underlying]
        self.underlying = underlying

    # ---- market data --------------------------------------------------------
    def index_ltp(self) -> float:
        key = f"{self.exchange}_{self.index_symbol}"
        r = self.g.get_ltp(segment=self.g.SEGMENT_CASH, exchange_trading_symbols=key)
        return float(r[key])

    def option_ltp(self, trading_symbol: str) -> float:
        key = f"{self.exchange}_{trading_symbol}"
        r = self.g.get_ltp(segment=self.g.SEGMENT_FNO, exchange_trading_symbols=key)
        return float(r[key])

    def candles(self, groww_symbol: str, segment: str, start: datetime, end: datetime, minutes: int) -> List[Bar]:
        interval = {1: "1minute", 2: "2minute", 3: "3minute", 5: "5minute", 10: "10minute",
                    15: "15minute", 30: "30minute", 60: "1hour"}[minutes]
        r = self.g.get_historical_candles(
            exchange=self.exchange, segment=segment, groww_symbol=groww_symbol,
            start_time=start.strftime("%Y-%m-%d %H:%M:%S"), end_time=end.strftime("%Y-%m-%d %H:%M:%S"),
            candle_interval=interval)
        out = []
        for row in r.get("candles") or []:
            ts = datetime.fromisoformat(str(row[0]).replace("Z", ""))
            out.append(Bar(ts, float(row[1]), float(row[2]), float(row[3]), float(row[4])))
        return out

    def index_candles(self, day: date, minutes: int, until: Optional[datetime] = None) -> List[Bar]:
        start = datetime.combine(day, datetime.min.time()).replace(hour=9, minute=15)
        end = until or start.replace(hour=15, minute=30)
        return self.candles(self.index_groww_symbol, self.g.SEGMENT_CASH, start, end, minutes)

    def previous_session(self, day: date, minutes: int) -> Tuple[date, List[Bar]]:
        d = day
        for _ in range(10):
            d -= timedelta(days=1)
            if d.weekday() >= 5:
                continue
            bars = self.index_candles(d, minutes)
            if bars:
                return d, bars
        raise RuntimeError("no previous session found in the last 10 days")

    # ---- options -------------------------------------------------------------
    def nearest_expiry(self, day: date) -> str:
        found: List[str] = []
        for y, m in {(day.year, day.month), ((day + timedelta(days=32)).year, (day + timedelta(days=32)).month)}:
            r = self.g.get_expiries(exchange=self.exchange, underlying_symbol=self.underlying, year=y, month=m)
            found += r.get("expiries", [])
        future = sorted(e for e in found if e >= day.isoformat())
        if not future:
            raise RuntimeError("no expiry found")
        return future[0]

    def pick_option(self, side: str, spot: float, expiry: str, target_premium: float = 150.0,
                    max_steps_itm: int = 6) -> Dict:
        """Slightly in-the-money option whose premium is closest to `target_premium` (his ~Rs 150 rule)."""
        chain = self.g.get_option_chain(exchange=self.exchange, underlying=self.underlying, expiry_date=expiry)
        atm = round(spot / self.step) * self.step
        best = None
        for k_str, legs in (chain.get("strikes") or {}).items():
            k = float(k_str)
            itm_steps = (atm - k) / self.step if side == "CE" else (k - atm) / self.step
            if itm_steps < 0 or itm_steps > max_steps_itm:
                continue
            leg = legs.get(side) or {}
            ltp = leg.get("ltp")
            if not ltp:
                continue
            cand = {"trading_symbol": leg["trading_symbol"], "strike": k, "ltp": float(ltp),
                    "delta": abs(float((leg.get("greeks") or {}).get("delta") or 0.5)), "expiry": expiry}
            if best is None or abs(cand["ltp"] - target_premium) < abs(best["ltp"] - target_premium):
                best = cand
        if best is None:
            raise RuntimeError(f"no {side} strike found near {spot}")
        return best

    # ---- orders --------------------------------------------------------------
    def place_limit(self, trading_symbol: str, qty: int, buy: bool, price: float, ref: str) -> str:
        g = self.g
        r = g.place_order(
            trading_symbol=trading_symbol, quantity=qty, validity=g.VALIDITY_DAY, exchange=self.exchange,
            segment=g.SEGMENT_FNO, product=g.PRODUCT_MIS, order_type=g.ORDER_TYPE_LIMIT,
            transaction_type=g.TRANSACTION_TYPE_BUY if buy else g.TRANSACTION_TYPE_SELL,
            price=_tick(price), order_reference_id=ref)
        return r["groww_order_id"]

    def place_stop_market(self, trading_symbol: str, qty: int, trigger: float, ref: str) -> str:
        """Protective sell stop held at the exchange, in case this program dies."""
        g = self.g
        r = g.place_order(
            trading_symbol=trading_symbol, quantity=qty, validity=g.VALIDITY_DAY, exchange=self.exchange,
            segment=g.SEGMENT_FNO, product=g.PRODUCT_MIS, order_type=g.ORDER_TYPE_STOP_LOSS_MARKET,
            transaction_type=g.TRANSACTION_TYPE_SELL, price=0.0, trigger_price=_tick(trigger), order_reference_id=ref)
        return r["groww_order_id"]

    def order(self, order_id: str) -> Dict:
        return self.g.get_order_detail(groww_order_id=order_id, segment=self.g.SEGMENT_FNO)

    def cancel(self, order_id: str) -> None:
        try:
            self.g.cancel_order(groww_order_id=order_id, segment=self.g.SEGMENT_FNO)
        except Exception as e:  # already executed / cancelled
            print(f"cancel {order_id}: {e}")

    def wait_fill(self, order_id: str, timeout_s: float = 8.0) -> Tuple[str, int, float]:
        done = {"EXECUTED", "COMPLETED"}
        dead = {"REJECTED", "FAILED", "CANCELLED"}
        t0 = _time.time()
        while True:
            d = self.order(order_id)
            st = d.get("order_status", "")
            if st in done or st in dead or _time.time() - t0 > timeout_s:
                return st, int(d.get("filled_quantity") or 0), float(d.get("average_fill_price") or 0)
            _time.sleep(0.5)

    def open_fno_positions(self) -> List[Dict]:
        r = self.g.get_positions_for_user(segment=self.g.SEGMENT_FNO)
        return [p for p in r.get("positions", []) if int(p.get("quantity") or 0) != 0]

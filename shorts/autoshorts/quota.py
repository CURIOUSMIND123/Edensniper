"""Quota and rate-limit handling.

This is the piece that lets you close the laptop. When the API says
"you're done for now", we work out *how long* for, write that deadline to
the database, and sleep. A restart mid-sleep reads the deadline back and
keeps waiting instead of hammering the API and burning the account.
"""
from __future__ import annotations

import datetime as dt
import random
import re
import time
from dataclasses import dataclass

from .db import Store

BLOCKED_UNTIL_KEY = "blocked_until"

# Substrings that mean "stop asking for a while", not "retry immediately".
_QUOTA_MARKERS = (
    "resource_exhausted",
    "resource has been exhausted",
    "quota",
    "rate limit",
    "too many requests",
    "429",
)
_DAILY_MARKERS = (
    "per day",
    "perday",
    "daily limit",
    "requests per day",
    "generate_requests_per_model_per_day",
)


@dataclass
class Verdict:
    """What to do about an exception."""

    kind: str  # "quota" | "transient" | "fatal"
    wait_seconds: float
    reason: str

    @property
    def retryable(self) -> bool:
        return self.kind in ("quota", "transient")


def _retry_delay_from(text: str) -> float | None:
    """Google returns a RetryInfo like `retryDelay: '37s'` — honour it."""
    match = re.search(r"retry[_ ]?delay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s", text, re.I)
    if match:
        return float(match.group(1))
    match = re.search(r"retry[- ]after['\"]?\s*[:=]\s*['\"]?(\d+)", text, re.I)
    if match:
        return float(match.group(1))
    return None


def seconds_until_daily_reset(reset_hour_utc: int, now: dt.datetime | None = None) -> float:
    now = now or dt.datetime.now(dt.timezone.utc)
    target = now.replace(hour=reset_hour_utc % 24, minute=2, second=0, microsecond=0)
    if target <= now:
        target += dt.timedelta(days=1)
    return (target - now).total_seconds()


def classify(exc: BaseException, cfg, attempts: int = 0) -> Verdict:
    """Decide whether an exception is a quota wall, a blip, or a real bug."""
    text = f"{type(exc).__name__}: {exc}".lower()
    status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    qcfg = cfg["quota"]

    is_quota = status == 429 or any(marker in text for marker in _QUOTA_MARKERS)

    if is_quota:
        hinted = _retry_delay_from(str(exc))
        daily = any(marker in text for marker in _DAILY_MARKERS)
        if daily:
            wait = seconds_until_daily_reset(qcfg["daily_reset_hour_utc"])
            return Verdict("quota", wait, "daily quota exhausted; waiting for reset")
        if hinted:
            return Verdict("quota", hinted + 5, f"rate limited; API asked for {hinted:.0f}s")
        # No hint: back off geometrically but stay inside the configured band.
        wait = min(
            qcfg["max_backoff_seconds"],
            qcfg["min_backoff_seconds"] * (2 ** min(attempts, 5)),
        )
        return Verdict("quota", wait, "rate limited; backing off")

    if status in (500, 502, 503, 504) or any(
        marker in text for marker in ("timeout", "timed out", "deadline", "unavailable",
                                      "connection reset", "temporarily")
    ):
        wait = min(qcfg["max_backoff_seconds"], 15 * (2 ** min(attempts, 5)))
        return Verdict("transient", wait, "transient API/network error")

    return Verdict("fatal", 0, "non-retryable error")


class QuotaGate:
    """Shared cooldown. Every API call goes through `wait_if_blocked` first."""

    def __init__(self, store: Store, cfg, log=print):
        self.store = store
        self.cfg = cfg
        self.log = log

    def blocked_for(self) -> float:
        until = self.store.get_meta(BLOCKED_UNTIL_KEY, 0) or 0
        return max(0.0, float(until) - time.time())

    def block(self, seconds: float, reason: str = "") -> None:
        until = time.time() + max(0.0, seconds)
        current = float(self.store.get_meta(BLOCKED_UNTIL_KEY, 0) or 0)
        if until > current:
            self.store.set_meta(BLOCKED_UNTIL_KEY, until)
        stamp = dt.datetime.fromtimestamp(until).strftime("%H:%M:%S")
        self.log(f"  cooldown {seconds/60:.1f} min (until {stamp}) — {reason}")

    def clear(self) -> None:
        self.store.set_meta(BLOCKED_UNTIL_KEY, 0)

    def wait_if_blocked(self, stop_check=None) -> None:
        """Sleep out any active cooldown, in slices so Ctrl-C still works."""
        remaining = self.blocked_for()
        if remaining <= 0:
            return
        stamp = dt.datetime.fromtimestamp(time.time() + remaining).strftime("%a %H:%M")
        self.log(f"[quota] sleeping {remaining/60:.1f} min, resuming {stamp}")
        while remaining > 0:
            if stop_check and stop_check():
                return
            time.sleep(min(30.0, remaining))
            remaining = self.blocked_for()
        self.log("[quota] cooldown over, resuming")

    def call(self, fn, *args, attempts: int = 0, label: str = "api", **kwargs):
        """Run an API call, translating failures into cooldowns.

        Raises the original exception for fatal errors and for retryable ones
        the caller should record — the caller owns attempt counting, we own
        the sleeping.
        """
        self.wait_if_blocked()
        try:
            result = fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - deliberately broad, we classify
            verdict = classify(exc, self.cfg, attempts)
            if verdict.retryable:
                jitter = random.uniform(0, min(30, verdict.wait_seconds * 0.1))
                self.block(verdict.wait_seconds + jitter, f"{label}: {verdict.reason}")
            raise
        else:
            self.clear()
            return result

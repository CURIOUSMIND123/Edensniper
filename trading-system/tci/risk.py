"""Position sizing and hard stops that sit above the strategy rules."""
from __future__ import annotations

import math
import os
from dataclasses import dataclass


@dataclass
class RiskConfig:
    capital: float = 50_000.0          # money set aside for this strategy
    risk_per_trade_pct: float = 1.0    # % of capital lost if the stop is hit
    max_daily_loss_pct: float = 2.0    # stop for the day after losing this much
    max_lots: int = 1                  # hard cap regardless of the maths
    lot_size: int = 65                 # NIFTY lot size (check the instrument file)
    kill_switch_file: str = "STOP"     # create this file to stop new trades and exit


class RiskManager:
    def __init__(self, cfg: RiskConfig):
        self.cfg = cfg
        self.realised = 0.0

    @property
    def risk_budget(self) -> float:
        return self.cfg.capital * self.cfg.risk_per_trade_pct / 100

    @property
    def daily_loss_limit(self) -> float:
        return self.cfg.capital * self.cfg.max_daily_loss_pct / 100

    def lots_for(self, option_risk_pts: float) -> int:
        """Lots such that hitting the stop loses at most the per-trade budget. 0 means skip."""
        if option_risk_pts <= 0:
            return 0
        per_lot = option_risk_pts * self.cfg.lot_size
        return max(0, min(self.cfg.max_lots, math.floor(self.risk_budget / per_lot)))

    def record(self, pnl: float) -> None:
        self.realised += pnl

    def kill_switch(self) -> bool:
        return os.path.exists(self.cfg.kill_switch_file)

    def blocked(self) -> str:
        """Reason new trades are blocked, or '' if trading is allowed."""
        if self.kill_switch():
            return f"kill switch file '{self.cfg.kill_switch_file}' exists"
        if self.realised <= -self.daily_loss_limit:
            return f"daily loss limit hit ({self.realised:.0f} <= -{self.daily_loss_limit:.0f})"
        return ""

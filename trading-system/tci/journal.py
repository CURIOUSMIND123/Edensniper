"""Append-only CSV journal of every closed trade, used to judge paper results before going live."""
from __future__ import annotations

import csv
import glob
import os
import statistics
from typing import Dict, List

FIELDS = ["date", "mode", "side", "zone", "symbol", "lots", "qty", "index_entry", "index_stop", "index_target",
          "index_exit", "reason", "opt_entry", "opt_exit", "gross", "charges", "net", "opened", "closed"]


class Journal:
    def __init__(self, folder: str = "journal"):
        self.folder = folder
        os.makedirs(folder, exist_ok=True)

    def path(self, date: str) -> str:
        return os.path.join(self.folder, f"{date}.csv")

    def add(self, row: Dict) -> None:
        p = self.path(row["date"])
        new = not os.path.exists(p)
        with open(p, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
            if new:
                w.writeheader()
            w.writerow(row)

    def rows(self, mode: str = "") -> List[Dict]:
        out = []
        for p in sorted(glob.glob(os.path.join(self.folder, "*.csv"))):
            with open(p) as f:
                out += [r for r in csv.DictReader(f) if not mode or r["mode"] == mode]
        return out

    def stats(self, mode: str = "paper") -> Dict:
        rows = self.rows(mode)
        nets = [float(r["net"]) for r in rows]
        days = len({r["date"] for r in rows})
        if not nets:
            return {"trades": 0, "days": 0, "net": 0.0, "avg": 0.0, "win_pct": 0.0}
        return {"trades": len(nets), "days": days, "net": round(sum(nets), 2),
                "avg": round(statistics.mean(nets), 2), "win_pct": round(100 * sum(n > 0 for n in nets) / len(nets), 1)}

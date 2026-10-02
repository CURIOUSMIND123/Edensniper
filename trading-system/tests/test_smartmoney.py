"""Run with:  python -m unittest discover -s tests   (from the trading-system folder)"""
import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tci.rules import Bar  # noqa: E402
from tci.smartmoney import SMParams, run  # noqa: E402

D0 = datetime(2026, 9, 14, 9, 15)
D1 = datetime(2026, 9, 15, 9, 15)


def day(start, level, n=75, spread=4.0):
    out = []
    for i in range(n):
        o = level + (1 if i % 2 else -1)
        out.append(Bar(start + timedelta(minutes=5 * i), o, o + spread / 2, o - spread / 2, level - (1 if i % 2 else -1)))
    return out


def t(i):
    return D1 + timedelta(minutes=5 * i)


class TrapTests(unittest.TestCase):
    def setUp(self):
        self.prev = day(D0, 1000)
        self.prev[10] = Bar(self.prev[10].t, 1000, 1100, 999, 1001)   # PDH 1100
        self.prev[20] = Bar(self.prev[20].t, 1000, 1001, 990, 999)    # PDL 990

    def test_trap_below_pdl_gives_buy_with_min_25_sl_and_50_target(self):
        today = [Bar(t(0), 1000, 1002, 998, 1000), Bar(t(1), 1000, 1001, 998, 999), Bar(t(2), 999, 1000, 998, 999),
                 Bar(t(3), 999, 1000, 975, 998),       # runs 15 below PDL, closes back above: trap (pin bar)
                 Bar(t(4), 998, 1003, 997, 1002),      # follow-up breaks 1000 + 1
                 Bar(t(5), 1002, 1060, 1001, 1058)]
        e = run(self.prev + today, SMParams())
        sig = [ev for ev in e.events if ev[1] == "signal" and ev[0] >= D1]
        self.assertTrue(sig and sig[0][2].startswith("BUY TRAP") and "990" in sig[0][2], e.events)
        tr = [x for x in e.trades if x.opened >= D1][0]
        self.assertEqual((tr.side, tr.entry), ("BUY", 1001))
        self.assertEqual(tr.sl0, 1001 - 28)                 # structure: 975 - 2 = 973 -> 28 points (>= 25)
        self.assertEqual(tr.t1, 1100)                       # first liquidity at least 50 points away: PDH
        self.assertGreaterEqual(tr.t1 - tr.entry, 50)

    def test_min_sl_applies_when_structure_is_tight(self):
        today = [Bar(t(0), 1000, 1002, 998, 1000), Bar(t(1), 1000, 1001, 998, 999), Bar(t(2), 999, 1000, 998, 999),
                 Bar(t(3), 999, 1000, 986, 999.5), Bar(t(4), 999.5, 1003, 998, 1002)]
        e = run(self.prev + today, SMParams())
        tr = [x for x in e.trades if x.opened >= D1][0]
        self.assertEqual(tr.entry - tr.sl0, 25)             # structure says 16, minimum is 25

    def test_after_t1_the_stop_trails_toward_max(self):
        self.prev[25] = Bar(self.prev[25].t, 1000, 1200, 999, 1001)  # PDH 1200 (takes out the earlier 1100 high)
        self.prev[50] = Bar(self.prev[50].t, 1000, 1100, 999, 1001)  # a later 1100 swing high: the nearer liquidity
        today = [Bar(t(0), 1000, 1002, 998, 1000), Bar(t(1), 1000, 1001, 998, 999), Bar(t(2), 999, 1000, 998, 999),
                 Bar(t(3), 999, 1000, 975, 998), Bar(t(4), 998, 1003, 997, 1002),
                 Bar(t(5), 1002, 1105, 1001, 1104),     # T1 (1100) hit: keep the trade, trail it
                 Bar(t(6), 1104, 1150, 1100, 1148),
                 Bar(t(7), 1148, 1149, 1060, 1062)]     # pullback hits the trailing stop
        e = run(self.prev + today, SMParams())
        tr = [x for x in e.trades if x.opened >= D1][0]
        self.assertEqual((tr.t1, tr.tmax), (1100, 1200))
        self.assertTrue(tr.t1_hit)
        self.assertEqual(tr.reason, "trail")
        self.assertGreater(tr.exit, 1100)                   # locked in more than T1


class MapTests(unittest.TestCase):
    def test_map_has_levels_both_sides(self):
        prev = day(D0, 1000)
        prev[10] = Bar(prev[10].t, 1000, 1100, 999, 1001)
        prev[20] = Bar(prev[20].t, 1000, 1001, 900, 999)
        today = [Bar(t(0), 1000, 1002, 998, 1000)]
        e = run(prev + today, SMParams())
        m = e.liquidity_map(1000)
        self.assertIn(1100, [round(l.price) for l in m["above"]])
        self.assertIn(900, [round(l.price) for l in m["below"]])
        self.assertTrue(any("PDH" in l.name for l in m["above"]))


if __name__ == "__main__":
    unittest.main()

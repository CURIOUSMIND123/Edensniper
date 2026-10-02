"""Run with:  python -m unittest discover -s tests   (from the trading-system folder)"""
import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tci.allinone import AIParams, AllInOne, run  # noqa: E402
from tci.rules import Bar  # noqa: E402

D0 = datetime(2026, 9, 14, 9, 15)
D1 = datetime(2026, 9, 15, 9, 15)


def flat_day(start, level=1000.0, n=75):
    """A quiet day: candles of 4 points around `level`, so PDH ~1003, PDL ~997."""
    out = []
    for i in range(n):
        o = level + (1 if i % 2 else -1)
        out.append(Bar(start + timedelta(minutes=5 * i), o, o + 2, o - 2, level - (1 if i % 2 else -1)))
    return out


def t(i):
    return D1 + timedelta(minutes=5 * i)


class SweepTests(unittest.TestCase):
    def test_sell_side_sweep_with_pin_bar_gives_buy(self):
        prev = flat_day(D0)
        prev[10] = Bar(prev[10].t, 1000, 1060, 999, 1001)   # PDH 1060: room for a target
        today = [Bar(t(0), 1000, 1002, 998, 1000), Bar(t(1), 1000, 1001, 998, 999), Bar(t(2), 999, 1000, 998, 999),
                 # pin bar: runs 12 points below PDL (~997), closes back above it with a long lower wick
                 Bar(t(3), 1003, 1004, 985, 1003.5),
                 # follow-up breaks the pin bar's high (1004 + 1) -> BUY
                 Bar(t(4), 1003.5, 1008, 1002, 1007),
                 Bar(t(5), 1007, 1065, 1006, 1062)]
        e = run(prev + today, AIParams())
        sig = [ev for ev in e.events if ev[1] == "signal"]
        self.assertTrue(sig and sig[0][2].startswith("BUY SWEEP"), e.events)
        self.assertIn("PDL", sig[0][2])
        self.assertEqual(len(e.trades), 1)
        tr = e.trades[0]
        self.assertEqual((tr.side, tr.setup, tr.entry, tr.sl0, tr.t1), ("BUY", "SWEEP", 1005, 983, 1060))
        self.assertEqual(tr.reason, "T1")
        self.assertAlmostEqual(tr.r, 55 / 22)

    def test_no_room_no_trade(self):
        prev = flat_day(D0)                                   # PDH ~1003: right above the entry
        today = [Bar(t(0), 1000, 1002, 998, 1000), Bar(t(1), 1000, 1001, 998, 999), Bar(t(2), 999, 1000, 998, 999),
                 Bar(t(3), 999, 1000, 985, 999.5), Bar(t(4), 999.5, 1004, 999, 1003)]
        e = run(prev + today, AIParams())
        self.assertEqual(len(e.trades), 0)
        self.assertTrue(any("no room" in ev[2] for ev in e.events))

    def test_no_follow_up_no_trade(self):
        prev = flat_day(D0)
        prev[10] = Bar(prev[10].t, 1000, 1060, 999, 1001)
        today = [Bar(t(0), 1000, 1002, 998, 1000), Bar(t(1), 1000, 1001, 998, 999), Bar(t(2), 999, 1000, 998, 999),
                 Bar(t(3), 1003, 1004, 985, 1003.5),
                 Bar(t(4), 1003.5, 1004.5, 996, 997)]   # never trades above 1005
        e = run(prev + today, AIParams())
        self.assertEqual(len(e.trades), 0)


class CandleTests(unittest.TestCase):
    def test_pin_and_engulfing(self):
        e = AllInOne()
        c = e._candle(Bar(D1, 100, 101, 90, 100.5), None)
        self.assertTrue(c["bull_pin"])
        self.assertFalse(c["bear_pin"])
        prev = Bar(D1, 105, 106, 99, 100)
        c = e._candle(Bar(D1, 99.5, 107, 99, 106), prev)
        self.assertTrue(c["bull_eng"])


class TargetTests(unittest.TestCase):
    def test_t1_uses_nearest_level_when_in_range(self):
        e = AllInOne(AIParams())
        e.daily = []
        from tci.allinone import Level
        e.swings_hi = [Level(1030, "swing high", "high", True), Level(1050, "swing high", "high", True)]
        t1, t2, t3, room = e._targets("BUY", 1000, 10)
        self.assertEqual((t1, t2, room), (1030, 1050, 30))
        self.assertEqual(t3, 1060)

    def test_t1_defaults_to_2r_when_level_far(self):
        e = AllInOne(AIParams())
        from tci.allinone import Level
        e.swings_lo = [Level(900, "swing low", "low", True)]
        t1, t2, t3, room = e._targets("SELL", 1000, 10)
        self.assertEqual((t1, t2), (980, 970))


class LimitTests(unittest.TestCase):
    def test_day_limits(self):
        e = AllInOne(AIParams(max_losses=2))
        e.day = "2026-09-15"
        from tci.allinone import AITrade
        for _ in range(2):
            tr = AITrade("BUY", "SWEEP", "", D1, D1, 100, 90, 120, 130, 140, sl0=90)
            tr.exit = 90
            e.day_trades.append(tr)
        self.assertFalse(e.can_open(D1.replace(hour=10)))


if __name__ == "__main__":
    unittest.main()

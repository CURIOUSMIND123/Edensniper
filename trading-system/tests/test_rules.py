"""Run with:  python -m unittest discover -s tests   (from the trading-system folder)"""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tci import costs  # noqa: E402
from tci.journal import Journal  # noqa: E402
from tci.risk import RiskConfig, RiskManager  # noqa: E402
from tci.rules import Bar, Params, Strategy, Trade, bar_path, merge_zones, Zone, run_day  # noqa: E402
from tci.session import PaperBroker, Session  # noqa: E402

D0 = datetime(2026, 9, 14)
D1 = datetime(2026, 9, 15)


def at(day, hh, mm):
    return day.replace(hour=hh, minute=mm)


def prev_day():
    """PDH 1050, PDL 950, PDC 1000, last-hour (14:00+) range 980-1020."""
    bars = []
    t = at(D0, 9, 15)
    while t.hour < 15 or (t.hour == 15 and t.minute < 30):
        if t.hour >= 14:
            b = Bar(t, 1000, 1010, 990, 1000)
        else:
            b = Bar(t, 1000, 1005, 995, 1000)
        bars.append(b)
        t += timedelta(minutes=5)
    bars[10] = Bar(bars[10].t, 1000, 1050, 999, 1001)
    bars[20] = Bar(bars[20].t, 1000, 1001, 950, 999)
    late = [i for i, b in enumerate(bars) if b.t.hour >= 14]
    bars[late[2]] = Bar(bars[late[2]].t, 1000, 1020, 999, 1000)
    bars[late[4]] = Bar(bars[late[4]].t, 1000, 1001, 980, 1000)
    return bars


def opening():
    return [Bar(at(D1, 9, 15), 1005, 1008, 1003, 1006), Bar(at(D1, 9, 20), 1006, 1007, 1004, 1005),
            Bar(at(D1, 9, 25), 1005, 1007, 1004, 1006),
            Bar(at(D1, 9, 30), 1016, 1024, 1015, 1023)]  # breakout candle through 1020


P = Params(zone_merge_pts=0)


class ZoneTests(unittest.TestCase):
    def test_prior_day_zones(self):
        s = Strategy(prev_day(), P)
        self.assertEqual(sorted(z.level for z in s.zones), [950, 980, 1000, 1020, 1050])

    def test_opening_range_added_after_15_minutes(self):
        s = Strategy(prev_day(), P)
        for b in opening()[:3]:
            s.on_bar_close(b)
        self.assertIn(1008, [z.level for z in s.zones])
        self.assertIn(1003, [z.level for z in s.zones])

    def test_merge(self):
        z = merge_zones([Zone(100, "a"), Zone(105, "b"), Zone(130, "c")], 10)
        self.assertEqual([round(x.level, 1) for x in z], [102.5, 130])


class TradeTests(unittest.TestCase):
    def test_breakout_followup_target(self):
        bars = opening() + [Bar(at(D1, 9, 35), 1023, 1030, 1022, 1029), Bar(at(D1, 9, 40), 1029, 1052, 1027, 1050)]
        s = run_day(prev_day(), bars, P)
        self.assertEqual(len(s.trades), 1)
        tr = s.trades[0]
        self.assertEqual((tr.side, tr.entry, tr.initial_stop, tr.target, tr.exit, tr.reason), ("CE", 1025, 1014, 1050, 1050, "target"))
        self.assertAlmostEqual(tr.r, 25 / 11, places=3)

    def test_no_followup_cancels(self):
        bars = opening() + [Bar(at(D1, 9, 35), 1022, 1024, 1018, 1019)]
        s = run_day(prev_day(), bars, P)
        self.assertEqual(len(s.trades), 0)
        self.assertTrue(any(e.kind == "cancel" for e in s.events))
        self.assertTrue(any(e.kind == "skip" and "next zone only" in e.detail for e in s.events))

    def test_breakeven_exit(self):
        bars = opening() + [Bar(at(D1, 9, 35), 1023, 1030, 1022, 1029), Bar(at(D1, 9, 40), 1029, 1037, 1026, 1030),
                            Bar(at(D1, 9, 45), 1030, 1031, 1020, 1021)]
        s = run_day(prev_day(), bars, P)
        self.assertEqual(s.trades[0].reason, "breakeven")
        self.assertEqual(s.trades[0].points, 0)
        self.assertEqual(s.losses, 0)

    def test_stop_exit(self):
        bars = opening() + [Bar(at(D1, 9, 35), 1023, 1030, 1022, 1029), Bar(at(D1, 9, 40), 1029, 1030, 1010, 1012)]
        s = run_day(prev_day(), bars, P)
        self.assertEqual((s.trades[0].reason, s.trades[0].exit), ("stop", 1014))
        self.assertEqual(s.losses, 1)

    def test_square_off(self):
        bars = opening() + [Bar(at(D1, 9, 35), 1023, 1030, 1022, 1029)]
        t = at(D1, 9, 40)
        while t <= at(D1, 15, 10):
            bars.append(Bar(t, 1029, 1033, 1027, 1030))
            t += timedelta(minutes=5)
        s = run_day(prev_day(), bars, P)
        self.assertEqual(s.trades[0].reason, "square-off")
        self.assertEqual(s.trades[0].closed, at(D1, 15, 10))

    def test_no_entries_after_two_losses(self):
        s = Strategy(prev_day(), P)
        for _ in range(2):
            s.trades.append(Trade("CE", "x", D1, 100, 90, 120, D1, 90, "stop"))
        self.assertFalse(s.can_open(at(D1, 10, 0)))

    def test_no_entries_outside_window(self):
        s = Strategy(prev_day(), P)
        self.assertFalse(s.can_open(at(D1, 9, 20)))
        self.assertTrue(s.can_open(at(D1, 9, 25)))
        self.assertFalse(s.can_open(at(D1, 14, 35)))

    def test_bar_path(self):
        self.assertEqual(bar_path(Bar(D1, 10, 12, 9, 11)), [10, 9, 12, 11])
        self.assertEqual(bar_path(Bar(D1, 10, 12, 9, 9.5)), [10, 12, 9, 9.5])


class RiskAndCostTests(unittest.TestCase):
    def test_lots(self):
        r = RiskManager(RiskConfig(capital=50000, risk_per_trade_pct=1, max_lots=3, lot_size=65))
        self.assertEqual(r.lots_for(6), 1)   # 6 x 65 = 390 <= 500
        self.assertEqual(r.lots_for(8), 0)   # 520 > 500: skip
        self.assertEqual(r.lots_for(2), 3)   # capped at max_lots

    def test_daily_loss_block(self):
        r = RiskManager(RiskConfig(capital=50000, max_daily_loss_pct=2, kill_switch_file="/nonexistent/STOP"))
        r.record(-999)
        self.assertEqual(r.blocked(), "")
        r.record(-1)
        self.assertIn("daily loss", r.blocked())

    def test_round_trip_charges(self):
        c = costs.round_trip(150 * 65, 150 * 65, "NSE")
        self.assertTrue(55 < c < 75, c)


class SessionTests(unittest.TestCase):
    def test_paper_session_journals_trade(self):
        bars = opening() + [Bar(at(D1, 9, 35), 1023, 1030, 1022, 1029), Bar(at(D1, 9, 40), 1029, 1052, 1027, 1050)]
        state = {"i": 1000.0}
        with tempfile.TemporaryDirectory() as tmp:
            j = Journal(tmp)
            risk = RiskManager(RiskConfig(capital=100000, kill_switch_file=os.path.join(tmp, "STOP")))
            s = Strategy(prev_day(), P)
            sess = Session("2026-09-15", s, PaperBroker(lambda sym: 150 + 0.5 * (state["i"] - 1025), 1.0), risk, j, "paper",
                           pick_option=lambda side, spot: {"trading_symbol": "X", "strike": 1000, "ltp": 150, "delta": 0.5},
                           option_quote=lambda sym: 150.0, log=lambda m: None)
            for b in bars:
                for k, px in enumerate(bar_path(b)):
                    state["i"] = px
                    sess.on_tick(b.t, px, first_of_bar=(k == 0))
                sess.on_bar(b)
            rows = j.rows("paper")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["reason"], "target")
            # the paper broker fills at the option price when the order is sent: index 1030 (bar high) on
            # entry and 1052 on exit, plus/minus 1 point of slippage
            self.assertAlmostEqual(float(rows[0]["opt_entry"]), 150 + 0.5 * 5 + 1)
            self.assertAlmostEqual(float(rows[0]["opt_exit"]), 150 + 0.5 * 27 - 1)
            self.assertLess(risk.realised, float(rows[0]["gross"]))      # charges deducted

    def test_kill_switch_flattens(self):
        bars = opening() + [Bar(at(D1, 9, 35), 1023, 1030, 1022, 1029)]
        with tempfile.TemporaryDirectory() as tmp:
            kill = os.path.join(tmp, "STOP")
            risk = RiskManager(RiskConfig(capital=100000, kill_switch_file=kill))
            s = Strategy(prev_day(), P)
            sess = Session("2026-09-15", s, PaperBroker(lambda sym: 150.0, 0.0), risk, Journal(tmp), "paper",
                           pick_option=lambda side, spot: {"trading_symbol": "X", "strike": 1000, "ltp": 150, "delta": 0.5},
                           option_quote=lambda sym: 150.0, log=lambda m: None)
            for b in bars:
                for k, px in enumerate(bar_path(b)):
                    sess.on_tick(b.t, px, first_of_bar=(k == 0))
                sess.on_bar(b)
            self.assertIsNotNone(s.position)
            open(kill, "w").close()
            sess.on_tick(at(D1, 9, 41), 1028)
            self.assertIsNone(s.position)
            self.assertEqual(s.trades[-1].reason, "kill switch")
            self.assertTrue(s.halted)


if __name__ == "__main__":
    unittest.main()

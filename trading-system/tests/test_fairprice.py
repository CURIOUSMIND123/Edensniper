"""Run with:  python -m unittest discover -s tests   (from the trading-system folder)"""
import os
import sys
import unittest
from datetime import datetime, time, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tci.fairprice import FPParams, htf_bias, run_day, tested_params, usual_range  # noqa: E402
from tci.rules import Bar  # noqa: E402

D0 = datetime(2026, 9, 14, 9, 15)
D1 = datetime(2026, 9, 15, 9, 15)


def m(i):
    return D1 + timedelta(minutes=i)


def prev_day(open_px):
    return [Bar(D0, open_px, open_px + 5, open_px - 5, open_px)]


def flat(start, n, px):
    """n quiet candles at px, alternating colour, 2-point bodies."""
    out = []
    for i in range(n):
        o, c = (px - 1, px + 1) if i % 2 else (px + 1, px - 1)
        out.append(Bar(m(start + i), o, px + 2, px - 2, c))
    return out


NO_CONT = FPParams(use_continuation=False)


class BiasTests(unittest.TestCase):
    def test_bias_inverts_the_last_session(self):
        self.assertEqual(htf_bias(prev_day(1000), 1050), -1)   # rallied since yesterday's open -> look for shorts
        self.assertEqual(htf_bias(prev_day(1000), 950), 1)
        self.assertEqual(htf_bias([], 950), 0)


class ContinuationTests(unittest.TestCase):
    def test_red_opening_candle_with_short_bias_sells_at_its_close(self):
        today = [Bar(m(0), 1050, 1052, 1040, 1042)] + flat(1, 3, 1030) + [Bar(m(4), 1030, 1030, 1010, 1011)]
        s = run_day(prev_day(1000), today)
        tr = s.trades[0]
        self.assertEqual((tr.setup, tr.side, tr.entry, tr.sl, tr.tp, tr.size), ("CONT", "SELL", 1042, 1062, 1012, 1.0))
        self.assertEqual((tr.reason, tr.exit), ("TP", 1012))

    def test_opening_candle_against_the_bias_is_skipped(self):
        today = [Bar(m(0), 1050, 1060, 1049, 1058)] + flat(1, 5, 1058)
        s = run_day(prev_day(1000), today)                       # green open but bias is short
        self.assertFalse([t for t in s.trades if t.setup == "CONT"])
        s2 = run_day(prev_day(1000), today, FPParams(use_bias=False))
        self.assertEqual(s2.trades[0].side, "BUY")

    def test_big_opening_candle_doubles_stop_and_target_at_half_size(self):
        today = [Bar(m(0), 1050, 1052, 1025, 1028)] + flat(1, 3, 1028)
        tr = run_day(prev_day(1000), today).trades[0]
        self.assertEqual((tr.sl, tr.tp, tr.size), (1068, 968, 0.5))


class ReversionTests(unittest.TestCase):
    def falls_then_breaks_up(self, low):
        """Open 1000 (fair price), slide to `low`, a swing high at low+7, then a close above it."""
        bars = [Bar(m(0), 1000, 1001, 999, 1000)]
        px = 1000
        i = 1
        while px > low:
            bars.append(Bar(m(i), px, px + 1, px - 6, px - 5))
            px -= 5
            i += 1
        bars += [Bar(m(i), px, px + 7, px - 1, px + 4),            # swing high at px + 7
                 Bar(m(i + 1), px + 4, px + 5, px - 2, px),         # confirms it (lower high)
                 Bar(m(i + 2), px, px + 10, px - 1, px + 9)]        # closes above px + 7: break of structure up
        return bars, px

    def test_break_of_structure_buys_back_toward_the_open(self):
        bars, px = self.falls_then_breaks_up(950)
        s = run_day(prev_day(1000), bars, NO_CONT)
        tr = s.trades[0]
        self.assertEqual((tr.setup, tr.side, tr.entry), ("BOS", "BUY", px + 9))
        self.assertEqual((tr.sl, tr.tp), (px + 9 - 20, px + 9 + 30))

    def test_no_reversion_when_too_close_to_fair_price(self):
        bars, px = self.falls_then_breaks_up(980)               # entry 989, only 11 points of room (< 0.8 x 30)
        self.assertFalse(run_day(prev_day(1000), bars, NO_CONT).trades)

    def test_target_can_be_the_fair_price_itself(self):
        bars, px = self.falls_then_breaks_up(950)
        tr = run_day(prev_day(1000), bars, FPParams(use_continuation=False, target="fair")).trades[0]
        self.assertEqual(tr.tp, 1000)

    def test_displacement_needs_bigger_body_closing_beyond_an_opposite_candle(self):
        bars = [Bar(m(0), 1000, 1001, 999, 1000)]
        bars += [Bar(m(1 + k), 1000 - 5 * k, 1001 - 5 * k, 994 - 5 * k, 995 - 5 * k) for k in range(10)]  # down to 950
        bars += [Bar(m(11), 950, 951, 944, 945),                 # red
                 Bar(m(12), 945, 960, 944, 958)]                  # green, body 13 > 5, closes above 951
        p = FPParams(use_continuation=False, use_bos=False)
        self.assertEqual(run_day(prev_day(1000), bars, p).trades[0].setup, "DISP")
        self.assertFalse(run_day(prev_day(1000), bars, FPParams(use_continuation=False, use_displacement=False,
                                                                use_bos=False)).trades)

    def test_no_new_entries_after_the_window(self):
        bars, px = self.falls_then_breaks_up(950)
        p = FPParams(use_continuation=False, end=time(9, 16))
        self.assertFalse(run_day(prev_day(1000), bars, p).trades)


class AfternoonTests(unittest.TestCase):
    def test_afternoon_first_candle_toward_the_open_is_a_continuation_trade(self):
        pm = D1.replace(hour=13, minute=29)
        bars = [Bar(m(0), 1000, 1001, 999, 1000), Bar(pm, 950, 952, 948, 950),
                Bar(pm + timedelta(minutes=1), 948, 954, 947, 953)]     # 13:30 candle, green, toward 1000
        self.assertFalse(run_day(prev_day(1000), bars).trades)          # off unless a second session is set
        p = FPParams(pm_start=time(13, 30), pm_end=time(15, 0))
        tr = run_day(prev_day(1000), bars, p).trades[0]
        self.assertEqual((tr.setup, tr.side, tr.entry, tr.sl, tr.tp), ("CONT", "BUY", 953, 933, 983))


class LossLimitTests(unittest.TestCase):
    def test_three_losses_in_a_row_end_the_session(self):
        bars = [Bar(m(0), 1000, 1001, 999, 1000)]
        px, i = 1000, 1
        for _ in range(4):                                       # four drops, each with a BOS buy that gets stopped
            for _ in range(10):
                bars.append(Bar(m(i), px, px + 1, px - 6, px - 5)); px -= 5; i += 1
            bars += [Bar(m(i), px, px + 7, px - 1, px + 4), Bar(m(i + 1), px + 4, px + 5, px - 2, px),
                     Bar(m(i + 2), px, px + 10, px - 1, px + 9),
                     Bar(m(i + 3), px + 8, px + 9, px - 30, px - 25)]   # straight through the 20-point stop
            px -= 25
            i += 4
        s = run_day(prev_day(1000), bars, NO_CONT)
        self.assertEqual([(t.setup, t.reason) for t in s.trades], [("BOS", "SL")] * 3)
        self.assertTrue(s.stopped)


class TestedVersionTests(unittest.TestCase):
    def test_usual_range_is_the_median_of_recent_days(self):
        self.assertIsNone(usual_range([100, 90]))
        self.assertEqual(usual_range([100, 90, 120]), 100)
        self.assertEqual(usual_range([50] * 30 + [100, 90, 120, 80], n=4), 95)

    def test_tested_params_scale_with_the_range(self):
        p = tested_params(100)
        self.assertEqual((p.sl, p.tp, p.swing_n, p.max_losses), (40, 120, 2, 2))
        self.assertFalse(p.use_continuation or p.use_displacement)

    def big_drop_then_break(self, depth):
        """Open 1000, fall `depth` points, a swing high with 2 lower highs each side, then a close above it."""
        bars = [Bar(m(0), 1000, 1001, 999, 1000)]
        px, i = 1000, 1
        while px > 1000 - depth:
            bars.append(Bar(m(i), px, px + 1, px - 6, px - 5)); px -= 5; i += 1
        lo = px
        bars += [Bar(m(i), lo, lo + 3, lo - 1, lo + 2), Bar(m(i + 1), lo + 2, lo + 6, lo, lo + 4),
                 Bar(m(i + 2), lo + 4, lo + 10, lo + 3, lo + 5),                      # swing high lo + 10
                 Bar(m(i + 3), lo + 5, lo + 8, lo + 1, lo + 2), Bar(m(i + 4), lo + 2, lo + 7, lo, lo + 6),
                 Bar(m(i + 5), lo + 6, lo + 13, lo + 5, lo + 12)]                     # closes above it
        return bars, lo

    def test_tested_version_buys_only_after_a_big_move_away(self):
        bars, lo = self.big_drop_then_break(110)                 # range 100: needs 96 points of room
        tr = run_day(prev_day(1000), bars, tested_params(100)).trades
        self.assertEqual([(t.setup, t.side, t.entry, t.sl, t.tp) for t in tr], [("BOS", "BUY", lo + 12, lo + 12 - 40, lo + 12 + 120)])
        bars2, _ = self.big_drop_then_break(60)                  # not far enough from the open
        self.assertFalse(run_day(prev_day(1000), bars2, tested_params(100)).trades)

    def test_swing_needs_two_lower_highs_on_each_side_when_swing_n_is_2(self):
        bars, lo = self.big_drop_then_break(110)
        bars[-3] = Bar(bars[-3].t, lo + 5, lo + 11, lo + 1, lo + 2)   # a right-hand candle higher than the swing
        p = tested_params(100)
        self.assertFalse(run_day(prev_day(1000), bars, p).trades)

    def test_break_even_moves_the_stop_to_entry(self):
        bars, lo = self.big_drop_then_break(110)
        e = lo + 12
        bars += [Bar(m(200), e, e + 45, e - 1, e + 40), Bar(m(201), e + 40, e + 41, e - 5, e - 4)]
        p = tested_params(100)
        p.be_at_r = 1.0
        tr = run_day(prev_day(1000), bars, p).trades[0]
        self.assertEqual((tr.reason, tr.exit), ("BE", e))


if __name__ == "__main__":
    unittest.main()

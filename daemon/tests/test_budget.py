import calendar
import unittest
from datetime import datetime, timezone

from clawdmeter_daemon.providers import _budget as b

UTC = timezone.utc


def dt(*a):
    return datetime(*a, tzinfo=UTC)


def legacy_pace(spent, budget, now):
    """Verbatim copy of the pre-refactor Langdock._estimate_pace."""
    if budget <= 0:
        return None
    dim = calendar.monthrange(now.year, now.month)[1]
    expected = ((now.day + now.hour / 24.0) / dim) * 100.0
    delta = (spent / budget) * 100.0 - expected
    if delta <= -25: return -3
    if delta <= -15: return -2
    if delta <= -5: return -1
    if delta < 5: return 0
    if delta < 15: return 1
    if delta < 25: return 2
    return 3


def legacy_month_end(now):
    last = calendar.monthrange(now.year, now.month)[1]
    return int((datetime(now.year, now.month, last, 23, 59, 59, tzinfo=UTC) - now).total_seconds())


class ParseTests(unittest.TestCase):
    def test_duration(self):
        self.assertEqual(b.parse_duration("1M"), (1, "M"))
        self.assertEqual(b.parse_duration("30s"), (30, "s"))
        for bad in ("", "M", "0d", "1x", None, 5):
            self.assertIsNone(b.parse_duration(bad))

    def test_iso(self):
        self.assertEqual(b.parse_iso("2026-10-01T00:00:00Z"), dt(2026, 10, 1))
        self.assertEqual(b.parse_iso("2026-09-18T08:06:50.24957123Z"),
                         datetime(2026, 9, 18, 8, 6, 50, 249571, tzinfo=UTC))
        self.assertIsNone(b.parse_iso("nope"))


class ResetTests(unittest.TestCase):
    def test_day_and_week(self):
        now = dt(2026, 10, 7, 12)
        self.assertEqual(b.next_reset(dt(2026, 10, 7), (1, "d"), now), dt(2026, 10, 8))
        self.assertEqual(b.next_reset(dt(2026, 10, 5), (1, "w"), now), dt(2026, 10, 12))

    def test_month_spec_scenario(self):
        now = dt(2026, 10, 7, 12)
        nxt = b.next_reset(dt(2026, 10, 1), (1, "M"), now)
        self.assertEqual(nxt, dt(2026, 11, 1))
        self.assertEqual(b.seconds_until(nxt, now), 2116800)

    def test_month_across_year_boundary(self):
        now = dt(2026, 12, 20)
        self.assertEqual(b.next_reset(dt(2026, 12, 1), (1, "M"), now), dt(2027, 1, 1))

    def test_month_end_clamping_keeps_anchor(self):
        # Anchor on the 31st: Feb is clamped, March goes back to the 31st.
        self.assertEqual(b.add_months(dt(2026, 1, 31), 1), dt(2026, 2, 28))
        self.assertEqual(b.next_reset(dt(2026, 1, 31), (1, "M"), dt(2026, 3, 1)), dt(2026, 3, 31))

    def test_quarter(self):
        self.assertEqual(b.next_reset(dt(2026, 7, 1), (1, "Q"), dt(2026, 8, 5)), dt(2026, 10, 1))
        self.assertEqual(b.next_reset(dt(2026, 10, 1), (1, "Q"), dt(2026, 10, 7)), dt(2027, 1, 1))
        self.assertEqual(b.next_reset(dt(2026, 1, 1), (1, "Q"), dt(2026, 10, 7)), dt(2027, 1, 1))

    def test_stale_last_reset_steps_forward(self):
        now = dt(2026, 10, 7, 12)
        start, nxt = b.current_window(dt(2026, 3, 1), (1, "M"), now)
        self.assertEqual((start, nxt), (dt(2026, 10, 1), dt(2026, 11, 1)))
        start, nxt = b.current_window(dt(2026, 10, 1), (1, "d"), now)
        self.assertEqual((start, nxt), (dt(2026, 10, 7), dt(2026, 10, 8)))

    def test_late_reset_in_gateway(self):
        # next boundary (Oct 1) already passed but gateway has not reset yet
        now = dt(2026, 10, 1, 0, 5)
        self.assertEqual(b.next_reset(dt(2026, 9, 1), (1, "M"), now), dt(2026, 11, 1))


class PaceStatusTests(unittest.TestCase):
    def test_status(self):
        self.assertEqual(b.status_for(89, 100), "ok")
        self.assertEqual(b.status_for(90, 100), "near-limit")
        self.assertEqual(b.status_for(100, 100), "over-budget")
        self.assertEqual(b.status_for(5, 0), "ok")

    def test_pace_spec_scenario_slightly_ahead(self):
        start, end = dt(2026, 10, 1), dt(2026, 11, 1)
        now = dt(2026, 10, 1) + (end - start) * 0.226
        self.assertGreater(b.pace(25, 100, start, end, now), 0)

    def test_pace_range(self):
        start, end = dt(2026, 10, 1), dt(2026, 11, 1)
        now = dt(2026, 10, 2)
        self.assertEqual(b.pace(100, 100, start, end, now), 3)
        self.assertEqual(b.pace(0, 100, start, end, dt(2026, 10, 25)), -3)
        self.assertIsNone(b.pace(1, 0, start, end, now))

    def test_langdock_equivalence(self):
        for day in (1, 7, 15, 28, 31):
            for hour in (0, 11, 23):
                now = dt(2026, 10, day, hour, 17)
                for spent in (0, 10, 30, 50, 75, 99, 150):
                    self.assertEqual(b.month_pace(spent, 100, now), legacy_pace(spent, 100, now))
                self.assertEqual(b.seconds_to_month_end(now), legacy_month_end(now))
        self.assertIsNone(b.month_pace(5, 0, dt(2026, 10, 1)))


if __name__ == "__main__":
    unittest.main()

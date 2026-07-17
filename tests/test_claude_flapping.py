"""Tests for the Claude gauges surviving a rate-limited endpoint.

Observed live: the usage endpoint returns HTTP 429 with `Retry-After: 0` for
long stretches. The old behaviour polled straight through it every 60s (which
keeps the rate limit alive) and blanked the gauges on every failure (which
made them flicker between real numbers and "usage unavailable").
"""
import time
import unittest
from unittest import mock

from statstrip import collector, display


class BackoffTest(unittest.TestCase):
    def test_healthy_polling_uses_the_normal_interval(self):
        with mock.patch.object(collector.config, "CLAUDE_REFRESH", 60):
            self.assertEqual(collector._claude_delay(0), 60)

    def test_each_failure_doubles_the_wait(self):
        with mock.patch.object(collector.config, "CLAUDE_REFRESH", 60), \
             mock.patch.object(collector.config, "CLAUDE_BACKOFF_MAX", 1800):
            self.assertEqual(collector._claude_delay(1), 120)
            self.assertEqual(collector._claude_delay(2), 240)
            self.assertEqual(collector._claude_delay(3), 480)

    def test_backoff_is_capped(self):
        """Backoff must not grow without bound, or recovery takes hours."""
        with mock.patch.object(collector.config, "CLAUDE_REFRESH", 60), \
             mock.patch.object(collector.config, "CLAUDE_BACKOFF_MAX", 1800):
            self.assertEqual(collector._claude_delay(99), 1800)


class ClaudeLoopTest(unittest.TestCase):
    """Drives single iterations by breaking out of the sleep."""

    def setUp(self):
        collector._state.update({
            "claude_active": True, "claude_5h_pct": 20.0,
            "claude_week_pct": 30.0, "claude_captured_at": None,
            "claude_status": None,
        })

    def run_iterations(self, results, n):
        """Run n iterations, returning the delay passed to each sleep."""
        class Stop(Exception):
            pass

        delays = []
        calls = iter(results)

        def fake_sleep(d):
            delays.append(d)
            if len(delays) >= n:
                raise Stop

        with mock.patch.object(collector.config, "CLAUDE_ENABLED", True), \
             mock.patch.object(collector.config, "CLAUDE_REFRESH", 60), \
             mock.patch.object(collector.config, "CLAUDE_BACKOFF_MAX", 1800), \
             mock.patch.object(collector, "write_snapshot"), \
             mock.patch.object(collector, "collect_claude",
                               side_effect=lambda: next(calls)), \
             mock.patch.object(collector.time, "sleep", fake_sleep):
            with self.assertRaises(Stop):
                collector.claude_loop()
        return delays

    def test_rate_limited_polls_back_off(self):
        """Hammering a 429 every 60s is what keeps the rate limit alive."""
        unavailable = (False, None, None, "unavailable")
        delays = self.run_iterations([unavailable] * 4, 4)
        self.assertEqual(delays, [120, 240, 480, 960])

    def test_a_429_holds_the_last_reading_instead_of_blanking_it(self):
        """The flicker: one failed poll used to wipe numbers that were right a
        minute ago."""
        good = (True, 20.0, 30.0, "ok")
        unavailable = (False, None, None, "unavailable")
        self.run_iterations([good, unavailable], 2)
        self.assertEqual(collector._state["claude_status"], "ok")
        self.assertEqual(collector._state["claude_5h_pct"], 20.0)
        self.assertEqual(collector._state["claude_week_pct"], 30.0)
        self.assertIsNotNone(collector._state["claude_captured_at"])

    def test_failure_before_any_reading_is_unavailable(self):
        """With nothing to hold over, there's nothing to show."""
        self.run_iterations([(False, None, None, "unavailable")], 1)
        self.assertEqual(collector._state["claude_status"], "unavailable")

    def test_success_resets_the_backoff(self):
        good = (True, 20.0, 30.0, "ok")
        unavailable = (False, None, None, "unavailable")
        delays = self.run_iterations([unavailable, unavailable, good, good], 4)
        self.assertEqual(delays, [120, 240, 60, 60])

    def test_login_required_clears_the_held_reading(self):
        """A real logout must not keep showing stale percentages."""
        good = (True, 20.0, 30.0, "ok")
        self.run_iterations([good, (False, None, None, "login_required")], 2)
        self.assertEqual(collector._state["claude_status"], "login_required")
        self.assertIsNone(collector._state["claude_5h_pct"])
        self.assertIsNone(collector._state["claude_captured_at"])

    def test_crash_does_not_kill_the_loop(self):
        delays = self.run_iterations([], 2)  # StopIteration on every call
        self.assertEqual(delays, [120, 240])  # survived, and backed off


class ClaudeRenderTest(unittest.TestCase):
    def snapshot(self, status="ok", age_s=0, **kw):
        s = {
            "claude_status": status, "claude_active": True,
            "claude_5h_pct": 20.0, "claude_week_pct": 30.0,
            "claude_captured_at": time.time() - age_s,
        }
        s.update(kw)
        return s

    def test_fresh_reading_has_no_age_marker(self):
        self.assertEqual(display.claude_parts(self.snapshot()),
                         ["CLAUDE 5h 20%", "WEEK 30%"])

    def test_held_reading_shows_its_age(self):
        """Claude usage moves while you work, so a held number must never
        pose as current."""
        self.assertEqual(display.claude_parts(self.snapshot(age_s=3 * 3600)),
                         ["CLAUDE 5h 20%", "WEEK 30%", "(3h ago)"])

    def test_login_required_still_reported(self):
        self.assertEqual(display.claude_parts(self.snapshot(status="login_required")),
                         ["CLAUDE login required"])

    def test_unavailable_when_never_read(self):
        self.assertEqual(display.claude_parts(self.snapshot(status="unavailable")),
                         ["CLAUDE usage unavailable"])

    def test_estimate_mode_keeps_its_tilde(self):
        self.assertEqual(display.claude_parts(self.snapshot(status="estimate")),
                         ["CLAUDE 5h ~20%", "WEEK ~30%"])

    def test_idle_reading(self):
        self.assertEqual(display.claude_parts(self.snapshot(claude_active=False)),
                         ["CLAUDE 5h idle", "WEEK 30%"])


if __name__ == "__main__":
    unittest.main()

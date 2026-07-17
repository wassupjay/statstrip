"""Tests for the collector's Codex wiring (log source; see
test_codex_appserver.py for live-source selection).

The loop's job is to never freeze a reading on screen: a thread that dies, or
one that keeps failing while holding its last success, both show stale
percentages as if they were live.
"""
import unittest
from unittest import mock

from statstrip import collector


class CollectCodexTest(unittest.TestCase):
    def setUp(self):
        # These cover the log path. Without pinning the source off, they would
        # reach the real app-server and assert against live account data.
        patcher = mock.patch.object(collector.config, "CODEX_LIVE", False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_disabled_reports_nothing(self):
        with mock.patch.object(collector.config, "CODEX_ENABLED", False):
            self.assertEqual(collector.collect_codex(), ([], None, None, None))

    def test_reading_maps_to_ok(self):
        windows = [{"label": "5h", "used_pct": 42.0, "rolled_over": False}]
        with mock.patch.object(collector.config, "CODEX_ENABLED", True), \
             mock.patch("statstrip.codex_local.collect",
                        return_value=(windows, 1234.0)):
            self.assertEqual(collector.collect_codex(),
                             (windows, 1234.0, "ok", "log"))

    def test_login_required_passes_through(self):
        with mock.patch.object(collector.config, "CODEX_ENABLED", True), \
             mock.patch("statstrip.codex_local.collect",
                        return_value="login_required"):
            self.assertEqual(collector.collect_codex(),
                             ([], None, "login_required", None))

    def test_no_reading_maps_to_unavailable(self):
        with mock.patch.object(collector.config, "CODEX_ENABLED", True), \
             mock.patch("statstrip.codex_local.collect", return_value=None):
            self.assertEqual(collector.collect_codex(),
                             ([], None, "unavailable", None))


class CodexLoopTest(unittest.TestCase):
    """Drives exactly one iteration by breaking out of the sleep."""

    def setUp(self):
        collector._state.update({
            "codex_windows": [{"label": "5h", "used_pct": 42.0,
                               "rolled_over": False}],
            "codex_captured_at": 1234.0,
            "codex_status": "ok",
        })

    def run_one_iteration(self):
        class Stop(Exception):
            pass

        with mock.patch.object(collector.config, "CODEX_ENABLED", True), \
             mock.patch.object(collector, "write_snapshot"), \
             mock.patch.object(collector.time, "sleep", side_effect=Stop):
            with self.assertRaises(Stop):
                collector.codex_loop()

    def test_failure_clears_the_last_good_reading(self):
        """A poll that keeps failing must not leave its last success on screen
        looking current — that's the frozen-numbers bug."""
        with mock.patch.object(collector, "collect_codex",
                               side_effect=RuntimeError("schema changed")):
            self.run_one_iteration()
        self.assertEqual(collector._state["codex_windows"], [])
        self.assertIsNone(collector._state["codex_captured_at"])
        self.assertEqual(collector._state["codex_status"], "unavailable")

    def test_failure_does_not_kill_the_loop(self):
        """A dead thread freezes numbers on screen forever."""
        with mock.patch.object(collector, "collect_codex",
                               side_effect=RuntimeError("boom")):
            self.run_one_iteration()  # reached sleep => survived the error

    def test_success_stores_the_reading(self):
        windows = [{"label": "7d", "used_pct": 9.0, "rolled_over": False}]
        with mock.patch.object(collector, "collect_codex",
                               return_value=(windows, 999.0, "ok", "live")):
            self.run_one_iteration()
        self.assertEqual(collector._state["codex_windows"], windows)
        self.assertEqual(collector._state["codex_captured_at"], 999.0)
        self.assertEqual(collector._state["codex_status"], "ok")


if __name__ == "__main__":
    unittest.main()

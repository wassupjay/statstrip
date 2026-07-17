"""Tests for how Codex usage is rendered on the strip.

The two real bugs this project has hit were both display-side lies: telling
a logged-in user to log in, and showing numbers that looked live but
weren't. These cover exactly those branches.
"""
import time
import unittest
from unittest import mock

from statstrip import display


_UNSET = object()


def snapshot(status="ok", windows=None, age_s=0, captured_at=_UNSET):
    return {
        "codex_status": status,
        "codex_windows": windows if windows is not None else [
            {"label": "5h", "used_pct": 42.0, "rolled_over": False},
            {"label": "7d", "used_pct": 63.0, "rolled_over": False},
        ],
        "codex_captured_at": (time.time() - age_s
                              if captured_at is _UNSET else captured_at),
    }


class CodexRenderTest(unittest.TestCase):
    def test_fresh_reading(self):
        self.assertEqual(display.codex_parts(snapshot()),
                         ["CODEX 5h 42%", "7d 63%"])

    def test_login_required_only_when_truly_logged_out(self):
        self.assertEqual(display.codex_parts(snapshot(status="login_required")),
                         ["CODEX login required"])

    def test_no_snapshot_says_unavailable_not_login(self):
        """Logged in but nothing recorded yet must never read as a login
        problem — that's the mislabeling bug the Claude side shipped."""
        self.assertEqual(display.codex_parts(snapshot(status="unavailable")),
                         ["CODEX usage unavailable"])

    def test_unknown_status_is_unavailable(self):
        self.assertEqual(display.codex_parts(snapshot(status="something_new")),
                         ["CODEX usage unavailable"])

    def test_stale_reading_is_marked(self):
        """Codex only writes usage when it runs, so an old reading must be
        visibly old rather than pose as current."""
        parts = display.codex_parts(snapshot(age_s=3 * 3600))
        self.assertEqual(parts, ["CODEX 5h 42%", "7d 63%", "(3h ago)"])

    def test_fresh_reading_is_not_marked(self):
        parts = display.codex_parts(snapshot(age_s=60))
        self.assertNotIn("(1m ago)", parts)

    def test_rolled_over_window_shows_reset_not_a_number(self):
        parts = display.codex_parts(snapshot(windows=[
            {"label": "5h", "used_pct": 99.0, "rolled_over": True},
        ]))
        self.assertEqual(parts, ["CODEX 5h reset"])

    def test_arbitrary_windows_render(self):
        """Whatever windows the plan has is what shows up."""
        parts = display.codex_parts(snapshot(windows=[
            {"label": "3h", "used_pct": 10.0, "rolled_over": False},
            {"label": "30d", "used_pct": 5.0, "rolled_over": False},
        ]))
        self.assertEqual(parts, ["CODEX 3h 10%", "30d 5%"])

    def test_empty_windows_is_unavailable(self):
        self.assertEqual(display.codex_parts(snapshot(windows=[])),
                         ["CODEX usage unavailable"])

    def test_missing_percent_does_not_crash(self):
        parts = display.codex_parts(snapshot(windows=[
            {"label": "5h", "used_pct": None, "rolled_over": False},
        ]))
        self.assertEqual(parts, ["CODEX 5h ?"])

    def test_missing_label_falls_back(self):
        parts = display.codex_parts(snapshot(windows=[
            {"label": None, "used_pct": 12.0, "rolled_over": False},
        ]))
        self.assertEqual(parts, ["CODEX w1 12%"])

    def test_garbage_window_entries_are_skipped(self):
        parts = display.codex_parts(snapshot(windows=["nonsense"]))
        self.assertEqual(parts, ["CODEX usage unavailable"])

    def test_skipped_first_entry_still_labels_the_gauge(self):
        """If entry 0 is dropped, the surviving gauge must still say CODEX —
        otherwise it reads as another Claude window on the strip."""
        parts = display.codex_parts(snapshot(windows=[
            "nonsense",
            {"label": "7d", "used_pct": 80.0, "rolled_over": False},
        ]))
        self.assertEqual(parts, ["CODEX 7d 80%"])

    def test_missing_capture_time_is_unavailable(self):
        """Without a capture instant we can't say how old the reading is, so
        we must not present it as current."""
        parts = display.codex_parts(snapshot(captured_at=None))
        self.assertEqual(parts, ["CODEX usage unavailable"])

    def test_age_grows_when_collector_stops_updating(self):
        """Age is derived from the capture time, so a wedged collector shows a
        visibly ageing reading rather than one frozen at 'just now'."""
        s = snapshot(age_s=0)
        self.assertEqual(display.codex_parts(s), ["CODEX 5h 42%", "7d 63%"])
        # Same snapshot, read much later — no collector update in between.
        with mock.patch.object(display.time, "time",
                               return_value=time.time() + 4 * 3600):
            self.assertEqual(display.codex_parts(s),
                             ["CODEX 5h 42%", "7d 63%", "(4h ago)"])

    def test_boolean_percent_does_not_render_as_one_percent(self):
        parts = display.codex_parts(snapshot(windows=[
            {"label": "5h", "used_pct": True, "rolled_over": False},
        ]))
        self.assertEqual(parts, ["CODEX 5h ?"])


class BuildTextTest(unittest.TestCase):
    """build_text has never had coverage; these pin the whole-strip shape."""

    def setUp(self):
        import time
        display._snapshot.clear()
        display._snapshot.update({
            "cpu_pct": 12, "ram_pct": 34, "disk_pct": 56,
            "gpus": [{"index": 0, "util_pct": 7}],
            "updated_at": time.time(),
            "claude_status": "ok", "claude_active": True,
            "claude_5h_pct": 20.0, "claude_week_pct": 30.0,
            **snapshot(),
        })
        self.addCleanup(display._snapshot.clear)

    def test_full_strip(self):
        with mock.patch.object(display.config, "CLAUDE_ENABLED", True), \
             mock.patch.object(display.config, "CODEX_ENABLED", True):
            text = display.build_text()
        self.assertIn("CPU 12%", text)
        self.assertIn("CLAUDE 5h 20%", text)
        self.assertIn("CODEX 5h 42%", text)

    def test_codex_disabled_hides_gauges(self):
        with mock.patch.object(display.config, "CLAUDE_ENABLED", True), \
             mock.patch.object(display.config, "CODEX_ENABLED", False):
            text = display.build_text()
        self.assertNotIn("CODEX", text)
        self.assertIn("CLAUDE", text)

    def test_stale_collector_hides_everything(self):
        display._snapshot["updated_at"] = 0
        self.assertEqual(display.build_text(), "collector stalled — data stale")


if __name__ == "__main__":
    unittest.main()

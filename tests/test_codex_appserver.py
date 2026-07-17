"""Tests for the live (zero-token) Codex usage source.

Fixtures mirror a real `account/rateLimits/read` reply captured from
codex 0.144.5 — note camelCase (usedPercent, windowDurationMins, resetsAt)
where the rollout log uses snake_case for the same three facts.

The app-server is experimental, so the contract under test is mostly about
degrading: anything unexpected must return None so the caller falls back to
the log, never a wrong number.
"""
import subprocess
import time
import unittest
from unittest import mock

from statstrip import codex_appserver, collector


def reply(used=10, window=10080, resets_at=None, **kw):
    snap = {
        "limitId": "codex",
        "limitName": None,
        "primary": {"usedPercent": used, "windowDurationMins": window,
                    "resetsAt": resets_at if resets_at is not None
                    else int(time.time() + window * 60 / 2)},
        "secondary": None,
        "credits": {"hasCredits": False, "unlimited": False, "balance": "0"},
        "individualLimit": None,
        "planType": "plus",
        "rateLimitReachedType": None,
    }
    snap.update(kw)
    return {"id": 2, "result": {"rateLimits": snap,
                                "rateLimitsByLimitId": {"codex": snap}}}


class ResetCooldown(unittest.TestCase):
    """The live source's cooldown is module state; without clearing it, one
    failing test would silently suppress the next one's call."""

    def setUp(self):
        codex_appserver._fail_count = 0
        codex_appserver._next_attempt = 0.0
        self.addCleanup(setattr, codex_appserver, "_fail_count", 0)
        self.addCleanup(setattr, codex_appserver, "_next_attempt", 0.0)


class ParseTest(ResetCooldown):
    def collect_with(self, msg):
        with mock.patch.object(codex_appserver, "_codex_exe",
                               return_value="codex.exe"), \
             mock.patch.object(codex_appserver, "_rpc_read", return_value=msg):
            return codex_appserver.collect()

    def test_real_reply_shape(self):
        """Verbatim shape captured from codex 0.144.5."""
        windows, at = self.collect_with(reply(used=10))
        self.assertEqual(windows, [{"label": "7d", "used_pct": 10.0,
                                    "rolled_over": False}])
        self.assertAlmostEqual(at, time.time(), delta=2)

    def test_live_reading_is_never_stale(self):
        """It's fetched now, so captured_at is now — no age marker."""
        _, at = self.collect_with(reply())
        self.assertLess(time.time() - at, 2)

    def test_both_windows_render_in_protocol_order(self):
        r = reply(used=12)
        r["result"]["rateLimits"]["secondary"] = {
            "usedPercent": 40, "windowDurationMins": 300,
            "resetsAt": int(time.time() + 600),
        }
        windows, _ = self.collect_with(r)
        self.assertEqual([(w["label"], w["used_pct"]) for w in windows],
                         [("7d", 12.0), ("5h", 40.0)])

    def test_credits_and_plan_metadata_are_not_windows(self):
        windows, _ = self.collect_with(reply())
        self.assertEqual(len(windows), 1)

    def test_falls_back_to_by_limit_id_view(self):
        r = reply(used=7)
        del r["result"]["rateLimits"]
        windows, _ = self.collect_with(r)
        self.assertEqual(windows[0]["used_pct"], 7.0)

    # --- degrading -----------------------------------------------------------

    def test_error_reply_falls_back(self):
        """Not signed in, or method unknown on an older codex."""
        self.assertIsNone(self.collect_with(
            {"id": 2, "error": {"code": -32601, "message": "unknown method"}}))

    def test_no_reply_falls_back(self):
        self.assertIsNone(self.collect_with(None))

    def test_unknown_shape_falls_back(self):
        self.assertIsNone(self.collect_with({"id": 2, "result": {"nope": 1}}))

    def test_out_of_range_percent_falls_back(self):
        self.assertIsNone(self.collect_with(reply(used=-1)))

    def test_missing_codex_binary_falls_back(self):
        with mock.patch.object(codex_appserver, "_codex_exe", return_value=None):
            self.assertIsNone(codex_appserver.collect())

    def test_rpc_exception_falls_back(self):
        with mock.patch.object(codex_appserver, "_codex_exe",
                               return_value="codex.exe"), \
             mock.patch.object(codex_appserver, "_rpc_read",
                               side_effect=OSError("spawn failed")):
            self.assertIsNone(codex_appserver.collect())


class ReplyMatchingTest(unittest.TestCase):
    def test_our_reply_is_accepted(self):
        self.assertTrue(codex_appserver._is_reply({"id": 2, "result": {}}))
        self.assertTrue(codex_appserver._is_reply({"id": 2, "error": {}}))

    def test_server_request_sharing_our_id_is_not_our_reply(self):
        """JSON-RPC ids are per-direction: the server numbers its own requests
        from its own counter, so id==2 alone doesn't mean it's ours."""
        self.assertFalse(codex_appserver._is_reply(
            {"id": 2, "method": "loginChatGptComplete", "params": {}}))

    def test_other_ids_ignored(self):
        self.assertFalse(codex_appserver._is_reply({"id": 1, "result": {}}))


class SnapshotSelectionTest(unittest.TestCase):
    def test_unknown_limit_bucket_is_refused(self):
        """Only the "codex" bucket meters Codex. Rendering some other limit's
        percentage as Codex usage would be a confident wrong number."""
        msg = {"id": 2, "result": {"rateLimitsByLimitId": {
            "org-seat": {"primary": {"usedPercent": 91,
                                     "windowDurationMins": 10080}}}}}
        self.assertIsNone(codex_appserver._snapshot_from(msg))

    def test_codex_bucket_is_used(self):
        msg = {"id": 2, "result": {"rateLimitsByLimitId": {
            "codex": {"primary": {"usedPercent": 5, "windowDurationMins": 10080}}}}}
        self.assertIsNotNone(codex_appserver._snapshot_from(msg))


class LiveFreshnessTest(ResetCooldown):
    def test_live_reading_never_renders_as_reset(self):
        """A reading fetched now can't predate a reset — the server already
        applied it. Marking it "reset" would throw away a correct number."""
        r = reply(used=3, resets_at=int(time.time()) - 30)  # just reset
        with mock.patch.object(codex_appserver, "_codex_exe",
                               return_value="codex.exe"), \
             mock.patch.object(codex_appserver, "_rpc_read", return_value=r):
            windows, _ = codex_appserver.collect()
        self.assertFalse(windows[0]["rolled_over"])
        self.assertEqual(windows[0]["used_pct"], 3.0)


class CooldownTest(ResetCooldown):
    def collect_failing(self):
        with mock.patch.object(codex_appserver, "_codex_exe",
                               return_value="codex.exe"), \
             mock.patch.object(codex_appserver, "_rpc_read", return_value=None) as r:
            return codex_appserver.collect(), r

    def test_repeated_failure_stops_spawning_every_poll(self):
        """A wedged app-server costs a spawn and up to TIMEOUT seconds per
        poll; don't pay that every minute when the log is answering."""
        self.collect_failing()  # first failure arms the cooldown
        _, rpc = self.collect_failing()
        rpc.assert_not_called()

    def test_cooldown_grows_and_is_capped(self):
        for _ in range(3):
            codex_appserver._next_attempt = 0.0  # let each attempt through
            self.collect_failing()
        self.assertGreaterEqual(codex_appserver._fail_count, 3)
        codex_appserver._next_attempt = 0.0
        for _ in range(20):
            codex_appserver._next_attempt = 0.0
            self.collect_failing()
        self.assertLessEqual(codex_appserver._next_attempt - time.time(),
                             codex_appserver._COOLDOWN_MAX + 1)

    def test_success_clears_the_cooldown(self):
        self.collect_failing()
        codex_appserver._next_attempt = 0.0
        with mock.patch.object(codex_appserver, "_codex_exe",
                               return_value="codex.exe"), \
             mock.patch.object(codex_appserver, "_rpc_read", return_value=reply()):
            self.assertIsNotNone(codex_appserver.collect())
        self.assertEqual(codex_appserver._fail_count, 0)
        self.assertEqual(codex_appserver._next_attempt, 0.0)


class ShutdownTest(unittest.TestCase):
    """The child is spawned every 60s forever under pythonw. A leaked process
    or thread per poll compounds silently over days."""

    def fake_proc(self, exits=True):
        proc = mock.MagicMock()
        proc.pid = 4321
        proc.stdin.closed = False
        proc.stdout.closed = False
        if not exits:
            proc.wait.side_effect = subprocess.TimeoutExpired("codex", 5)
        return proc

    def test_stdin_is_closed_first(self):
        """Closing stdin is how the app-server exits, and how the reader sees
        EOF and unblocks. Skipping it leaks a thread per poll."""
        proc = self.fake_proc()
        reader = mock.MagicMock()
        codex_appserver._shutdown(proc, reader)
        proc.stdin.close.assert_called_once()
        reader.join.assert_called_once()

    def test_wedged_child_gets_its_whole_tree_killed(self):
        """codex is a .cmd shim: cmd.exe -> node.exe -> codex.exe. Killing only
        the shim orphans the app-server on every failed poll, forever."""
        proc = self.fake_proc(exits=False)
        with mock.patch.object(codex_appserver.os, "name", "nt"), \
             mock.patch.object(codex_appserver.subprocess, "run") as run:
            codex_appserver._shutdown(proc, mock.MagicMock())
        args = run.call_args[0][0]
        self.assertEqual(args[:3], ["taskkill", "/T", "/F"])
        self.assertIn("4321", args)

    def test_reader_is_always_joined(self):
        proc = self.fake_proc(exits=False)
        reader = mock.MagicMock()
        with mock.patch.object(codex_appserver.subprocess, "run"):
            codex_appserver._shutdown(proc, reader)
        reader.join.assert_called_once()

    def test_shutdown_survives_a_broken_proc(self):
        proc = mock.MagicMock()
        proc.pid = 1
        proc.stdin.close.side_effect = OSError("already gone")
        proc.wait.side_effect = OSError("gone")
        with mock.patch.object(codex_appserver.subprocess, "run",
                               side_effect=OSError("no taskkill")):
            codex_appserver._shutdown(proc, mock.MagicMock())  # must not raise


class SourceSelectionTest(unittest.TestCase):
    """The collector must prefer live and fall back to the log."""

    def setUp(self):
        self.live = ([{"label": "7d", "used_pct": 10.0, "rolled_over": False}],
                     time.time())
        self.log = ([{"label": "7d", "used_pct": 4.0, "rolled_over": False}],
                    time.time() - 3600)

    def test_live_wins_when_available(self):
        with mock.patch.object(collector.config, "CODEX_ENABLED", True), \
             mock.patch.object(collector.config, "CODEX_LIVE", True), \
             mock.patch("statstrip.codex_appserver.collect", return_value=self.live), \
             mock.patch("statstrip.codex_local.collect", return_value=self.log):
            windows, _, status, _src = collector.collect_codex()
        self.assertEqual(status, "ok")
        self.assertEqual(windows[0]["used_pct"], 10.0)  # not the stale 4%

    def test_falls_back_to_log_when_live_unavailable(self):
        with mock.patch.object(collector.config, "CODEX_ENABLED", True), \
             mock.patch.object(collector.config, "CODEX_LIVE", True), \
             mock.patch("statstrip.codex_appserver.collect", return_value=None), \
             mock.patch("statstrip.codex_local.collect", return_value=self.log):
            windows, _, status, _src = collector.collect_codex()
        self.assertEqual(status, "ok")
        self.assertEqual(windows[0]["used_pct"], 4.0)

    def test_log_mode_never_calls_the_app_server(self):
        with mock.patch.object(collector.config, "CODEX_ENABLED", True), \
             mock.patch.object(collector.config, "CODEX_LIVE", False), \
             mock.patch("statstrip.codex_appserver.collect") as live, \
             mock.patch("statstrip.codex_local.collect", return_value=self.log):
            collector.collect_codex()
        live.assert_not_called()

    def test_login_required_still_reported_via_the_log(self):
        with mock.patch.object(collector.config, "CODEX_ENABLED", True), \
             mock.patch.object(collector.config, "CODEX_LIVE", True), \
             mock.patch("statstrip.codex_appserver.collect", return_value=None), \
             mock.patch("statstrip.codex_local.collect", return_value="login_required"):
            _, _, status, _src = collector.collect_codex()
        self.assertEqual(status, "login_required")


if __name__ == "__main__":
    unittest.main()

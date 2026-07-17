"""Tests for the Codex session-log reader.

These lean on synthetic rollout files rather than a real ~/.codex, because
the rollout format is Codex's internal business and we want the failure
modes pinned down: an unreadable or unfamiliar log must degrade to "no
reading", never to a confident wrong percentage.
"""
import json
import os
import time
import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from statstrip import codex_local


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def ago(seconds):
    return iso(datetime.now(timezone.utc) - timedelta(seconds=seconds))


def window(used, window_minutes, resets_in=None, captured=None):
    """One rate-limit window, shaped the way Codex 0.144.5 actually writes it:
    an absolute `resets_at` epoch, not a relative offset."""
    base = captured if captured is not None else time.time()
    return {
        "used_percent": used,
        "window_minutes": window_minutes,
        "resets_at": base + (resets_in if resets_in is not None
                             else window_minutes * 60 / 2),
    }


def rollout_line(used_primary=10.0, used_secondary=50.0, ts=None,
                 primary_window=300, secondary_window=10080,
                 primary_resets=None, secondary_resets=None):
    """One token_count event, shaped the way Codex writes them.

    Mirrors a payload captured from a real Codex turn, including the fields
    this parser must ignore (limit_id, credits, plan_type) and the null
    `secondary` a single-window plan sends.
    """
    ts = ts or ago(5)
    captured = _parse_or_now(ts)
    return json.dumps({
        "timestamp": ts,
        "type": "event_msg",
        "payload": {
            "type": "token_count",
            "rate_limits": {
                "limit_id": "codex",
                "limit_name": None,
                "primary": None if used_primary is None else window(
                    used_primary, primary_window, primary_resets, captured),
                "secondary": None if used_secondary is None else window(
                    used_secondary, secondary_window, secondary_resets,
                    captured),
                "credits": {"has_credits": False, "unlimited": False,
                            "balance": "0"},
                "individual_limit": None,
                "plan_type": "plus",
                "rate_limit_reached_type": None,
            },
        },
    })


def _parse_or_now(ts):
    from statstrip.codex_local import _parse_timestamp
    return _parse_timestamp(ts) or time.time()


class CodexHome:
    """A fake Codex home, pointed at via CODEX_HOME."""

    def __init__(self, stack, logged_in=True, make_sessions=True):
        self.root = Path(stack.enter_context(TemporaryDirectory()))
        self.sessions = self.root / "sessions" / "2026" / "07" / "17"
        if make_sessions:
            self.sessions.mkdir(parents=True)
        if logged_in:
            (self.root / "auth.json").write_text("{}", encoding="utf-8")
        stack.enter_context(
            mock.patch.dict(os.environ, {"CODEX_HOME": str(self.root)})
        )
        # An API key in the real environment would change the login verdict.
        stack.enter_context(
            mock.patch.dict(os.environ, {}, clear=False)
        )
        os.environ.pop("OPENAI_API_KEY", None)

    def write(self, name, lines, mtime=None, subdir=None):
        d = self.sessions if subdir is None else self.root / "sessions" / subdir
        d.mkdir(parents=True, exist_ok=True)
        p = d / name
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        if mtime:
            os.utime(p, (mtime, mtime))
        return p


class ReaderTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)

    def test_reads_latest_snapshot(self):
        home = CodexHome(self.stack)
        home.write("rollout-a.jsonl", [
            rollout_line(used_primary=1.0, ts=ago(600)),
            rollout_line(used_primary=42.0, used_secondary=63.0, ts=ago(5)),
        ])
        windows, captured_at = codex_local.collect()
        self.assertEqual([w["used_pct"] for w in windows], [42.0, 63.0])
        self.assertLess(time.time() - captured_at, 60)

    def test_labels_come_from_reported_window(self):
        """Windows are named by what Codex reports, not hardcoded to 5h/week —
        a plan with different windows must still read correctly."""
        home = CodexHome(self.stack)
        home.write("rollout-a.jsonl", [
            rollout_line(primary_window=180, secondary_window=4320),
        ])
        windows, _ = codex_local.collect()
        self.assertEqual([w["label"] for w in windows], ["3h", "3d"])

    def test_default_windows_label_as_5h_and_7d(self):
        home = CodexHome(self.stack)
        home.write("rollout-a.jsonl", [rollout_line()])
        windows, _ = codex_local.collect()
        self.assertEqual([w["label"] for w in windows], ["5h", "7d"])

    def test_rolled_over_window_is_flagged(self):
        """A snapshot whose window has since reset holds a number we know is
        wrong; it must not be reported as a live percentage."""
        home = CodexHome(self.stack)
        home.write("rollout-a.jsonl", [
            rollout_line(ts=ago(7200), primary_resets=60,
                         secondary_window=10080, secondary_resets=500000),
        ])
        windows, _ = codex_local.collect()
        self.assertTrue(windows[0]["rolled_over"])   # reset 60s after capture
        self.assertFalse(windows[1]["rolled_over"])  # still open

    def test_real_payload_from_codex_0_144_5(self):
        """Verbatim rate_limits captured from a real Codex turn. Pins the two
        things a synthetic fixture got wrong: resets is an absolute `resets_at`
        epoch, and a single-window plan puts the *weekly* window in `primary`
        with `secondary` null — so "primary is the 5h block" is not a safe
        assumption."""
        home = CodexHome(self.stack)
        captured = time.time() - 9
        home.write("rollout-real.jsonl", [json.dumps({
            "timestamp": iso(datetime.fromtimestamp(captured, timezone.utc)),
            "type": "event_msg",
            "payload": {"type": "token_count", "rate_limits": {
                "limit_id": "codex",
                "limit_name": None,
                "primary": {"used_percent": 4.0, "window_minutes": 10080,
                            "resets_at": captured + 599938},
                "secondary": None,
                "credits": {"has_credits": False, "unlimited": False,
                            "balance": "0"},
                "individual_limit": None,
                "plan_type": "plus",
                "rate_limit_reached_type": None,
            }},
        })])
        windows, at = codex_local.collect()
        self.assertEqual(windows, [{"label": "7d", "used_pct": 4.0,
                                    "rolled_over": False}])
        self.assertAlmostEqual(at, captured, delta=1)

    def test_absolute_resets_at_is_used(self):
        home = CodexHome(self.stack)
        captured = time.time() - 7200
        home.write("rollout-a.jsonl", [json.dumps({
            "timestamp": iso(datetime.fromtimestamp(captured, timezone.utc)),
            "payload": {"rate_limits": {"primary": {
                "used_percent": 90.0, "window_minutes": 300,
                "resets_at": captured + 60,  # reset an hour before now
            }}},
        })])
        windows, _ = codex_local.collect()
        self.assertTrue(windows[0]["rolled_over"])

    def test_relative_resets_in_seconds_still_accepted(self):
        """The format is undocumented; tolerate the relative form too."""
        home = CodexHome(self.stack)
        captured = time.time() - 7200
        home.write("rollout-a.jsonl", [json.dumps({
            "timestamp": iso(datetime.fromtimestamp(captured, timezone.utc)),
            "payload": {"rate_limits": {"primary": {
                "used_percent": 90.0, "window_minutes": 300,
                "resets_in_seconds": 60,
            }}},
        })])
        windows, _ = codex_local.collect()
        self.assertTrue(windows[0]["rolled_over"])

    def test_implausible_reset_is_ignored_not_guessed(self):
        """A resets_at in milliseconds (or any unit change) must not mark a
        live window as rolled over, nor hide a stale one."""
        home = CodexHome(self.stack)
        captured = time.time() - 60
        home.write("rollout-a.jsonl", [json.dumps({
            "timestamp": iso(datetime.fromtimestamp(captured, timezone.utc)),
            "payload": {"rate_limits": {"primary": {
                "used_percent": 50.0, "window_minutes": 300,
                "resets_at": (captured + 600) * 1000,  # ms, not s
            }}},
        })])
        windows, _ = codex_local.collect()
        self.assertFalse(windows[0]["rolled_over"])

    def test_null_secondary_yields_single_window(self):
        """A plan with one window must show that window, not a placeholder."""
        home = CodexHome(self.stack)
        home.write("rollout-a.jsonl", [
            rollout_line(used_secondary=None, primary_window=10080,
                         used_primary=4.0),
        ])
        windows, _ = codex_local.collect()
        self.assertEqual([(w["label"], w["used_pct"]) for w in windows],
                         [("7d", 4.0)])

    def test_credits_block_is_not_mistaken_for_a_window(self):
        home = CodexHome(self.stack)
        home.write("rollout-a.jsonl", [rollout_line(used_secondary=None)])
        windows, _ = codex_local.collect()
        self.assertEqual(len(windows), 1)

    # --- login classification -------------------------------------------------

    def test_no_auth_is_login_required(self):
        home = CodexHome(self.stack, logged_in=False)
        home.write("rollout-a.jsonl", [json.dumps({"type": "user_message"})])
        self.assertEqual(codex_local.collect(), "login_required")

    def test_logged_in_but_no_sessions_is_not_login_required(self):
        """A fresh Codex install has a login but no turns yet. Sending that
        user off to log in again would be a lie — same trap the Claude side
        fell into with rate limits."""
        CodexHome(self.stack)
        self.assertIsNone(codex_local.collect())

    def test_codex_not_installed_is_not_login_required(self):
        """No Codex home at all means Codex isn't set up here — that's not an
        auth problem to nag about."""
        with TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nope"
            with mock.patch.dict(os.environ, {"CODEX_HOME": str(missing)}):
                self.assertIsNone(codex_local.collect())

    def test_api_key_auth_is_not_login_required(self):
        CodexHome(self.stack, logged_in=False)
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
            self.assertIsNone(codex_local.collect())

    def test_readable_usage_never_says_login_required(self):
        """If we can read real usage, 'log in' is definitionally wrong."""
        home = CodexHome(self.stack, logged_in=False)
        home.write("rollout-a.jsonl", [rollout_line(used_primary=15.0)])
        windows, _ = codex_local.collect()
        self.assertEqual(windows[0]["used_pct"], 15.0)

    def test_relocated_codex_home_is_honoured(self):
        """A logged-in user with CODEX_HOME set must not be told to log in."""
        home = CodexHome(self.stack)
        home.write("rollout-a.jsonl", [rollout_line(used_primary=77.0)])
        windows, _ = codex_local.collect()
        self.assertEqual(windows[0]["used_pct"], 77.0)

    # --- timestamps -----------------------------------------------------------

    def test_naive_timestamp_is_rejected(self):
        """A zone-less timestamp would be read as local time, inventing an age
        (and on some machines a capture in the future, which would make a
        stale snapshot look brand new)."""
        home = CodexHome(self.stack)
        home.write("rollout-a.jsonl", [
            rollout_line(ts="2026-07-17T06:00:00.000"),
        ])
        self.assertIsNone(codex_local.collect())

    def test_future_timestamp_is_rejected(self):
        """A capture in the future means we misread it — no reading beats a
        reading we'd clamp to '0 seconds old'."""
        home = CodexHome(self.stack)
        home.write("rollout-a.jsonl", [rollout_line(ts=ago(-3600))])
        self.assertIsNone(codex_local.collect())

    def test_nanosecond_precision_parses(self):
        """Rust emits 9 fractional digits; fromisoformat rejects that before
        3.11 and this package supports 3.9."""
        home = CodexHome(self.stack)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        home.write("rollout-a.jsonl", [
            rollout_line(used_primary=31.0, ts=f"{stamp}.123456789Z"),
        ])
        windows, _ = codex_local.collect()
        self.assertEqual(windows[0]["used_pct"], 31.0)

    def test_numeric_offset_timestamp_parses(self):
        home = CodexHome(self.stack)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        home.write("rollout-a.jsonl", [
            rollout_line(used_primary=8.0, ts=f"{stamp}.000+00:00"),
        ])
        windows, _ = codex_local.collect()
        self.assertEqual(windows[0]["used_pct"], 8.0)

    def test_no_mtime_fallback_for_missing_timestamp(self):
        """mtime is the last write of any line, which can be hours newer than
        the last usage snapshot — using it would make an old reading current."""
        home = CodexHome(self.stack)
        home.write("rollout-a.jsonl", [
            json.dumps({"payload": {"rate_limits": {
                "primary": {"used_percent": 50.0, "window_minutes": 300,
                            "resets_in_seconds": 600}}}}),
        ])
        self.assertIsNone(codex_local.collect())

    # --- schema robustness ----------------------------------------------------

    def test_unparseable_lines_are_skipped(self):
        home = CodexHome(self.stack)
        home.write("rollout-a.jsonl", [
            "{not json at all",
            rollout_line(used_primary=7.0),
            '"rate_limits but a bare string"',
        ])
        windows, _ = codex_local.collect()
        self.assertEqual(windows[0]["used_pct"], 7.0)

    def test_unknown_schema_yields_no_reading(self):
        """If Codex renames things, we want silence, not a wrong number."""
        home = CodexHome(self.stack)
        home.write("rollout-a.jsonl", [
            json.dumps({"timestamp": ago(5),
                        "payload": {"rate_limits": {"primary": {"pct": 12}}}}),
        ])
        self.assertIsNone(codex_local.collect())

    def test_out_of_range_percent_is_refused(self):
        """A sentinel or a unit change must not render as 'CODEX 5h -1%'."""
        home = CodexHome(self.stack)
        home.write("rollout-a.jsonl", [
            rollout_line(used_primary=-1.0, used_secondary=350.0),
        ])
        self.assertIsNone(codex_local.collect())

    def test_boolean_percent_is_refused(self):
        """bool is an int in Python; True must never read as 1%."""
        home = CodexHome(self.stack)
        home.write("rollout-a.jsonl", [
            json.dumps({"timestamp": ago(5), "payload": {"rate_limits": {
                "primary": {"used_percent": True, "window_minutes": 300,
                            "resets_in_seconds": 600}}}}),
        ])
        self.assertIsNone(codex_local.collect())

    def test_partly_valid_snapshot_keeps_good_windows(self):
        home = CodexHome(self.stack)
        home.write("rollout-a.jsonl", [
            rollout_line(used_primary=20.0, used_secondary=999.0),
        ])
        windows, _ = codex_local.collect()
        self.assertEqual([w["used_pct"] for w in windows], [20.0])

    def test_nesting_change_still_found(self):
        """rate_limits is located structurally, so a nesting change doesn't
        break the reading."""
        home = CodexHome(self.stack)
        home.write("rollout-a.jsonl", [
            json.dumps({
                "timestamp": ago(5),
                "payload": {"info": {"deeper": {"rate_limits": {
                    "primary": {"used_percent": 33.0, "window_minutes": 300,
                                "resets_in_seconds": 600},
                }}}},
            }),
        ])
        windows, _ = codex_local.collect()
        self.assertEqual(windows[0]["used_pct"], 33.0)

    # --- picking the right snapshot -------------------------------------------

    def test_newest_snapshot_wins_not_newest_file(self):
        """A session touched by a cancelled turn has the newest mtime but a
        stale snapshot; the fresher reading in the other session must win."""
        home = CodexHome(self.stack)
        now = time.time()
        home.write("rollout-fresh.jsonl",
                   [rollout_line(used_primary=85.0, ts=ago(120))],
                   mtime=now - 120)
        home.write("rollout-touched.jsonl", [
            rollout_line(used_primary=30.0, ts=ago(720)),
            json.dumps({"type": "user_message", "timestamp": ago(2)}),
        ], mtime=now)
        windows, _ = codex_local.collect()
        self.assertEqual(windows[0]["used_pct"], 85.0)

    def test_falls_back_to_older_session_without_snapshot(self):
        """The newest session may not have made an API call yet."""
        home = CodexHome(self.stack)
        now = time.time()
        home.write("rollout-old.jsonl", [rollout_line(used_primary=21.0)],
                   mtime=now - 10000)
        home.write("rollout-new.jsonl", [json.dumps({"type": "user_message"})],
                   mtime=now)
        windows, _ = codex_local.collect()
        self.assertEqual(windows[0]["used_pct"], 21.0)

    def test_searches_newest_date_directories_first(self):
        """Sessions are date-partitioned and never pruned; the reader must
        find today's without walking all of history."""
        home = CodexHome(self.stack)
        home.write("rollout-old.jsonl", [rollout_line(used_primary=3.0)],
                   subdir="2025/01/01")
        home.write("rollout-today.jsonl", [rollout_line(used_primary=64.0)])
        windows, _ = codex_local.collect()
        self.assertEqual(windows[0]["used_pct"], 64.0)

    def test_vanishing_file_does_not_raise(self):
        """Codex or a cleanup can delete a rollout mid-scan; a poll may be
        lost but the reader must not throw into the collector loop."""
        home = CodexHome(self.stack)
        home.write("rollout-a.jsonl", [rollout_line(used_primary=12.0)])
        real_scandir = os.scandir

        def racing_scandir(path):
            entries = list(real_scandir(path))
            for e in entries:
                if e.name.endswith(".jsonl"):
                    os.unlink(e.path)  # gone before we stat it
            return iter(entries)

        with mock.patch.object(codex_local.os, "scandir", racing_scandir):
            self.assertIsNone(codex_local.collect())

    def test_unreadable_sessions_dir_does_not_raise(self):
        home = CodexHome(self.stack)
        with mock.patch.object(codex_local.os, "scandir",
                               side_effect=PermissionError("denied")):
            self.assertIsNone(codex_local.collect())


if __name__ == "__main__":
    unittest.main()

"""Codex usage from Codex CLI's own session logs — no network, no token.

Codex records a rate-limit snapshot in its session rollout files
(<codex home>/sessions/YYYY/MM/DD/rollout-*.jsonl) every time it talks to the
API: the same numbers its /status command shows. We read the most recent
snapshot instead of calling an API, which means no credentials leave this
machine, nothing can rate-limit us, and there's no auth state to misreport
(the two bugs the Claude side hit — see claude_oauth.py).

The tradeoff is freshness: a snapshot is only as current as your last Codex
turn. So a reading carries the instant it was captured, and a window whose
reset time has already passed is reported as rolled-over rather than shown
as a live percentage — stale usage numbers that look live are worse than no
numbers at all.

Window names come from Codex, not from us. It reports how long each window
is (window_minutes) and we label it from that, so whatever windows a plan
actually has — 5h/weekly or otherwise — is what shows up.

The rollout format is internal to Codex and undocumented: every field is
treated as optional, anything outside its expected contract means
"unavailable" (transient), never a confident wrong number.
"""
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

# Cap how much of a rollout we read backwards looking for a snapshot. The
# newest snapshot is at the tail, and this runs on a 60s poll.
_MAX_SCAN_BYTES = 512 * 1024
_MAX_SESSIONS_TRIED = 5

# A timestamp this far in the future means we don't understand it (clock
# skew, wrong units, a timezone we misread) — better no reading than a
# nonsense age. Small enough to catch a timezone error, big enough to
# tolerate ordinary clock drift.
_FUTURE_TOLERANCE = 120  # seconds


def _codex_home():
    # Codex honours CODEX_HOME; read it per call so it isn't frozen at import
    # (the collector starts at login, before a user env change may apply).
    override = os.environ.get("CODEX_HOME")
    return Path(override) if override else Path.home() / ".codex"


def _newest_rollouts(limit=_MAX_SESSIONS_TRIED):
    """Up to `limit` most recently modified rollout files, newest first.

    Sessions are date-partitioned (YYYY/MM/DD) and Codex never prunes them,
    so this descends newest-directory-first and stops as soon as it has
    enough candidates rather than walking (and stat-ing) a year of history
    every poll.
    """
    root = _codex_home() / "sessions"
    found = []

    def walk(path):
        """True once we have enough candidates."""
        try:
            entries = list(os.scandir(path))
        except OSError:
            return False  # vanished or unreadable — just skip it
        dirs, files = [], []
        for e in entries:
            try:
                if e.is_dir():
                    dirs.append(e)
                elif e.is_file() and e.name.endswith(".jsonl"):
                    # DirEntry.stat() is cached, unlike Path.stat()
                    files.append((e.stat().st_mtime, Path(e.path)))
            except OSError:
                continue  # deleted between scandir and stat
        files.sort(key=lambda t: t[0], reverse=True)
        found.extend(files)
        if len(found) >= limit:
            return True
        # Date-partitioned, so descending name order is newest-first.
        for d in sorted(dirs, key=lambda e: e.name, reverse=True):
            if walk(d.path):
                return True
        return False

    try:
        walk(root)
    except Exception:
        return []
    found.sort(key=lambda t: t[0], reverse=True)
    return [p for _, p in found[:limit]]


def _tail_lines(path, max_bytes=_MAX_SCAN_BYTES):
    """Last chunk of a file as lines, oldest first."""
    try:
        size = path.stat().st_size
        with open(path, "rb") as f:
            if size > max_bytes:
                f.seek(size - max_bytes)
                f.readline()  # discard the partial line the seek landed in
            return f.read().decode("utf-8", "replace").splitlines()
    except Exception:
        return []


def _find_rate_limits(obj, depth=0):
    """Pull the rate_limits dict out of a rollout line.

    Searched structurally rather than by a fixed path (payload.rate_limits
    today) so a nesting change in Codex demotes us to 'no snapshot found'
    instead of a crash or a stale reading.
    """
    if depth > 6 or not isinstance(obj, dict):
        return None
    rl = obj.get("rate_limits")
    if isinstance(rl, dict) and rl:
        return rl
    for v in obj.values():
        if isinstance(v, dict):
            found = _find_rate_limits(v, depth + 1)
            if found:
                return found
    return None


def _number(v):
    # bool is an int in Python; True must never read as a percentage.
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _label(window_minutes):
    """Codex names its own windows by length; render them the way a person
    would say them ("5h", "7d")."""
    minutes = _number(window_minutes)
    if minutes is None or minutes <= 0:
        return None
    minutes = int(round(minutes))
    if minutes < 60:
        return f"{minutes}m"
    if minutes < 24 * 60:
        hours = minutes / 60
        return f"{hours:.0f}h" if abs(hours - round(hours)) < 0.05 else f"{hours:.1f}h"
    days = minutes / (24 * 60)
    return f"{days:.0f}d" if abs(days - round(days)) < 0.05 else f"{days:.1f}d"


def _window(entry, captured_at, now):
    if not isinstance(entry, dict):
        return None
    used = _number(entry.get("used_percent"))
    # Out of [0, 100] means the field no longer means what we assume (a
    # sentinel, a unit change) — the only cheap signal we get that this
    # parser is out of date. Refuse it rather than print "CODEX 5h -1%".
    if used is None or not 0 <= used <= 100:
        return None
    resets_in = _number(entry.get("resets_in_seconds"))
    # The snapshot's window may have rolled over since it was written, which
    # resets usage to zero. We can't know the new figure, but we do know the
    # old one is wrong — say so rather than show it.
    rolled_over = resets_in is not None and now > captured_at + resets_in
    return {
        "label": _label(entry.get("window_minutes")),
        "used_pct": float(used),
        "rolled_over": bool(rolled_over),
    }


# Codex is Rust and emits RFC3339 with nanosecond precision, which
# datetime.fromisoformat rejects before 3.11 — and this package supports 3.9.
# Parse it ourselves rather than depend on the interpreter's strictness.
_TS_RE = re.compile(
    r"^(?P<base>\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}:\d{2})"
    r"(?:\.(?P<frac>\d+))?"
    r"(?P<tz>[Zz]|[+-]\d{2}:?\d{2})$"
)


def _parse_timestamp(ts):
    """Epoch seconds from Codex's timestamp, or None if we can't be sure.

    A timestamp without a zone is rejected rather than guessed: fromisoformat
    would silently read it as local time, which on any non-UTC machine
    invents an age (and can push the capture into the future, making a stale
    snapshot look brand new).
    """
    if not isinstance(ts, str):
        return None
    m = _TS_RE.match(ts.strip())
    if not m:
        return None
    frac = (m.group("frac") or "0")[:6].ljust(6, "0")  # ns -> us
    tz = m.group("tz")
    tz = "+00:00" if tz in ("Z", "z") else tz
    if len(tz) == 5:  # +0000 -> +00:00
        tz = tz[:3] + ":" + tz[3:]
    try:
        dt = datetime.fromisoformat(f"{m.group('base')}.{frac}{tz}")
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None
    return dt.timestamp()


def _captured_at(line_obj, now):
    """When this snapshot was taken, or None if we can't establish it.

    There's deliberately no file-mtime fallback: mtime is the last write of
    any line, which in a long-lived session can be hours newer than the last
    rate-limit snapshot — it would make an old reading look current, the
    exact failure this module exists to avoid.
    """
    at = _parse_timestamp(line_obj.get("timestamp"))
    if at is None:
        return None
    # A capture in the future means we've misread it. Don't clamp it to
    # "0 seconds old" — that would launder the error into a live reading.
    if at > now + _FUTURE_TOLERANCE:
        return None
    return at


def _snapshot_from(path, now):
    """Newest usable (captured_at, windows) in one rollout, or None."""
    for line in reversed(_tail_lines(path)):
        line = line.strip()
        if not line or "rate_limits" not in line:
            continue  # cheap reject before paying for json.loads
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        rl = _find_rate_limits(obj)
        if not rl:
            continue
        captured_at = _captured_at(obj, now)
        if captured_at is None:
            continue
        windows = [w for w in (_window(e, captured_at, now) for e in rl.values()) if w]
        if windows:
            return captured_at, windows
    return None


def collect():
    """(windows, captured_at) on success, "login_required" when Codex has no
    login, or None when there's no usable snapshot (transient).

    windows: [{label, used_pct, rolled_over}] in the order Codex reports them.
    captured_at is epoch seconds — the caller ages it, so a wedged collector
    can't freeze a reading at "just now".
    """
    now = time.time()
    best = None
    for path in _newest_rollouts():
        # The newest *file* isn't necessarily the newest *snapshot*: a session
        # can be touched (a cancelled turn, a user message) long after its
        # last API call. Compare captures, not mtimes.
        snap = _snapshot_from(path, now)
        if snap and (best is None or snap[0] > best[0]):
            best = snap
    if best:
        # We're reading real usage, so "log in" is definitionally wrong here —
        # never let the auth check below override a working reading.
        captured_at, windows = best
        return windows, captured_at

    home = _codex_home()
    try:
        if not home.is_dir():
            return None  # Codex isn't installed here — nothing to say
        if (home / "auth.json").exists():
            return None  # logged in, just no snapshot yet (no turns run)
        if os.environ.get("OPENAI_API_KEY"):
            return None  # authenticated without auth.json
    except OSError:
        return None  # unreadable home: unavailable, not an accusation
    # Codex is set up but has no login of any kind — the one case where
    # telling the user to log in is correct.
    return "login_required"

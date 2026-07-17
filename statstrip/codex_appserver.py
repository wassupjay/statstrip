"""Live Codex usage via the CLI's own app-server — primary source, no tokens.

`codex app-server` speaks JSON-RPC over stdio and answers
`account/rateLimits/read` with the account's current rate limits: the same
call its TUI makes to refresh usage. It runs no model, so it costs nothing —
verified by reading three times in a row and watching usedPercent hold still.

This exists because the rollout-log reader (codex_local) can only see what
the last local Codex turn happened to record. Measured on this machine, the
log said 4% while the account was really at 10%: usage moves when you use
Codex anywhere — another terminal, another device — and the log never learns
about it. Polling this every minute is free and always current, so it's the
primary source and the log is the fallback for when it isn't available.

The app-server is marked experimental in the CLI, so treat every failure as
routine: a missing binary, an old version without the method, a timeout, a
shape we don't recognise all return None and let the caller fall back to the
log rather than showing a wrong number. Repeated failures put the live source
on a cooldown, so a wedged app-server costs one slow poll every so often
rather than one every minute.
"""
import json
import os
import shutil
import subprocess
import threading
import time

from . import codex_local

_INIT = {
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {"clientInfo": {"name": "statstrip", "version": "0.1.0"}},
}
_READ_ID = 2
_READ = {"jsonrpc": "2.0", "id": _READ_ID, "method": "account/rateLimits/read"}

TIMEOUT = 20  # generous: observed ~0.5s, but a cold start can page in the binary
_EXIT_GRACE = 5  # seconds to exit after stdin closes, before we kill the tree

# Back off when the live source keeps failing. Each poll costs a process spawn
# and, if the app-server is wedged on the network, up to TIMEOUT seconds — no
# point paying that every minute when the log fallback is answering anyway.
_COOLDOWN_BASE = 60
_COOLDOWN_MAX = 1800

# Windows: don't flash a console window on every poll (statstrip runs windowless
# under pythonw). Same reason claude_local passes it to ccusage.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_fail_count = 0
_next_attempt = 0.0
_state_lock = threading.Lock()


def _codex_exe():
    # npm installs codex as a .cmd shim on Windows, which subprocess cannot
    # launch by bare name — resolve the real path first. (Exactly the bug that
    # made ccusage silently produce nothing.)
    return shutil.which("codex")


def _kill_tree(proc):
    """Kill the child *and its descendants*.

    On Windows `codex` is a .cmd shim, so the tree is cmd.exe -> node.exe ->
    codex.exe and proc.kill() only reaps the shim: the app-server itself would
    survive every failed poll, forever, invisibly.
    """
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                           capture_output=True, timeout=10,
                           creationflags=_NO_WINDOW)
            return
        except Exception:
            pass  # fall through to the single-process kill
    try:
        proc.kill()
    except Exception:
        pass


def _is_reply(msg):
    """Our answer, not a server-originated request that happens to share an id.

    JSON-RPC ids are per-direction: the app-server numbers its own requests to
    us from its own counter, so `id == 2` alone doesn't mean it's ours.
    """
    return (isinstance(msg, dict) and msg.get("id") == _READ_ID
            and ("result" in msg or "error" in msg))


def _rpc_read(exe):
    """Send initialize + account/rateLimits/read, return the reply message.

    stdin is deliberately held open until the answer arrives: the app-server
    exits as soon as stdin closes, and closing it early makes it quit before
    replying.
    """
    proc = subprocess.Popen(
        [exe, "app-server"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, encoding="utf-8", bufsize=1, creationflags=_NO_WINDOW,
        cwd=os.path.expanduser("~"),  # don't hold a lock on wherever we started
    )
    found = {}
    # Started before the writes so notifications can't fill the stdout pipe
    # and deadlock us while we're still writing.
    reader = threading.Thread(target=_drain, args=(proc, found), daemon=True)
    reader.start()
    try:
        try:
            proc.stdin.write(json.dumps(_INIT) + "\n")
            proc.stdin.write(json.dumps(_READ) + "\n")
            proc.stdin.flush()
            reader.join(TIMEOUT)
        except Exception:
            return None
        return found.get("msg")
    finally:
        _shutdown(proc, reader)


def _drain(proc, found):
    try:
        for line in proc.stdout:
            try:
                msg = json.loads(line)
            except Exception:
                continue  # log noise on stdout is not our problem
            if _is_reply(msg):
                found["msg"] = msg
                return
    except Exception:
        pass


def _shutdown(proc, reader):
    """Retire the child and unblock the reader. Runs on every path.

    Order matters: closing stdin is the documented way the app-server exits,
    and it's also what lets the reader see EOF. Skipping it leaks a blocked
    thread per poll, which keeps the Popen (and its pipes) alive forever.
    """
    try:
        if proc.stdin and not proc.stdin.closed:
            proc.stdin.close()
    except Exception:
        pass
    try:
        proc.wait(timeout=_EXIT_GRACE)
    except Exception:
        _kill_tree(proc)
        try:
            proc.wait(timeout=_EXIT_GRACE)
        except Exception:
            pass
    # The reader unblocks once the last writer of the stdout pipe is gone.
    reader.join(timeout=_EXIT_GRACE)
    try:
        if proc.stdout and not proc.stdout.closed:
            proc.stdout.close()
    except Exception:
        pass


def _snapshot_from(msg):
    """The rate-limit snapshot dict out of a JSON-RPC reply, or None."""
    if not isinstance(msg, dict) or "error" in msg:
        return None  # e.g. not signed in, or method unknown on an old build
    result = msg.get("result")
    if not isinstance(result, dict):
        return None
    snap = result.get("rateLimits")
    if isinstance(snap, dict) and snap:
        return snap
    # Newer multi-bucket view. Only the "codex" bucket is the one the CLI
    # meters against — any other key is a different limit entirely, and
    # rendering it as Codex usage would be a confident wrong number.
    by_id = result.get("rateLimitsByLimitId")
    if isinstance(by_id, dict):
        snap = by_id.get("codex")
        if isinstance(snap, dict) and snap:
            return snap
    return None


def _windows(snap, now):
    """Windows in the order the protocol defines them (primary, then
    secondary) — not dict order, since the snapshot also carries credits and
    plan metadata that are not windows."""
    out = []
    for key in ("primary", "secondary"):
        entry = snap.get(key)
        if not isinstance(entry, dict):
            continue
        w = codex_local.shape_window(
            entry.get("usedPercent"),        # camelCase here; the rollout log
            entry.get("windowDurationMins"),  # uses snake_case for the same facts
            entry.get("resetsAt"),
            now, now,  # live reading: captured now
        )
        if w:
            # "Rolled over" means "this saved number predates a reset". A
            # reading fetched just now can't: the server already applied the
            # reset, so this *is* the post-reset figure. Without this, a poll
            # landing just after a reset would throw away a correct number and
            # render "reset".
            w["rolled_over"] = False
            out.append(w)
    return out


def collect():
    """(windows, captured_at) on success, or None to fall back to the log.

    Never raises and never reports "login_required": distinguishing a real
    logout from an experimental endpoint misbehaving isn't something this can
    do reliably, and codex_local already classifies login state from disk.
    """
    global _fail_count, _next_attempt
    with _state_lock:
        if time.time() < _next_attempt:
            return None  # cooling off; the log fallback is carrying us

    result = None
    exe = _codex_exe()
    if exe:
        try:
            result = _parse(_rpc_read(exe))
        except Exception:
            result = None

    with _state_lock:
        if result is None:
            _fail_count += 1
            _next_attempt = time.time() + min(
                _COOLDOWN_BASE * 2 ** (_fail_count - 1), _COOLDOWN_MAX)
        else:
            _fail_count = 0
            _next_attempt = 0.0
    return result


def _parse(msg):
    snap = _snapshot_from(msg)
    if not snap:
        return None
    now = time.time()
    windows = _windows(snap, now)
    if not windows:
        return None
    return windows, now

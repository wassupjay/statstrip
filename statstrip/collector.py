"""Data-extraction layer only. No UI. Everything is read from this PC.

Polls CPU/RAM/DISK/GPU via psutil/pynvml, Claude usage via Claude Code's own
session, and Codex usage via Codex CLI's session logs, then writes the merged
snapshot to a stats file AND serves it
over a tiny local HTTP endpoint so any other script/app/website can consume
it independently of display.py.

    python -m statstrip.collector

Consume from elsewhere:
    GET http://127.0.0.1:5757/stats   -> JSON
    or read the stats file (see config.STATS_FILE)
"""
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import psutil

from . import config

try:
    import pynvml
    pynvml.nvmlInit()
    _GPU_HANDLES = [pynvml.nvmlDeviceGetHandleByIndex(i)
                    for i in range(pynvml.nvmlDeviceGetCount())]
except Exception:
    _GPU_HANDLES = []

_lock = threading.Lock()
_state = {
    "cpu_pct": None, "ram_pct": None, "disk_pct": None,
    "gpus": [],  # [{index, util_pct, mem_used_mb, mem_total_mb}]
    "claude_5h_pct": None, "claude_active": False,
    "claude_week_pct": None, "claude_status": None,
    "codex_windows": [],  # [{label, used_pct, rolled_over}], as Codex names them
    "codex_captured_at": None,  # epoch when Codex recorded them; consumers age
                                # it themselves so a stuck collector can't
                                # freeze a reading at "just now"
    "codex_status": None,
    "updated_at": None,
}


def collect_local():
    cpu = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory().percent
    disk = psutil.disk_usage(config.DISK_PATH).percent
    gpus = []
    for i, h in enumerate(_GPU_HANDLES):
        try:
            util = pynvml.nvmlDeviceGetUtilizationRates(h).gpu
            mem = pynvml.nvmlDeviceGetMemoryInfo(h)
            gpus.append({
                "index": i,
                "util_pct": util,
                "mem_used_mb": mem.used // 2**20,
                "mem_total_mb": mem.total // 2**20,
            })
        except Exception:
            continue
    return cpu, ram, disk, gpus


def collect_claude():
    """Returns (active, five_h, week, status).

    status: "ok" (real plan-limit %), "estimate" (ccusage heuristic),
    "login_required" (no usable Claude Code login), "unavailable" (transient
    API failure — rate limited, network, endpoint hiccup), or None (disabled).
    """
    if not config.CLAUDE_ENABLED:
        return False, None, None, None
    from . import claude_local, claude_oauth
    if config.CLAUDE_MODE == "estimate":
        active, five_h, week = claude_local.collect()
        return active, five_h, week, "estimate"
    result = claude_oauth.collect()  # real plan-limit % via Claude Code's session
    if result == "login_required":
        return False, None, None, "login_required"
    if result is None:
        return False, None, None, "unavailable"
    return (*result, "ok")


def collect_codex():
    """Returns (windows, captured_at, status).

    status: "ok" (real percentages from Codex's session log), "login_required"
    (Codex is set up but not logged in), "unavailable" (no usable snapshot —
    no turns run yet, or a format we don't recognise), or None (disabled).
    """
    if not config.CODEX_ENABLED:
        return [], None, None
    from . import codex_local
    result = codex_local.collect()
    if result == "login_required":
        return [], None, "login_required"
    if result is None:
        return [], None, "unavailable"
    windows, captured_at = result
    return windows, captured_at, "ok"


_write_lock = threading.Lock()  # local_loop, claude_loop and codex_loop all write
_last_written = None
_last_write_time = 0.0
WRITE_HEARTBEAT = 30  # rewrite at least this often so the file's updated_at
                      # keeps advancing on idle machines and file consumers
                      # can still tell a live collector from a dead one


def write_snapshot():
    global _last_written, _last_write_time
    with _lock:
        snapshot = dict(_state)
    payload = json.dumps(snapshot)
    # Skip write when nothing changed (ignore the timestamp-only churn)
    comparable = {k: v for k, v in snapshot.items() if k != "updated_at"}
    with _write_lock:
        if comparable == _last_written and time.time() - _last_write_time < WRITE_HEARTBEAT:
            return
        try:
            tmp = config.STATS_FILE + ".tmp"
            with open(tmp, "w") as f:
                f.write(payload)
            os.replace(tmp, config.STATS_FILE)  # atomic — readers never see partial JSON
            _last_written = comparable
            _last_write_time = time.time()
        except Exception:
            pass


def local_loop():
    while True:
        try:
            cpu, ram, disk, gpus = collect_local()
            with _lock:
                _state["cpu_pct"] = cpu
                _state["ram_pct"] = ram
                _state["disk_pct"] = disk
                _state["gpus"] = gpus
                _state["updated_at"] = time.time()
            write_snapshot()
        except Exception as e:
            # Never let a transient error (bad disk path, psutil hiccup)
            # kill the loop — stale data is flagged via updated_at.
            print(f"local_loop error: {e}")
        time.sleep(config.LOCAL_REFRESH)


def claude_loop():
    if not config.CLAUDE_ENABLED:
        return
    while True:
        try:
            active, five_h, week, status = collect_claude()
            with _lock:
                _state["claude_active"] = active
                _state["claude_5h_pct"] = five_h
                _state["claude_week_pct"] = week
                _state["claude_status"] = status
            write_snapshot()
        except Exception as e:
            # Same rule as local_loop: a ccusage hiccup or schema change
            # must never kill the thread — dead threads keep showing the
            # last percentages as if they were live.
            print(f"claude_loop error: {e}")
        time.sleep(config.CLAUDE_REFRESH)


def codex_loop():
    if not config.CODEX_ENABLED:
        return
    while True:
        try:
            windows, captured_at, status = collect_codex()
            with _lock:
                _state["codex_windows"] = windows
                _state["codex_captured_at"] = captured_at
                _state["codex_status"] = status
            write_snapshot()
        except Exception as e:
            # Same rule as the other loops: a rollout-format change must never
            # kill the thread and leave the last percentages frozen on screen.
            # Clear the reading too — a poll that keeps failing must stop
            # showing its last success as if it were current.
            with _lock:
                _state["codex_windows"] = []
                _state["codex_captured_at"] = None
                _state["codex_status"] = "unavailable"
            write_snapshot()
            print(f"codex_loop error: {e}")
        time.sleep(config.CODEX_REFRESH)


class StatsHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path != "/stats":
            self.send_error(404); return
        with _lock:
            body = json.dumps(_state).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        if config.CORS_ORIGIN:
            self.send_header("Access-Control-Allow-Origin", config.CORS_ORIGIN)
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)


def main():
    try:
        server = ThreadingHTTPServer(("127.0.0.1", config.SERVE_PORT), StatsHandler)
    except OSError as e:
        raise SystemExit(
            f"Cannot bind 127.0.0.1:{config.SERVE_PORT} ({e}). "
            f"Another collector already running? Set STATSTRIP_PORT to use a different port."
        )
    threading.Thread(target=local_loop, daemon=True).start()
    threading.Thread(target=claude_loop, daemon=True).start()
    threading.Thread(target=codex_loop, daemon=True).start()
    print(f"collector running: http://127.0.0.1:{config.SERVE_PORT}/stats "
          f"(also writing {config.STATS_FILE})")
    server.serve_forever()


if __name__ == "__main__":
    main()

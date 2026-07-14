"""Data-extraction layer only. No UI.

Polls CPU/RAM/DISK/GPU locally, and optionally a Claude usage dashboard's
JSON API, then writes the merged snapshot to a stats file AND serves it over
a tiny local HTTP endpoint so any other script/app/website can consume it
independently of display.py.

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
import requests

from . import config

try:
    import pynvml
    pynvml.nvmlInit()
    _GPU_HANDLES = [pynvml.nvmlDeviceGetHandleByIndex(i)
                    for i in range(pynvml.nvmlDeviceGetCount())]
except Exception:
    _GPU_HANDLES = []

_session = requests.Session()

_lock = threading.Lock()
_state = {
    "cpu_pct": None, "ram_pct": None, "disk_pct": None,
    "gpus": [],  # [{index, util_pct, mem_used_mb, mem_total_mb}]
    "claude_5h_pct": None, "claude_active": False,
    "claude_week_pct": None,
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
    if config.CLAUDE_SOURCE == "api" and config.CLAUDE_API_URL:
        try:
            r = _session.get(config.CLAUDE_API_URL, timeout=10)
            d = r.json()
            active = bool(d.get("active"))
            five_h = d.get("tokens_pct") if active else None
            week = (d.get("weekly") or {}).get("pct")
            return active, five_h, week
        except Exception:
            return False, None, None
    if config.CLAUDE_SOURCE == "local":
        from . import claude_local
        return claude_local.collect()
    return False, None, None


_last_written = None


def write_snapshot():
    global _last_written
    with _lock:
        snapshot = dict(_state)
    payload = json.dumps(snapshot)
    # Skip write when nothing changed (ignore the timestamp-only churn)
    comparable = {k: v for k, v in snapshot.items() if k != "updated_at"}
    if comparable == _last_written:
        return
    try:
        tmp = config.STATS_FILE + ".tmp"
        with open(tmp, "w") as f:
            f.write(payload)
        os.replace(tmp, config.STATS_FILE)  # atomic — readers never see partial JSON
        _last_written = comparable
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
    if config.CLAUDE_SOURCE == "off":
        return
    while True:
        active, five_h, week = collect_claude()
        with _lock:
            _state["claude_active"] = active
            _state["claude_5h_pct"] = five_h
            _state["claude_week_pct"] = week
        write_snapshot()
        time.sleep(config.CLAUDE_REFRESH)


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
        self.send_header("Access-Control-Allow-Origin", "*")
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
    print(f"collector running: http://127.0.0.1:{config.SERVE_PORT}/stats "
          f"(also writing {config.STATS_FILE})")
    server.serve_forever()


if __name__ == "__main__":
    main()

"""Display layer only. No data collection here.

Reads snapshots from collector's local endpoint and renders an always-on-top
bar docked just above the Windows taskbar. Requires collector.py running.

    python -m statstrip.display
"""
import threading
import time
import tkinter as tk

import requests

from . import config

STATS_URL = f"http://127.0.0.1:{config.SERVE_PORT}/stats"
POLL_INTERVAL = 1  # seconds

_lock = threading.Lock()
_snapshot = {}
_session = requests.Session()


def poll():
    while True:
        try:
            r = _session.get(STATS_URL, timeout=3)
            with _lock:
                _snapshot.update(r.json())
                _snapshot.pop("_error", None)
        except Exception:
            with _lock:
                _snapshot["_error"] = "collector unreachable"
        time.sleep(POLL_INTERVAL)


STALE_AFTER = 15  # seconds without a fresh collector snapshot


def build_text():
    with _lock:
        s = dict(_snapshot)
    if not s or s.get("_error"):
        return "waiting for collector…"
    updated = s.get("updated_at")
    if not updated or time.time() - updated > STALE_AFTER:
        # Collector's HTTP server is up but its polling thread stopped —
        # don't keep displaying frozen numbers as if they were live.
        return "collector stalled — data stale"

    def pct(v):
        return f"{v:.0f}%" if isinstance(v, (int, float)) else "?"

    gpu_txt = "  ".join(
        f"GPU{g['index']} {g['util_pct']}% {g['mem_used_mb']}/{g['mem_total_mb']}MB"
        for g in s.get("gpus", [])
    ) or "GPU n/a"

    parts = [
        f"CPU {pct(s.get('cpu_pct'))}",
        f"RAM {pct(s.get('ram_pct'))}",
        f"DISK {pct(s.get('disk_pct'))}",
        gpu_txt,
    ]
    if config.CLAUDE_API_URL:
        claude_5h = pct(s.get("claude_5h_pct")) if s.get("claude_active") else "idle"
        parts.append(f"CLAUDE 5h {claude_5h}")
        parts.append(f"WEEK {pct(s.get('claude_week_pct'))}")

    return "   ".join(parts)


def main():
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    sw = root.winfo_screenwidth()
    bar_h = 26
    root.geometry(f"{sw}x{bar_h}+0+{root.winfo_screenheight() - bar_h - 40}")
    root.configure(bg="#0a0f1a")

    label = tk.Label(root, text="loading…", fg="#22d3ee", bg="#0a0f1a",
                      font=("Consolas", 10), anchor="w")
    label.pack(fill="both", expand=True, padx=8)

    def refresh():
        label.config(text=build_text())
        root.after(1000, refresh)

    threading.Thread(target=poll, daemon=True).start()
    refresh()
    root.mainloop()


if __name__ == "__main__":
    main()

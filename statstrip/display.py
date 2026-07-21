"""Display layer only. No data collection here.

Reads snapshots from collector's local endpoint and renders the stats either
embedded inside the Windows taskbar (default, TrafficMonitor-style) or as an
always-on-top bar docked just above it. Requires collector.py running.

    python -m statstrip.display
"""
import ctypes
import threading
import time
import tkinter as tk
from ctypes import wintypes

import requests

from . import config

STATS_URL = f"http://127.0.0.1:{config.SERVE_PORT}/stats"
POLL_INTERVAL = 1  # seconds

BG = config.BG
FG = config.FG
FONT_FAMILY = config.FONT_FAMILY

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

    gpu_txt = "  ".join(
        f"GPU{g.get('index', '?')} {g.get('util_pct', '?')}%"
        for g in s.get("gpus", []) if isinstance(g, dict)
    ) or "GPU n/a"

    parts = [
        f"CPU {pct(s.get('cpu_pct'))}",
        f"RAM {pct(s.get('ram_pct'))}",
        f"DISK {pct(s.get('disk_pct'))}",
        gpu_txt,
    ]
    if config.CLAUDE_ENABLED:
        parts.extend(claude_parts(s))

    if config.CODEX_ENABLED:
        parts.extend(codex_parts(s))

    return "   ".join(parts)


def pct(v):
    return f"{v:.0f}%" if isinstance(v, (int, float)) and not isinstance(v, bool) else "?"


def claude_parts(s):
    """Render the Claude gauges from a snapshot.

    A reading is held through transient failures rather than blanked — the
    endpoint rate-limits routinely, and one 429 is no reason to throw away a
    number that was right a minute ago. The age is shown once it's old
    enough to matter, so a held reading can't quietly pose as current.
    """
    status = s.get("claude_status")
    if status == "login_required":
        return ["CLAUDE login required"]
    if status not in ("ok", "estimate"):
        # Never claim login is needed for a problem that isn't about login.
        return ["CLAUDE usage unavailable"]

    # "~" marks estimate mode: relative to your own history, not a real plan
    # limit.
    mark = "~" if status == "estimate" else ""
    five_h = pct(s.get("claude_5h_pct")) if s.get("claude_active") else "idle"
    out = [f"CLAUDE 5h {mark}{five_h}", f"WEEK {mark}{pct(s.get('claude_week_pct'))}"]

    captured_at = s.get("claude_captured_at")
    if isinstance(captured_at, (int, float)):
        age = max(0.0, time.time() - captured_at)
        if age > config.CLAUDE_STALE_AFTER:
            out.append(f"({age_text(age)} ago)")
    return out


def codex_parts(s):
    """Render the Codex gauges from a snapshot. Window names come from Codex
    itself, so a plan with different windows still reads correctly."""
    status = s.get("codex_status")
    if status == "login_required":
        return ["CODEX login required"]
    if status != "ok":
        # "unavailable" (no snapshot yet) or an unknown status — never guess.
        return ["CODEX usage unavailable"]

    windows = s.get("codex_windows")
    if not isinstance(windows, list) or not windows:
        return ["CODEX usage unavailable"]

    # Age is derived here from the capture instant rather than read as a
    # precomputed number, so a collector that stops updating shows a reading
    # growing visibly older instead of one frozen at "just now".
    captured_at = s.get("codex_captured_at")
    if not isinstance(captured_at, (int, float)):
        return ["CODEX usage unavailable"]
    age = max(0.0, time.time() - captured_at)

    out = []
    for i, w in enumerate(windows):
        if not isinstance(w, dict):
            continue
        label = w.get("label") or f"w{i + 1}"
        used = w.get("used_pct")
        if w.get("rolled_over"):
            # The window reset since this snapshot: the old number is known
            # to be wrong and the new one is unknown until Codex next runs.
            value = "reset"
        elif isinstance(used, (int, float)) and not isinstance(used, bool):
            value = f"{used:.0f}%"
        else:
            value = "?"
        # Prefix the first line we actually emit — keying this to the source
        # index would drop the label entirely if entry 0 were skipped, and
        # the gauge would read as another Claude window.
        out.append(f"{'CODEX ' if not out else ''}{label} {value}")
    if not out:
        return ["CODEX usage unavailable"]
    if age > config.CODEX_STALE_AFTER:
        out.append(f"({age_text(age)} ago)")
    return out


def age_text(seconds):
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes / 60
    if hours < 24:
        return f"{hours:.0f}h"
    return f"{hours / 24:.0f}d"


# ---------------------------------------------------------------------------
# Taskbar embedding (Windows only). Same trick TrafficMonitor uses: re-parent
# our window into Shell_TrayWnd and keep it positioned just left of the
# system tray, so it lives inside the taskbar instead of taking screen space.
# ---------------------------------------------------------------------------

user32 = ctypes.windll.user32

GWL_STYLE = -16
WS_POPUP = 0x80000000
WS_CHILD = 0x40000000
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020

# GetWindowLongPtr/SetWindowLongPtr only exist as such on 64-bit; declare
# types so styles aren't truncated.
_get_style = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
_get_style.restype = ctypes.c_ssize_t
_get_style.argtypes = [wintypes.HWND, ctypes.c_int]
_set_style = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
_set_style.restype = ctypes.c_ssize_t
_set_style.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]


def _rect(hwnd):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r


class TaskbarHost:
    """Embeds the tk root window inside the taskbar, left of the tray icons."""

    MARGIN = 6  # px gap between us and the tray

    def __init__(self, root):
        root.update_idletasks()
        # winfo_id() is the client widget; its parent is the real toplevel.
        self.hwnd = user32.GetParent(root.winfo_id())
        self.taskbar = user32.FindWindowW("Shell_TrayWnd", None)
        if not self.taskbar:
            raise OSError("taskbar window not found")
        self.tray = user32.FindWindowExW(self.taskbar, None, "TrayNotifyWnd", None)
        self._last = None

        old = _get_style(self.hwnd, GWL_STYLE)
        _set_style(self.hwnd, GWL_STYLE, (old & ~WS_POPUP) | WS_CHILD)
        if not user32.SetParent(self.hwnd, self.taskbar):
            _set_style(self.hwnd, GWL_STYLE, old)
            raise OSError("SetParent into taskbar failed")
        user32.SetWindowPos(self.hwnd, 0, 0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED)

    def alive(self):
        return bool(user32.IsWindow(self.taskbar))

    def place(self, width):
        tbr = _rect(self.taskbar)
        height = tbr.bottom - tbr.top
        if config.TASKBAR_ALIGN == "left":
            x = self.MARGIN
        else:
            # Right-align against the tray icons (or the taskbar edge if no
            # tray), in taskbar client coordinates.
            edge = _rect(self.tray).left if self.tray else tbr.right
            x = max(0, edge - tbr.left - width - self.MARGIN)
        if (x, width, height) != self._last:
            user32.MoveWindow(self.hwnd, x, 0, width, height, True)
            self._last = (x, width, height)


def _set_dpi_awareness():
    # Without this, GetWindowRect coordinates are DPI-virtualized and the bar
    # lands in the wrong spot on scaled displays.
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # per-monitor v2
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass


def run_bar():
    root = tk.Tk()
    root.overrideredirect(True)
    root.configure(bg=BG)

    font_size = 10
    try:
        font_size = max(8, round(10 * user32.GetDpiForSystem() / 96))
    except Exception:
        pass
    label = tk.Label(root, text="loading...", fg=FG, bg=BG,
                      font=(FONT_FAMILY, font_size), anchor="w")
    label.pack(fill="both", expand=True, padx=8)

    host = None
    if config.EMBED_TASKBAR:
        try:
            # Color-key the background away so only the text shows, floating
            # on whatever the taskbar renders underneath.
            root.attributes("-transparentcolor", BG)
            host = TaskbarHost(root)
        except Exception:
            root.attributes("-transparentcolor", "")
            host = None
    if host is None:
        root.attributes("-topmost", True)
        sw = root.winfo_screenwidth()
        bar_h = 26
        root.geometry(f"{sw}x{bar_h}+0+{root.winfo_screenheight() - bar_h - 40}")

    def refresh():
        rearm = True
        try:
            label.config(text=build_text())
            if host is not None:
                if not host.alive():
                    # Taskbar is gone (explorer.exe restarting) and took our
                    # child window with it — tear down and let main() rebuild.
                    rearm = False
                    root.destroy()
                    return
                root.update_idletasks()
                host.place(label.winfo_reqwidth() + 16)
        except tk.TclError:
            rearm = False  # window torn down under us; main() rebuilds
        except Exception:
            pass  # one bad snapshot must never stop the update chain
        finally:
            if rearm:
                root.after(1000, refresh)

    refresh()
    root.mainloop()


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_ERROR_ALREADY_EXISTS = 183
_mutex = None  # keep the handle alive for the process lifetime


def _already_running():
    # Second instances happen easily (install.bat re-run, double login
    # launch) and two bars overlay each other inside the taskbar.
    global _mutex
    _mutex = _kernel32.CreateMutexW(None, False, "Local\\StatStripDisplay")
    return ctypes.get_last_error() == _ERROR_ALREADY_EXISTS


def main():
    if _already_running():
        return
    _set_dpi_awareness()
    threading.Thread(target=poll, daemon=True).start()
    while True:
        try:
            run_bar()
        except tk.TclError:
            pass
        # The window only ever dies from outside (explorer restart); wait for
        # the new taskbar to come up, then rebuild into it.
        time.sleep(3)


if __name__ == "__main__":
    main()

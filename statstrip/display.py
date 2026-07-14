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

BG = "#0a0f1a"
FG = "#22d3ee"

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
        status = s.get("claude_status")
        if status == "login_required":
            parts.append("CLAUDE login required")
        elif status == "unavailable":
            # Transient (rate limited, network blip) — never claim login is
            # needed for a problem that isn't about login.
            parts.append("CLAUDE usage unavailable")
        else:
            # "~" marks estimate mode: relative to your own history, not a
            # real plan limit.
            mark = "~" if status == "estimate" else ""
            claude_5h = pct(s.get("claude_5h_pct")) if s.get("claude_active") else "idle"
            parts.append(f"CLAUDE 5h {mark}{claude_5h}")
            parts.append(f"WEEK {mark}{pct(s.get('claude_week_pct'))}")

    return "   ".join(parts)


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
    label = tk.Label(root, text="loading…", fg=FG, bg=BG,
                      font=("Consolas", font_size), anchor="w")
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

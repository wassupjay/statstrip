import os
import tempfile

# Claude gauges. "on" (default): real plan-limit percentages via Claude
# Code's own usage API — shows "login required" when no usable local login
# exists. "estimate": ccusage heuristic over local logs (relative to your own
# history, rendered with a ~ prefix). "off": hide the gauges.
CLAUDE_MODE = os.environ.get("STATSTRIP_CLAUDE", "on").lower()
CLAUDE_ENABLED = CLAUDE_MODE != "off"

# Codex gauges. "on" (default): usage percentages read from Codex CLI's own
# session logs — shows "login required" when Codex isn't logged in. "off":
# hide the gauges. There's no estimate mode: unlike Claude, Codex records the
# real percentages locally, so there's nothing to approximate.
CODEX_MODE = os.environ.get("STATSTRIP_CODEX", "on").lower()
CODEX_ENABLED = CODEX_MODE != "off"

# Codex only records usage when it actually runs, so a reading is a point in
# time, not a live feed. Past this age it's shown with its age attached
# rather than left to pose as current.
CODEX_STALE_AFTER = float(os.environ.get("STATSTRIP_CODEX_STALE_AFTER", "900"))

# "1" (default): embed the display inside the Windows taskbar, left of the
# tray icons. "0": float as a separate bar just above the taskbar instead.
EMBED_TASKBAR = os.environ.get("STATSTRIP_TASKBAR", "1") != "0"

# Where to sit inside the taskbar: "right" (default) hugs the tray icons;
# "left" hugs the taskbar's left edge — use it when the readout is wide
# enough to collide with Windows 11's centered app icons.
TASKBAR_ALIGN = os.environ.get("STATSTRIP_ALIGN", "right").lower()

LOCAL_REFRESH = float(os.environ.get("STATSTRIP_LOCAL_REFRESH", "2"))
CLAUDE_REFRESH = float(os.environ.get("STATSTRIP_CLAUDE_REFRESH", "60"))
CODEX_REFRESH = float(os.environ.get("STATSTRIP_CODEX_REFRESH", "60"))
DISK_PATH = os.environ.get("STATSTRIP_DISK_PATH", "C:\\")
SERVE_PORT = int(os.environ.get("STATSTRIP_PORT", "5757"))

# Access-Control-Allow-Origin value for /stats. Empty (default) sends no CORS
# header, so web pages in your browser can't read the feed. Set to "*" or a
# specific origin only if a browser-based dashboard needs it — it exposes
# live machine stats to any site you visit.
CORS_ORIGIN = os.environ.get("STATSTRIP_CORS", "")
STATS_FILE = os.environ.get(
    "STATSTRIP_STATS_FILE", os.path.join(tempfile.gettempdir(), "statstrip-stats.json")
)

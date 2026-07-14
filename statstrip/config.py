import os
import tempfile

# Claude gauges read local Claude Code logs via the ccusage CLI
# (npm install -g ccusage). Set STATSTRIP_CLAUDE=off to hide them;
# they also disable themselves silently when ccusage isn't installed.
CLAUDE_ENABLED = os.environ.get("STATSTRIP_CLAUDE", "on").lower() != "off"

# "1" (default): embed the display inside the Windows taskbar, left of the
# tray icons. "0": float as a separate bar just above the taskbar instead.
EMBED_TASKBAR = os.environ.get("STATSTRIP_TASKBAR", "1") != "0"

# Where to sit inside the taskbar: "right" (default) hugs the tray icons;
# "left" hugs the taskbar's left edge — use it when the readout is wide
# enough to collide with Windows 11's centered app icons.
TASKBAR_ALIGN = os.environ.get("STATSTRIP_ALIGN", "right").lower()

LOCAL_REFRESH = float(os.environ.get("STATSTRIP_LOCAL_REFRESH", "2"))
CLAUDE_REFRESH = float(os.environ.get("STATSTRIP_CLAUDE_REFRESH", "60"))
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

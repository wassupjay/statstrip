import os
import tempfile

# Claude gauges read local Claude Code logs via the ccusage CLI
# (npm install -g ccusage). Set STATSTRIP_CLAUDE=off to hide them;
# they also disable themselves silently when ccusage isn't installed.
CLAUDE_ENABLED = os.environ.get("STATSTRIP_CLAUDE", "on").lower() != "off"

LOCAL_REFRESH = float(os.environ.get("STATSTRIP_LOCAL_REFRESH", "2"))
CLAUDE_REFRESH = float(os.environ.get("STATSTRIP_CLAUDE_REFRESH", "60"))
DISK_PATH = os.environ.get("STATSTRIP_DISK_PATH", "C:\\")
SERVE_PORT = int(os.environ.get("STATSTRIP_PORT", "5757"))
STATS_FILE = os.environ.get(
    "STATSTRIP_STATS_FILE", os.path.join(tempfile.gettempdir(), "statstrip-stats.json")
)

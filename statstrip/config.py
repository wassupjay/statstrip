import os
import tempfile

# Optional: point at a Claude usage dashboard exposing the same JSON shape as
# https://github.com/<you>/claude-usage-dashboard 's /api endpoint
# ({"active": bool, "tokens_pct": float, "weekly": {"pct": float}}).
# Leave unset to disable the Claude gauges entirely.
CLAUDE_API_URL = os.environ.get("STATSTRIP_CLAUDE_API_URL", "")

LOCAL_REFRESH = float(os.environ.get("STATSTRIP_LOCAL_REFRESH", "2"))
CLAUDE_REFRESH = float(os.environ.get("STATSTRIP_CLAUDE_REFRESH", "60"))
DISK_PATH = os.environ.get("STATSTRIP_DISK_PATH", "C:\\")
SERVE_PORT = int(os.environ.get("STATSTRIP_PORT", "5757"))
STATS_FILE = os.environ.get(
    "STATSTRIP_STATS_FILE", os.path.join(tempfile.gettempdir(), "statstrip-stats.json")
)

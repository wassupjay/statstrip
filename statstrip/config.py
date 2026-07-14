import os
import tempfile

# Claude usage source, one of:
#   "local"  — run the ccusage CLI against local Claude Code logs (default;
#              silently disabled if ccusage isn't installed)
#   "api"    — poll a remote dashboard endpoint returning
#              {"active": bool, "tokens_pct": float, "weekly": {"pct": float}}
#              (requires STATSTRIP_CLAUDE_API_URL)
#   "off"    — no Claude gauges
CLAUDE_SOURCE = os.environ.get("STATSTRIP_CLAUDE_SOURCE", "local").lower()
CLAUDE_API_URL = os.environ.get("STATSTRIP_CLAUDE_API_URL", "")
if CLAUDE_API_URL and CLAUDE_SOURCE == "local":
    CLAUDE_SOURCE = "api"  # URL present implies api mode

LOCAL_REFRESH = float(os.environ.get("STATSTRIP_LOCAL_REFRESH", "2"))
CLAUDE_REFRESH = float(os.environ.get("STATSTRIP_CLAUDE_REFRESH", "60"))
DISK_PATH = os.environ.get("STATSTRIP_DISK_PATH", "C:\\")
SERVE_PORT = int(os.environ.get("STATSTRIP_PORT", "5757"))
STATS_FILE = os.environ.get(
    "STATSTRIP_STATS_FILE", os.path.join(tempfile.gettempdir(), "statstrip-stats.json")
)

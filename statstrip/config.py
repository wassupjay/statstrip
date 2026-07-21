import os
import tempfile

# ──────────────────────────────────────────────────────────────────────
# Theme / display presets
# ──────────────────────────────────────────────────────────────────────
# Each preset is (BG, FG, FONT_FAMILY). BG doubles as the transparent-color
# key for taskbar embedding (root.attributes("-transparentcolor", BG)), so a
# theme whose BG equals a color used in the text would make that text
# invisible. All presets here avoid that.
_THEMES = {
    # name: (bg, fg, font)
    "cyan":             ("#0a0f1a", "#22d3ee", "Consolas"),   # current default
    "mono":             ("#1a1a1a", "#e0e0e0", "Consolas"),
    "amber":            ("#1a0f00", "#ffb800", "Consolas"),
    "green":            ("#001a00", "#00ff88", "Consolas"),
    "high-contrast":    ("#000000", "#ffffff", "Consolas"),
}

_THEME_NAMES = tuple(_THEMES.keys())

# Resolve theme from env var (STATSTRIP_THEME), then allow individual
# STATSTRIP_BG / STATSTRIP_FG / STATSTRIP_FONT env vars to override any
# of the theme's values, falling back to "cyan" default.
_theme_name = os.environ.get("STATSTRIP_THEME", "").lower()
if _theme_name in _THEMES:
    _bg, _fg, _font = _THEMES[_theme_name]
else:
    _bg, _fg, _font = _THEMES["cyan"]

# Individual env vars can override theme values
BG = os.environ.get("STATSTRIP_BG", _bg)
FG = os.environ.get("STATSTRIP_FG", _fg)
FONT_FAMILY = os.environ.get("STATSTRIP_FONT", _font)


# Claude gauges. "on" (default): real plan-limit percentages via Claude
# Code's own usage API — shows "login required" when no usable local login
# exists. "estimate": ccusage heuristic over local logs (relative to your own
# history, rendered with a ~ prefix). "off": hide the gauges.
CLAUDE_MODE = os.environ.get("STATSTRIP_CLAUDE", "on").lower()
CLAUDE_ENABLED = CLAUDE_MODE != "off"

# Claude's usage endpoint rate-limits, and its Retry-After is unhelpful
# (observed: "0"). Polling straight through a 429 is what keeps us in the
# penalty box, so each consecutive failure doubles the wait up to this cap.
CLAUDE_BACKOFF_MAX = float(os.environ.get("STATSTRIP_CLAUDE_BACKOFF_MAX", "1800"))

# Past this age a held-over Claude reading is shown with its age attached.
# Claude usage does move while you work, so an old number must never pose as
# current — but it's still better than blanking the gauges over one 429.
CLAUDE_STALE_AFTER = float(os.environ.get("STATSTRIP_CLAUDE_STALE_AFTER", "600"))

# Codex gauges. "on" (default): live percentages from `codex app-server`
# (account/rateLimits/read — the same call its TUI makes; runs no model, so it
# costs no tokens), falling back to Codex's session logs when the app-server
# isn't usable. "log": only read the session logs — passive, but only as fresh
# as your last local Codex turn. "off": hide the gauges.
CODEX_MODE = os.environ.get("STATSTRIP_CODEX", "on").lower()
CODEX_ENABLED = CODEX_MODE != "off"
CODEX_LIVE = CODEX_MODE not in ("off", "log")

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
DISK_PATH = os.environ.get("STATSTRIP_DISK_PATH", "C:\\\\")
SERVE_PORT = int(os.environ.get("STATSTRIP_PORT", "5757"))

# Access-Control-Allow-Origin value for /stats. Empty (default) sends no CORS
# header, so web pages in your browser can't read the feed. Set to "*" or a
# specific origin only if a browser-based dashboard needs it — it exposes
# live machine stats to any site you visit.
CORS_ORIGIN = os.environ.get("STATSTRIP_CORS", "")
STATS_FILE = os.environ.get(
    "STATSTRIP_STATS_FILE", os.path.join(tempfile.gettempdir(), "statstrip-stats.json")
)

# Exported for --help / documentation generation
THEME_PRESETS = _THEMES
THEME_NAMES = _THEME_NAMES
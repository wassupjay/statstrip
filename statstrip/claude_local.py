"""Built-in local Claude usage source — no external dashboard needed.

Runs the `ccusage` CLI (https://github.com/ryoppippi/ccusage) against your
local Claude Code logs (~/.claude/projects) and reduces the output to the
shape the collector expects:

    (active: bool, five_hour_pct: float | None, weekly_pct: float | None)

Percentages are measured against the highest previously observed block/week,
since Anthropic doesn't publish absolute plan limits.
Requires Node.js: `npm install -g ccusage`.
"""
import json
import shutil
import subprocess

# npm installs ccusage as a .cmd shim, which CreateProcess can't launch by
# bare name — resolve the full path (PATHEXT-aware) up front.
_CCUSAGE = shutil.which("ccusage")
# Don't flash a console window every poll when running under pythonw.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _run_json(args):
    if not _CCUSAGE:
        return {}
    try:
        r = subprocess.run([_CCUSAGE, *args], capture_output=True, text=True,
                           timeout=60, shell=False, creationflags=_NO_WINDOW)
        return json.loads(r.stdout)
    except Exception:
        return {}


def collect():
    blocks = _run_json(["blocks", "--json"]).get("blocks", [])
    weekly = _run_json(["weekly", "--json"]).get("weekly", [])

    active = next((b for b in blocks if b.get("isActive")), None)
    five_h = None
    if active:
        completed = [b.get("totalTokens", 0) for b in blocks
                     if not b.get("isGap") and not b.get("isActive")]
        limit = max(completed, default=0)
        if limit:
            five_h = round(active.get("totalTokens", 0) / limit * 100, 1)

    week_pct = None
    if weekly:
        current = weekly[-1].get("totalTokens", 0)
        prior_max = max((w.get("totalTokens", 0) for w in weekly[:-1]), default=0)
        limit = max(prior_max, current)
        if limit:
            week_pct = round(current / limit * 100, 1)

    return bool(active), five_h, week_pct

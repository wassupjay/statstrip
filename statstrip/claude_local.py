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
        d = json.loads(r.stdout)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _entries(payload, key):
    # ccusage's --json shape has shifted across versions; only ever hand
    # back a list of dicts, whatever it printed.
    v = payload.get(key, [])
    return [e for e in v if isinstance(e, dict)] if isinstance(v, list) else []


def _tokens(entry):
    v = entry.get("totalTokens")
    return v if isinstance(v, (int, float)) else 0


def collect():
    blocks = _entries(_run_json(["blocks", "--json"]), "blocks")
    weekly = _entries(_run_json(["weekly", "--json"]), "weekly")

    active = next((b for b in blocks if b.get("isActive")), None)
    five_h = None
    if active:
        completed = [_tokens(b) for b in blocks
                     if not b.get("isGap") and not b.get("isActive")]
        limit = max(completed, default=0)
        if limit:
            five_h = round(_tokens(active) / limit * 100, 1)

    week_pct = None
    if weekly:
        current = _tokens(weekly[-1])
        prior_max = max((_tokens(w) for w in weekly[:-1]), default=0)
        limit = max(prior_max, current)
        if limit:
            week_pct = round(current / limit * 100, 1)

    return bool(active), five_h, week_pct

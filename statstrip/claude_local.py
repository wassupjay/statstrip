"""Built-in local Claude usage source — no external dashboard needed.

Runs the `ccusage` CLI (https://github.com/ryoppippi/ccusage) against your
local Claude Code logs (~/.claude/projects) and reduces the output to the
same shape the remote-API mode expects:

    (active: bool, five_hour_pct: float | None, weekly_pct: float | None)

Percentages are measured against the highest previously observed block/week,
since Anthropic doesn't publish absolute plan limits.
Requires Node.js: `npm install -g ccusage`.
"""
import json
import subprocess


def _run_json(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                           shell=False)
        return json.loads(r.stdout)
    except Exception:
        return {}


def collect():
    blocks = _run_json(["ccusage", "blocks", "--json"]).get("blocks", [])
    weekly = _run_json(["ccusage", "weekly", "--json"]).get("weekly", [])

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

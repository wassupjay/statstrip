"""Accurate Claude usage from Claude Code's own session — primary source.

Reads the OAuth access token Claude Code keeps in ~/.claude/.credentials.json
and asks the same endpoint its /usage command uses, so the gauges show real
percent-of-plan-limit for the 5-hour block and the weekly window (the local
ccusage heuristic in claude_local.py can only compare against your own
history). Returns "login_required" when there's genuinely no usable login
(no token, expired, or the API rejects it), and None for anything transient
(rate limited, network blip, endpoint hiccup) — the caller should only tell
the user to log in for the former.

This is an undocumented internal endpoint: treat failures as routine, never
as fatal. The token is read fresh each poll (Claude Code rewrites the file
when it refreshes) and is never logged or written anywhere.
"""
import json
import time
from pathlib import Path

import requests

_CREDENTIALS = Path.home() / ".claude" / ".credentials.json"
_URL = "https://api.anthropic.com/api/oauth/usage"

_session = requests.Session()


def _token():
    try:
        oauth = json.loads(_CREDENTIALS.read_text(encoding="utf-8")).get("claudeAiOauth", {})
        token = oauth.get("accessToken")
        expires_ms = oauth.get("expiresAt")
        if not token:
            return None
        # Don't bother the API with a token we already know is stale.
        if isinstance(expires_ms, (int, float)) and expires_ms / 1000 < time.time():
            return None
        return token
    except Exception:
        return None


def _utilization(payload, key):
    v = payload.get(key)
    u = v.get("utilization") if isinstance(v, dict) else None
    return float(u) if isinstance(u, (int, float)) else None


def collect():
    """(active, five_hour_pct, weekly_pct) on success, "login_required" when
    there's no usable login, or None for a transient failure (retry later)."""
    token = _token()
    if not token:
        return "login_required"
    try:
        r = _session.get(_URL, timeout=15, headers={
            "Authorization": f"Bearer {token}",
            "anthropic-beta": "oauth-2025-04-20",
        })
        if r.status_code in (401, 403):
            return "login_required"
        if r.status_code != 200:
            return None  # rate limited, 5xx, etc — transient, not an auth problem
        payload = r.json()
        if not isinstance(payload, dict):
            return None
    except Exception:
        return None
    five_h = _utilization(payload, "five_hour")
    week = _utilization(payload, "seven_day")
    if five_h is None and week is None:
        return None
    return bool(five_h), five_h, week

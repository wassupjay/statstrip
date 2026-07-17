# StatStrip

[![PyPI](https://img.shields.io/pypi/v/statstrip)](https://pypi.org/project/statstrip/)
[![Python](https://img.shields.io/pypi/pyversions/statstrip)](https://pypi.org/project/statstrip/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows-0078d6)](https://github.com/wassupjay/statstrip)

**Live CPU, RAM, disk, GPU — and your Claude Code + OpenAI Codex usage limits — inside the Windows taskbar.**

No extra window, no wasted screen space: the numbers sit in the empty part of the taskbar itself.

![StatStrip running in the Windows taskbar, showing CPU 13%, RAM 40%, DISK 38%, GPU0 0%, GPU1 0%, CLAUDE 5h 79%, WEEK 16%, CODEX 7d 18% to the left of the taskbar icons](https://raw.githubusercontent.com/wassupjay/statstrip/main/images/screenshot.png)

<sup>That's the real thing, in a real taskbar — not a mockup.</sup>

If you use Claude Code or Codex all day, the question you actually care about isn't
CPU — it's *how much of my 5-hour block have I burned?* StatStrip keeps that
answer on screen, next to your hardware stats, without spending any of the quota
it's reporting.

- **Real plan limits, not estimates.** Percent-of-your-actual-limit, read from the
  same sources the tools use themselves.
- **Costs you nothing to watch.** The Codex gauges run no model — zero tokens. The
  Claude gauges reuse your existing login.
- **Never lies to you.** A number it can't verify is marked with its age or hidden
  outright. Stale figures that look live are treated as bugs, not features.
- **Nothing leaves your PC.** No API keys, no accounts, no telemetry, no server.

---

## Install (2 minutes, no technical knowledge needed)

1. **Download**: click the green **Code** button at the top of this page →
   **Download ZIP**, then right-click the file → **Extract All**.
2. **Run**: open the extracted folder and double-click **`install.bat`**.

That's it. The installer finds Python (and downloads it automatically if it's
missing — this can take a few minutes the first time), installs StatStrip, and
starts it. The stats appear in your taskbar right away and come back every time
you log in. To remove it, double-click `uninstall.bat` in the same folder.

> If the automatic Python download fails (older Windows without `winget`), install
> Python once from [python.org/downloads](https://www.python.org/downloads/) —
> tick **"Add python.exe to PATH"** — and run `install.bat` again.

## What the gauges mean

| On the strip | Meaning |
|---|---|
| `CLAUDE 5h 75%` | 75% of your Claude 5-hour block used |
| `WEEK 16%` | 16% of your Claude weekly limit used |
| `CLAUDE 5h idle` | No active 5-hour block right now |
| `CODEX 7d 14%` | 14% of your Codex weekly limit used |
| `~` prefix | An *estimate* from your own history, not a real plan limit |
| `(3h ago)` | A held reading — this old, not current. See [Honest numbers](#honest-numbers) |
| `reset` | That window rolled over; the old number is known to be wrong |
| `login required` | No usable login for that tool |
| `usage unavailable` | No trustworthy reading right now (transient — it retries) |

Codex names its own windows, and StatStrip shows whatever your plan reports rather
than assuming. On a **Plus** plan that's a single weekly window (`CODEX 7d 14%`);
other plans report more, including a 5-hour one.

## Privacy — no API keys, nothing leaves your PC

- **No API keys, no accounts, no signup.** The Claude gauges reuse the Claude Code
  login already on your PC — the same request Claude Code makes when you run
  `/usage`. No Claude Code? They show "login required"; set `STATSTRIP_CLAUDE=off`
  to hide them.
- **The Codex gauges don't spend any of your quota.** They ask your local `codex`
  CLI for your usage (`account/rateLimits/read`, the same call behind its
  `/status`), which runs no model and costs **zero tokens**.
- **Your stats stay on your machine.** Hardware numbers are read locally and served
  only on `127.0.0.1`. Nothing is uploaded, logged, or shared — there is no server,
  no telemetry, no third party.

## Honest numbers

Most of the engineering here is about *not* showing a plausible wrong number. A
usage gauge that quietly drifts is worse than no gauge, because you'll trust it.

- **Readings carry the instant they were taken**, and the display ages them itself.
  A collector that wedges shows a reading growing visibly older (`(3h ago)`), never
  one frozen at "just now".
- **A window that has since reset shows `reset`**, not a number known to be stale.
- **"Login required" is reserved for an actual missing login.** A rate limit, a
  network blip, or an endpoint hiccup says `usage unavailable` instead — sending you
  off to re-authenticate for a problem that isn't about auth is a bug.
- **StatStrip backs off instead of making things worse.** Claude's usage endpoint
  rate-limits; polling straight through a 429 keeps the limit alive, so failures
  back off exponentially and let it clear.
- **Anything outside a source's expected contract is refused**, not guessed at — an
  unparseable timestamp, a percentage outside 0–100, a renamed field.

## Configuration

All optional, set as environment variables before launching.

| Variable | Default | Meaning |
|---|---|---|
| `STATSTRIP_CLAUDE` | `on` | `on`: real plan-limit % via Claude Code's usage API. `estimate`: [`ccusage`](https://github.com/ryoppippi/ccusage) heuristic over local logs, shown with a `~` prefix. `off`: hide the gauges. |
| `STATSTRIP_CODEX` | `on` | `on`: live % via `codex app-server` (zero tokens), falling back to Codex's session logs. `log`: session logs only — passive, but only as fresh as your last local Codex turn. `off`: hide the gauges. |
| `STATSTRIP_TASKBAR` | `1` | `1`: embed in the taskbar, left of the tray icons. `0`: float a bar just above it. |
| `STATSTRIP_ALIGN` | `right` | Position in the taskbar: `right` hugs the tray icons; `left` hugs the left edge (use when the readout collides with Windows 11's centered app icons). |
| `STATSTRIP_DISK_PATH` | `C:\` | Drive/path to report disk usage for. |
| `STATSTRIP_PORT` | `5757` | Local port the collector serves `/stats` on. |
| `STATSTRIP_CORS` | *(unset)* | `Access-Control-Allow-Origin` for `/stats`. Unset = no CORS header, so websites can't read your machine stats. |
| `STATSTRIP_STATS_FILE` | `%TEMP%\statstrip-stats.json` | Where the snapshot JSON is written. |
| `STATSTRIP_LOCAL_REFRESH` | `2` | Seconds between CPU/RAM/disk/GPU polls. |
| `STATSTRIP_CLAUDE_REFRESH` | `60` | Seconds between Claude usage polls. |
| `STATSTRIP_CODEX_REFRESH` | `60` | Seconds between Codex usage polls. |
| `STATSTRIP_CLAUDE_BACKOFF_MAX` | `1800` | Longest wait between Claude retries while its endpoint is refusing us. |
| `STATSTRIP_CLAUDE_STALE_AFTER` | `600` | Age past which a held Claude reading is shown with `(… ago)`. |
| `STATSTRIP_CODEX_STALE_AFTER` | `900` | Same, for a log-sourced Codex reading. |

## Architecture

Two independent layers, so the data is reusable outside this app — point any script,
dashboard, or website at the same local endpoint.

```
┌──────────────────┐      writes/serves       ┌─────────────────┐
│    collector     │ ───────────────────────▶ │  stats.json      │
│  (psutil/pynvml, │                          │  127.0.0.1:5757  │
│   Claude + Codex │◀───────── read only ─────┤      /stats      │
│      usage)      │                          └────────┬─────────┘
└──────────────────┘                                   │
                                             ┌─────────▼──────────┐
                                             │      display        │
                                             │ (taskbar bar, or    │
                                             │  your own consumer) │
                                             └─────────────────────┘
```

- **`collector.py`** — extraction only. Polls hardware, Claude and Codex usage, then
  writes a merged snapshot to a JSON file and serves it on
  `http://127.0.0.1:5757/stats`.
- **`display.py`** — consumption only. Renders the bar embedded inside the taskbar
  (TrafficMonitor-style, transparent, left of the tray icons). It has zero knowledge
  of collection internals — it's just one consumer of the feed.
- **`claude_oauth.py`** — primary Claude source: the same endpoint Claude Code's
  `/usage` uses, authenticated with the token it already stores locally.
- **`claude_local.py`** — opt-in estimate mode (`STATSTRIP_CLAUDE=estimate`): shells
  out to `ccusage` over your local logs and estimates against your own historical
  maximum (can exceed 100% — it's an estimate, not a plan limit).
- **`codex_appserver.py`** — primary Codex source: asks `codex app-server` for
  `account/rateLimits/read`, the call the Codex TUI makes to refresh its own usage.
  Runs no model, so it's free to poll — and it reports your whole account, including
  Codex you ran on another machine.
- **`codex_local.py`** — fallback Codex source (`STATSTRIP_CODEX=log` forces it):
  reads the rate-limit snapshot Codex writes into its session logs. Fully passive,
  but only sees turns run *on this machine* — measured 6 points behind the live
  figure — so its readings carry an age marker.

Anything else — a browser tab, another script, an Electron app — can hit the same
`/stats` endpoint or read the JSON directly. (Browser pages need `STATSTRIP_CORS`;
it's off by default.)

## Roadmap

Ideas for where StatStrip goes next. None are locked in — they're here to
show the direction and to mark good places to jump in. If one interests you,
there's likely a matching [issue](https://github.com/wassupjay/statstrip/issues)
tagged `good first issue` or `help wanted`; comment there before starting so we
don't duplicate work.

- **Skins / themes.** Colors and font are currently hardcoded
  (`display.py:22-23`, `:263`). Make them configurable — env vars or a small
  theme file — and ship a few presets (light, high-contrast, mono, a couple of
  accent colors). Good first contribution: self-contained, no data-layer risk.
- **More AI providers.** The Claude and Codex gauges follow the same shape
  (read a real usage source, render honest percentages). Gemini CLI, Cursor,
  and others expose usage the same way and could slot in beside them.
- **Pick your metrics.** Let users choose which readings show and in what
  order (per-core CPU, network throughput, battery, temperatures), instead of
  the fixed CPU/RAM/DISK/GPU set.
- **Click to expand.** A click on the strip could open a small panel with the
  detail the taskbar has no room for — GPU VRAM, per-window reset times, the
  history behind an estimate.
- **A proper config file.** Today everything is environment variables. A
  `statstrip.toml` next to a system-tray settings toggle would be friendlier
  for non-technical users than editing env vars.
- **Continuous integration.** Run the 101 tests on every push across the
  supported Python versions, so a regression is caught before it ships.
- **Beyond Windows?** The taskbar embedding is Windows-only by nature, but the
  collector and the `/stats` feed are portable — a Linux tray applet or a macOS
  menu-bar consumer could reuse the whole data layer untouched. A big lift, but
  the architecture already allows it.

Have a different idea? [Open an issue](https://github.com/wassupjay/statstrip/issues/new) —
feature requests are as welcome as code.

## Development

Requires Python 3.9+ on Windows. NVIDIA GPU optional — it degrades gracefully.

Published on PyPI — [pypi.org/project/statstrip](https://pypi.org/project/statstrip/):

```
pip install statstrip
statstrip-collector
statstrip-display
```

This gives you the two commands and the `/stats` feed, but not the auto-start at
login — for that, use `install.bat` above. Or work from a clone:

```
git clone https://github.com/wassupjay/statstrip.git
cd statstrip
pip install .
statstrip-collector
statstrip-display
```

Run the tests (no dependencies beyond the package itself):

```
python -m unittest discover -s tests
```

Contributions welcome — issues and PRs both. See
[CONTRIBUTING.md](CONTRIBUTING.md) for setup and the one house rule:
**a gauge must never show a number it can't stand behind.** If a source fails, is
stale, or returns something outside its contract, say so or say nothing.

## License

MIT — see [LICENSE](LICENSE).

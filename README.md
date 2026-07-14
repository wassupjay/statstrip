# StatStrip

System stats readout for Windows, embedded directly inside the taskbar
(TrafficMonitor-style — just left of the tray icons, transparent background,
zero extra screen space). Shows CPU, RAM, disk, GPU(s), and your Claude Code
usage (5-hour block + weekly) — everything read locally from this PC, no
external services. Set `STATSTRIP_TASKBAR=0` to get a floating always-on-top
bar above the taskbar instead.

```
CPU 34%   RAM 61%   DISK 72%   GPU0 18%   GPU1 0%   CLAUDE 5h 47%   WEEK 63%
```

## Architecture

Split into two independent layers so the data is reusable outside this app —
point any other script, dashboard, or website at the same local endpoint.

```
┌─────────────────┐      writes/serves       ┌────────────────┐
│   collector      │ ───────────────────────▶ │ stats.json      │
│  (psutil/pynvml,  │                          │ 127.0.0.1:5757  │
│   ccusage for     │                          │      /stats     │
│   Claude usage)    │◀────────── read only ───┤                │
└─────────────────┘                          └────────┬────────┘
                                                        │
                                              ┌─────────▼─────────┐
                                              │     display        │
                                              │ (tkinter bar, or    │
                                              │  your own consumer) │
                                              └────────────────────┘
```

- **`statstrip/collector.py`** — extraction only. Polls local hardware
  stats and local Claude usage, then writes the merged snapshot to a JSON
  file and serves it over `http://127.0.0.1:5757/stats`.
- **`statstrip/claude_oauth.py`** — primary Claude usage source: asks the
  same endpoint Claude Code's `/usage` command uses (authenticated with the
  token Claude Code already stores locally), so the gauges show your real
  percent-of-plan-limit numbers.
- **`statstrip/claude_local.py`** — opt-in estimate mode
  (`STATSTRIP_CLAUDE=estimate`): shells out to
  [`ccusage`](https://github.com/ryoppippi/ccusage) over your local Claude
  Code logs (`~/.claude/projects`) and estimates percentages against your
  own historical maximum (can exceed 100% — it's an estimate, not a plan
  limit; shown with a `~` prefix).
- **`statstrip/display.py`** — consumption only. Polls that endpoint
  and renders the bar. Has zero knowledge of psutil/pynvml/HTTP polling
  internals — it's just one consumer of the feed.

Anything else — a browser tab, another Python script, an Electron app — can
hit the same `/stats` endpoint or read the JSON file directly. (Browser pages
need `STATSTRIP_CORS` set; it's off by default so arbitrary websites can't
read your machine stats.)

## Install

Requires Python 3.9+ on Windows (NVIDIA GPU optional; the app degrades
gracefully without one).

```
git clone <this-repo>
cd statstrip
install.bat
```

`install.bat` does three things: `pip install`s the package (adds
`statstrip-collector` / `statstrip-display` to PATH), drops a shortcut in the
per-user Startup folder so it starts on every login (no admin required), then
runs it immediately.

To remove: run `uninstall.bat`.

### Manual run (no auto-start)

```
pip install .
statstrip-collector
statstrip-display
```

Or without installing:

```
pip install -r requirements.txt
python -m statstrip.collector
python -m statstrip.display
```

## Configuration

All optional, set as environment variables before launching:

| Variable              | Default              | Meaning                                   |
|------------------------|-----------------------|--------------------------------------------|
| `STATSTRIP_CLAUDE`           | `on`                  | `on`: real plan-limit % via Claude Code's usage API; shows `CLAUDE login required` when there's no usable local login. `estimate`: ccusage heuristic over local logs (`npm install -g ccusage`), rendered with a `~` prefix. `off`: hide the gauges. |
| `STATSTRIP_TASKBAR`          | `1`                   | `1`: embed the readout inside the taskbar, left of the tray icons. `0`: float a separate bar just above the taskbar. |
| `STATSTRIP_ALIGN`            | `right`               | Position inside the taskbar: `right` hugs the tray icons; `left` hugs the left edge (use when the readout collides with centered app icons). |
| `STATSTRIP_DISK_PATH`        | `C:\`                 | Drive/path to report disk usage for.       |
| `STATSTRIP_PORT`             | `5757`                | Local port the collector serves `/stats` on. |
| `STATSTRIP_CORS`             | *(unset)*             | `Access-Control-Allow-Origin` value for `/stats` (e.g. `*`). Unset = no CORS header, so browser pages can't read the feed. |
| `STATSTRIP_STATS_FILE`       | `%TEMP%\statstrip-stats.json` | Where the snapshot JSON is written.      |
| `STATSTRIP_LOCAL_REFRESH`    | `2`                   | Seconds between CPU/RAM/disk/GPU polls.    |
| `STATSTRIP_CLAUDE_REFRESH`   | `60`                  | Seconds between ccusage polls.   |

## License

MIT — see [LICENSE](LICENSE).

# StatStrip

Always-on-top system stats bar for Windows. Sits docked just above the real
taskbar, showing CPU, RAM, disk, and GPU(s) — with optional gauges for a
Claude usage dashboard's 5-hour and weekly limits.

```
CPU 34%   RAM 61%   DISK 72%   GPU0 18% 2100/12288MB   GPU1 0% 400/12288MB   CLAUDE 5h 47%   WEEK 63%
```

## Architecture

Split into two independent layers so the data is reusable outside this app —
point any other script, dashboard, or website at the same local endpoint.

```
┌─────────────────┐      writes/serves       ┌────────────────┐
│   collector      │ ───────────────────────▶ │ stats.json      │
│  (psutil/pynvml,  │                          │ 127.0.0.1:5757  │
│   optional Claude │                          │      /stats     │
│   API poll)        │◀────────── read only ───┤                │
└─────────────────┘                          └────────┬────────┘
                                                        │
                                              ┌─────────▼─────────┐
                                              │     display        │
                                              │ (tkinter bar, or    │
                                              │  your own consumer) │
                                              └────────────────────┘
```

- **`statstrip/collector.py`** — extraction only. Polls local
  hardware stats and (if configured) a remote Claude usage API, then writes
  the merged snapshot to a JSON file and serves it over
  `http://127.0.0.1:5757/stats`.
- **`statstrip/display.py`** — consumption only. Polls that endpoint
  and renders the bar. Has zero knowledge of psutil/pynvml/HTTP polling
  internals — it's just one consumer of the feed.

Anything else — a browser tab, another Python script, an Electron app — can
hit the same `/stats` endpoint or read the JSON file directly.

## Install

Requires Python 3.9+ on Windows (NVIDIA GPU optional; the app degrades
gracefully without one).

```
git clone <this-repo>
cd statstrip
install.bat
```

`install.bat` does three things: `pip install`s the package (adds
`statstrip-collector` / `statstrip-display` to PATH), registers a Task Scheduler entry so
it starts on every login, then runs it immediately.

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
| `STATSTRIP_CLAUDE_API_URL`   | *(unset)*             | URL of a Claude usage dashboard `/api` endpoint returning `{"active": bool, "tokens_pct": float, "weekly": {"pct": float}}`. Leave unset to disable the Claude gauges. |
| `STATSTRIP_DISK_PATH`        | `C:\`                 | Drive/path to report disk usage for.       |
| `STATSTRIP_PORT`             | `5757`                | Local port the collector serves `/stats` on. |
| `STATSTRIP_STATS_FILE`       | `%TEMP%\statstrip-stats.json` | Where the snapshot JSON is written.      |
| `STATSTRIP_LOCAL_REFRESH`    | `2`                   | Seconds between CPU/RAM/disk/GPU polls.    |
| `STATSTRIP_CLAUDE_REFRESH`   | `60`                  | Seconds between remote Claude API polls.   |

## License

MIT — see [LICENSE](LICENSE).

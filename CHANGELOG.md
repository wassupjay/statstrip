# Changelog

All notable changes to StatStrip are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
this project uses [Semantic Versioning](https://semver.org/).

## [2.0.0] — 2026-07-17

StatStrip 1.x showed your machine and your Claude usage. 2.0 adds Codex, and
makes both gauges honest about what they actually know.

### Added

- **OpenAI Codex usage gauges.** `CODEX 7d 14%` alongside the Claude ones.
  Window names come from Codex itself rather than being hardcoded, so whatever
  windows your plan reports is what you see — on a Plus plan that's a single
  weekly window; other plans report more.
- **Live Codex usage at zero token cost** (`statstrip/codex_appserver.py`).
  Asks `codex app-server` for `account/rateLimits/read` — the same call the
  Codex TUI makes to refresh its usage. It runs no model, so polling it every
  minute costs nothing, and it reports your whole account including Codex you
  ran on another machine.
- **Passive Codex fallback** (`statstrip/codex_local.py`, or
  `STATSTRIP_CODEX=log`). Reads the rate-limit snapshot Codex writes into its
  own session logs. No network at all, but it only sees turns run on this
  machine — measured 6 percentage points behind the live figure — so its
  readings carry an age marker.
- **Staleness markers.** A held reading shows its age (`(3h ago)`) instead of
  posing as current, and a window that has since reset shows `reset` rather
  than a number known to be wrong.
- **Exponential backoff for Claude's usage endpoint.** It rate-limits routinely;
  polling straight through a 429 every 60s kept the limit alive, so StatStrip
  was prolonging the outage it was reporting. Failures now back off (capped by
  `STATSTRIP_CLAUDE_BACKOFF_MAX`) and success resets it.
- **The project's first test suite** — 101 tests covering both usage sources,
  the display's rendering branches, and the collector loops.
- New settings: `STATSTRIP_CODEX`, `STATSTRIP_CODEX_REFRESH`,
  `STATSTRIP_CODEX_STALE_AFTER`, `STATSTRIP_CLAUDE_BACKOFF_MAX`,
  `STATSTRIP_CLAUDE_STALE_AFTER`.
- `codex_source` in the `/stats` feed (`live` or `log`), so a live source that
  has quietly started failing is visible rather than masked by the fallback.

### Changed

- **A transient Claude failure no longer blanks the gauges.** Usage doesn't move
  meaningfully in a minute, so one 429 discarding a good reading was the wrong
  trade — that's what made the gauges flicker between real numbers and
  "usage unavailable". The reading is now held, with its age shown.
- `/stats` gained `claude_captured_at`, `codex_windows`, `codex_captured_at`,
  `codex_status` and `codex_source`. Existing fields are unchanged.

### Fixed

- **Leaked Codex processes.** On Windows `codex` is a `.cmd` shim, so the process
  tree is `cmd.exe → node.exe → codex.exe` and killing the child only reaped the
  shim. Every failed poll orphaned an app-server — once a minute, forever,
  invisibly, while the fallback kept the gauge looking fine. The tree is now
  killed properly.
- **Leaked reader threads.** The stdout reader was never unblocked on timeout,
  leaking a thread and its pipes per poll. stdin is now closed first — the
  documented way the app-server exits, and what lets the reader see EOF.
- **Codex reset detection never fired.** Codex reports `resets_at` as an absolute
  epoch, not the `resets_in_seconds` offset first assumed. The field was simply
  never found, so a snapshot whose window had already reset would show its old
  percentage as current.
- A reset time that can't be true (already past at capture, or further out than a
  whole window — a seconds/milliseconds mixup) is ignored rather than trusted.
- A live Codex reading is no longer marked `reset` when a poll lands just after
  one; the server has already applied the reset, so that figure is correct.
- Only the `codex` metering bucket is accepted from the multi-bucket rate-limit
  view — any other key is a different limit entirely.
- A server-originated JSON-RPC request sharing our request id is no longer
  mistaken for our reply (ids are per-direction).
- Timestamps without a timezone are refused rather than read as local time, which
  invented an age and could push a capture into the future — making a stale
  snapshot look brand new.
- Codex percentages outside 0–100, or boolean values, are refused instead of
  rendered.

## [0.1.0]

Initial release.

- CPU, RAM, disk and multi-GPU stats embedded directly in the Windows taskbar
  (TrafficMonitor-style), with a floating-bar fallback.
- Claude Code usage gauges: real percent-of-plan-limit via Claude Code's own
  usage endpoint, plus an opt-in `ccusage` estimate mode.
- Collector/display split, with the snapshot served on `127.0.0.1:5757/stats`
  and written to a JSON file for any other consumer.
- `install.bat` with automatic Python detection and install, and a Startup-folder
  shortcut requiring no admin rights.

[2.0.0]: https://github.com/wassupjay/statstrip/releases/tag/v2.0.0

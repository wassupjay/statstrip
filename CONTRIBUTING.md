# Contributing to StatStrip

Thanks for considering it — issues and pull requests are both welcome, and a
good feature request is as valuable as code.

## The one rule

**A gauge must never show a number it can't stand behind.**

Everything else is negotiable; this isn't. A usage bar that quietly drifts is
worse than no bar, because people trust it. So if a data source fails, is
stale, or returns something outside its expected contract, the display must say
so (a `(3h ago)` age marker, `usage unavailable`, hiding the gauge) — never
show a plausible wrong number. Most of the existing tests exist to pin exactly
this, and the bugs worth catching in review are the ones that break it.

## Getting set up

```
git clone https://github.com/wassupjay/statstrip.git
cd statstrip
pip install .
python -m unittest discover -s tests
```

Requires Python 3.9+ on Windows. An NVIDIA GPU is optional — the code degrades
gracefully without one. You can run the collector and display separately
(`statstrip-collector`, `statstrip-display`) to see changes live.

## Before you start

- For anything more than a small fix, **comment on an issue first** (or open
  one) so we don't both build the same thing. Issues tagged
  [`good first issue`](https://github.com/wassupjay/statstrip/labels/good%20first%20issue)
  are scoped to be a gentle way in.
- The [Roadmap](README.md#roadmap) lists where the project is heading — a good
  place to find something worth doing.

## Pull requests

- **Add a test for behaviour you change**, especially anything on the
  data-honesty path above. The suite runs with no dependencies beyond the
  package itself.
- Keep the collector (data) and display (rendering) layers separate — the
  display is just one consumer of the `/stats` feed and shouldn't reach into
  collection internals.
- Match the surrounding style. Comments should explain *why* something is the
  way it is, not narrate *what* the next line does.
- Describe what you changed and how you checked it. "Ran the app and watched
  the gauge" is a perfectly good check for something with a visible effect.

## Reporting bugs

Open an [issue](https://github.com/wassupjay/statstrip/issues/new) with your
Windows and Python versions, what you saw on the strip, and what you expected.
A screenshot of the taskbar is worth a lot here.

By contributing, you agree your work is licensed under the project's
[MIT License](LICENSE).

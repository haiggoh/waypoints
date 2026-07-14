# waypoints v0.1.3 — `edit`/`show` commands + `summary` banner tier

**Date:** 2026-07-14 · **Status:** approved (design finalized 2026-07-13; implemented 2026-07-14)

## Problem

Two requests that turned out to share one root cause:

1. **Add an `edit`/`update` command.** With only `add`/`done`/`prune`, changing a waypoint meant
   `done` the old one + `add` a new one. That workaround has side effects: it regenerates the `id`,
   drops the original `created` date, and leaves a false `✓done` that really means "superseded."
2. **Keep the banner tidy without discarding context.** Some waypoints need a large continuity dump
   to survive a `/clear`, but that dump should not render in the SessionStart banner. The
   `run-adobe-cutout-re-test…` item is the cautionary example — its entire detail got crammed into
   `title` (a ~128-char headline) precisely because the `done`+re-`add` workaround pushed everything
   into the one field the banner shows.

The bloated banner is a **data-hygiene** failure caused by the **missing `edit` verb**, not a schema
gap — the store already had `title`/`detail` and the banner already rendered `title` only.

## Decisions (locked in)

- **Banner shape → 3 tiers:** `title` (headline, shown) + `summary` (a few short bullets, shown
  under the title) + `detail` (full dump, **on-demand only**, never in the banner).
- **Detail's home → the JSON store field, not memory.** Checked against the `where-rules-live`
  memory: memory is *relevance-recalled* (not guaranteed to load), but continuity after `/clear`
  must be *deterministic* (read by id, every time); and splitting one waypoint across two systems
  recreates the duplication `where-rules-live` warns against. The store must also stay
  self-contained because `waypoints` is a published plugin (other installers may not use memory).
- **`summary` is a list of short strings**, not a free-text blob — a list makes each bullet atomic
  and structurally un-bloatable, which is what enforces "tidy."
- **`reopen`/`reorder`/`priority`/`done-toggle` deferred** to a later version.

## Implementation

- **`summary` field** (list) — additive + optional; existing items with no `summary` render
  title-only (backward compatible via `.get()`).
- **`edit <id>`** — `--title`, `--point` (repeatable, replaces summary), `--clear-summary`,
  `--detail` (`""` clears), `--surface-on`, `--clear-surface-on`. Only passed fields change
  (an `_UNSET` sentinel in `edit_item` distinguishes "not passed" from "explicitly cleared").
  **`id` and `created` are immutable** — the whole reason `edit` exists.
- **`show <id>`** — prints title + summary bullets + dates + full detail (the "pick it up" view).
  The hook's model-facing context now tells Claude to `show <id>` when resuming an item.
- **`add --point`** — parity with `edit` for setting summary bullets at creation.
- **Slug cap (50 chars, trimmed at a hyphen boundary)** — companion polish so a long title can't
  produce a monstrous id.

## Tests

TDD, `pytest tests/` — core behavior in `test_waypoints.py` (slug cap, `summary`, `edit_item`
field-isolation + id/created immutability + surface_on sentinel, `get_item`, summary-aware banner),
CLI/hook wiring in `test_hook_and_cli.py` (`add --point`, `edit` retitle-keeps-id, `edit` summary,
missing-id → exit 1, `show`, `--clear-surface-on`). 34 passing.

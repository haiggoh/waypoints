# waypoints v0.1.12 — resolve-before-close (`done --as` + unresolved-title guard)

**Date:** 2026-08-01 · **Status:** approved

## Problem

`done <id>` flips only the `done` flag; it never touches `title`/`summary`. When a waypoint is
phrased as an **open question or pending decision** — "Confirm qwen thinking works", "Decide + open
the Adobe PRs", "Test CC Live queue-vs-interrupt behavior" — closing it leaves the interrogative
prose standing next to a ✓. The archived record then contradicts itself: `waypoints.py list` shows
`✓ [id] Confirm qwen thinking works` and `show` prints the same title with `done: True`, so the item
reads as an unresolved question that is also marked resolved — and the *answer* (did it work? what
was decided?) is nowhere.

This is the `waypoint-title-before-done` feedback: "update the title to reflect the actual resolution
before closing; don't leave a stale question on a closed item." Today that depends entirely on the
agent remembering to `edit` then `done` — nothing looks at the title at close time, so the mismatch
is invisible at the exact moment it's created.

## Decision

Rewrite the title with the resolution (not a new `resolution` field). Matches the feedback's wording,
needs no schema change, and the resolution phrasing normally implies the original question. Enforce
it at the point of action, not just in prose.

## Implementation — three layers

- **Layer 1 — `done <id> --as "resolved headline"` (ergonomic close).** One atomic call that rewrites
  the title to the resolution *and* marks done, replacing the two-step `edit`+`done`. `id`/`created`
  stay immutable (same guarantee as `edit`). `mark_done` gains an optional `resolved_title` argument;
  when provided it sets the title before flipping the flag.

- **Layer 2 — unresolved-title guard (the robust part).** A pure `looks_unresolved(title)` heuristic
  in `waypoints_core.py`: True when the title ends with `?`, or its first word is an
  *inquiry/decision* verb (confirm, verify, check, test, decide, research, investigate, evaluate,
  determine, assess, explore, compare, figure, whether, should, head-to-head). Plain task imperatives
  (fix, add, build, publish, finish) are deliberately **excluded** — "Fix login bug ✓" reads fine as
  a completed task; the contradiction is specific to inquiry/decision phrasing whose ✓ hides the
  answer. When `done` is called **without** `--as` on a matching title, it still marks done (a close
  is never blocked) and prints a **non-blocking** nudge to stderr suggesting the `--as` re-run. This
  is the key lever: it fires at the moment the contradiction would be baked in, so it works even when
  the prompted rule is forgotten — and it matches the plugin family's `no-hidden-changes` spirit
  (surface the mismatch, don't silently commit it).

- **Layer 3 — documented convention (prompt).** A short rule in `SKILL.md` next to the `done` docs
  describing `--as` and the resolve-before-close convention, plus a memory update pointing
  `waypoint-title-before-done` at the shipped mechanism.

## Tests

`pytest tests/` — core: `looks_unresolved` positive (question mark, each inquiry verb) and negative
(plain imperatives, statements); `mark_done(resolved_title=…)` rewrites title + sets done + keeps
id/created. CLI/hook: `done --as` retitles and closes in one call; `done` without `--as` on an
unresolved title emits the warning and still marks done; `done --as` on such a title stays quiet.

## Non-goals

No `resolution` field, no blocking a close, no touching already-clean imperative closes, no change to
banner rendering (done items never appear in the banner regardless).

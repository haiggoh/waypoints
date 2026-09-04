# Changelog

All notable changes to `waypoints` are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

**Provenance.** This file was reconstructed on 2026-09-03, after the fact, from the complete
first-parent Git history. Each commit was read together with the release it actually shipped in —
that is, the next version bump at or after it, *not* the version its own message happens to mention,
which is usually the previous release. Release dates are the date of the commit that set
`.claude-plugin/plugin.json` to that version. Entries therefore summarise recorded commits rather
than reproducing notes written at release time.

**Tags.** Annotated tags exist from ``v0.2.0`` onward, each on the commit that set `plugin.json` to
that version. Earlier versions are deliberately untagged: they are early-development releases nobody
would cite.

## [Unreleased]

_Nothing yet._

## [0.7.0] — 2026-09-04

### Added
- **`recover`** — the sanctioned file-level repair when the store itself is unreadable. Puts the
  newest backup that actually **parses** back in place (`--list` to see the candidates, `--from` to
  choose one), keeps the replaced file, and **journals** the event. Recovering over a *readable*
  store requires `--yes`, because that is the case that discards live data.
- **`pin <id> --because "…"` / `unpin`** — the machine-visible "heavy, but do it now anyway".
  Tier ordering dominates priority, so a heavy item a user wants done today previously had no
  field to say so, only a prose note no mechanism could see. A pin outranks the tier order and
  sorts ahead of priority; the **reason is required**, and the **tier is left alone** — a pin
  changes when an item runs, never the assessment of how big it is. Pinned items render as their
  own top section in `list`, are marked 📌 in the banner (with the reason, even in compact mode),
  and are never collapsed into the "N gated" count.
- `waiting` items can hold multiple targets via a repeatable `--waiting-on "<id> @ <milestone>"`
  (committed 2026-09-01, unreleased until now): `waiting_on` is always a list, release requires
  **all** targets to land, a single missing target makes the whole spec stale (and stale dominates
  landed), and `waiting_status` reports the target that explains the verdict — the offending one
  when stale, the first pending one otherwise.

### Changed
- **A corrupt store is now REFUSED instead of read as empty.** `load_store` raises `StoreCorrupt`;
  the CLI prints what broke, where the damaged bytes were preserved and which backup to recover
  from, then exits 2 **without writing**. Previously an unparseable store read as zero items and
  the next write made that emptiness canonical — data loss by default (this is what happened on
  2026-09-03). A *missing* store is still a first run, not corruption: the two are now distinct.
- **The SessionStart banner is loud about it.** A corrupt store used to make the banner vanish
  silently — the most alarming state producing the least alarming output. It now emits an explicit
  "THE STORE IS UNREADABLE" notice to both the user and the model, still exits 0, and never blocks
  a session.
- **Corruption evidence is kept OUT of the rotating backup ring.** The damaged file is copied to
  `<store>.corrupt-<stamp>` beside the store, where retention cannot reach it; the 10-deep ring
  had already evicted the 2026-09-03 evidence before it could be examined. Repeated reads of one
  corrupt file reuse the existing copy rather than littering.
- **`LIST_CONTRACT` 2 → 3**: adds `pinned` / `pin_reason` per item and a `pinned` count. Additive —
  the tier sum invariant is unchanged, because pinned is orthogonal to the tiers rather than a
  fifth one. The bump is there because the field carries an **ordering rule** a consumer must
  honour to be correct, which cannot be discovered from the shape.

### Documentation
- **"Never hand-edit the store" is now rule zero**, stated first in the skill, the injected banner
  context, the CLI `--help` and the core module — with the one-line reason (the file is one JSON
  document, so a botched escape makes *every* item unreadable, not one). Verified by dispatching
  the rule text to a non-Claude local model, which reached for the CLI rather than the file.

## [0.6.0] — 2026-08-31

### Added
- `waiting` tier: blocked only on another item in this store reaching a milestone
- `--waiting-on "<item-id> @ <milestone>"` — milestone required; bare id or no target refused
- Closing a target auto-releases dependents to `untriaged` (not a guessed `do-now`)
- Promotion fires on `done`, not on read; `resolve` covers drift

### Changed
- `list` is now title-only and grouped (~19.6 KB for a 148-item store); bullets, gate reasons and dates moved to `--verbose` and `show`
- A bare `waypoints` shows a ~1 KB dashboard instead of an argparse error
- `bin/waypoints` (extensionless) resolves its own symlink chain; `bin/waypoints.py` stays as a compatibility entry point
- Pagination bounded by measured output size AND item count, not a fixed count
- `waiting` gets its own section between `actionable` and `gated`
- `LIST_CONTRACT` bumped 1 → 2 (the documented sum invariant changed)

### Fixed
- Resolving a `waiting` target against a filtered list no longer reports valid targets as missing

## [0.5.1] — 2026-08-27

### Fixed
- Journal display keeps one line per entry when `--detail` carries a long dump; whitespace collapsed and each token capped at 60 chars (raw argv on disk untouched)

## [0.5.0] — 2026-08-27

### Added
- Append-only journal: one permanent JSONL line per mutation, holding raw argv and before/after of each changed item
- `waypoints.py journal [--id <id>] [--since YYYY-MM-DD]`, with `JOURNAL_CONTRACT=1` versioned independently of the store

### Changed
- Snapshot ring retention reduced 20 → 10 (history now lives in the journal)

## [0.4.0] — 2026-08-27

### Added
- `waiting` tier support (see 0.6.0)

### Changed
- `prune` now moves `done` items to `~/.claude/waypoints-archive.json` (stamped `archived_at`) instead of destroying them
- `rm <id>` archives (never deletes); accepts open items
- `rm <id> --delete --confirm` permanently deletes from the archive only
- `restore <id>` brings an archived item back as `done`; `reopen <id>` auto-restores and reopens in one step
- `archive list [--json]` / `archive show <id>` read the trail

### Fixed
- Recoverable writes: every store/archive write copies the current file to `~/.claude/waypoints-backups/` before rewriting (atomic writes plus snapshots)
- Banner capped to the 10 highest-priority items, long titles trimmed to one line, remainder disclosed as a count

## [0.3.0] — 2026-08-26

### Added
- `edit --add-point` appends bullets, keeping existing ones

### Fixed
- `edit --point` now fails closed instead of silently wiping bullets: refuses when bullets already exist unless `--replace-points` is also passed (exit 2, store untouched)
- Destructive paths (`--point` replace, `--clear-summary`) echo the bullets they discard
- Missing id reported before any summary handling

## [0.2.0] — 2026-08-14

### Added
- `list --json` — documented payload with a `contract` version separate from the store's `version`
- Optional `tier` (`do-now|heavy|gated`) + `gate_reason`, set via a new `triage` subcommand
- Gated items marked ⛔ in the banner; past `GATED_COLLAPSE_THRESHOLD` the group collapses to one counted line naming `/waypoints-gated`

### Fixed
- textwrap no longer splits hyphenated tokens (kebab-case ids, `/slash-commands`) mid-token in the banner

## [0.1.12] — 2026-08-01

### Added
- `done <id> --as "resolution"` rewrites the title to the outcome and closes in one atomic call
- `looks_unresolved(title)` heuristic emits a non-blocking ⚠️ nudge when an open-question/decision title is closed without `--as`

## [0.1.11] — 2026-07-24

### Changed
- SessionStart banner wait for `resume-interrupted`'s flag reduced: `BANNER_WAIT_S` 0.75 → 0.5s, poll 0.05 → 0.03s (both still env-overridable)

## [0.1.10] — 2026-07-16

### Fixed
- `(since DATE)` now renders on its own hanging-indented line, making every bullet's indentation deterministic regardless of terminal width or title length

## [0.1.9] — 2026-07-16

### Fixed
- Banner now pre-wraps at 72 columns to stop Claude Code's renderer double-wrapping hanging indents on narrower panes

## [0.1.8] — 2026-07-16

### Fixed
- `(since DATE)` no longer splits mid-phrase on wrap; a non-breaking space keeps the annotation unbreakable

## [0.1.7] — 2026-07-16

### Changed
- `slugify()` cap reduced 50 → 30 chars
- Banner no longer prints `[id]` next to each title (ids remain via `waypoints.py list` / `show <id>`)
- Wrapped bullet/summary lines now hang-indent under the text start column

## [0.1.6] — 2026-07-15

### Changed
- Compact banner mode past 3 open items: per-item detail points dropped, replaced with a one-line pointer to `waypoints.py show <id>`

## [0.1.5] — 2026-07-15

### Added
- Banner optionally sequences after `resume-interrupted`'s banner when that plugin is installed AND enabled (zero added latency and zero behavior change when it isn't)

## [0.1.4] — 2026-07-15

### Added
- `reopen <id>`: undo a mistaken `done` without regenerating the id
- `toggle`: flip done state in one call
- `priority <id> <level>`: higher sorts earlier in the banner
- `reorder <id> <position>`: explicit manual list-order override

### Changed
- `SKILL.md` description now triggers on generic open-item phrasing (to-do, loose end, remind me, don't let me forget) without requiring the word "waypoint"

## [0.1.3] — 2026-07-14

### Added
- `edit <id>`: update in place with id + created immutable
- `show <id>`: title + summary + full detail 'pick it up' view; hook points the model at it when resuming an item

### Changed
- `summary` (list) tier now renders title + short `--point` bullets; full detail stays on-demand only

## [0.1.2] — 2026-07-13

### Changed
- Waypoints are now conversation-managed rather than via a console command
- User-facing systemMessage drops the console command and leads with 🧭; model context carries the correct `waypoints.py done <id>` invocation

## [0.1.1] — 2026-07-13

### Changed
- SessionStart banner prefixed with 🧭 compass emoji for at-a-glance distinction from the resume-interrupted banner

## [0.1.0] — 2026-07-12

### Added
- Persistent startup reminder plugin: SessionStart banner for open items
- CLI (`list` / `add` / `done` / `prune`), skill, and tests
- Store `~/.claude/waypoints.json` lives outside the plugin

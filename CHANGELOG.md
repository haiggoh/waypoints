# Changelog

## [0.20.3] — 2026-11-25 — 🧠 knowledge lines in the SessionStart banner (run-5 §C migration, plan 2026-11-25-memory-plugin-primer Task 4)

- The model-facing `additionalContext` of the SessionStart hook now appends a short
  🧠 knowledge block: when resuming an interrupted session, also check `history.jsonl`
  (sessionId-keyed, epoch-ms timestamps), the session sidecar dir, attachment records and
  the /tmp debug log — the transcript tail alone misses mid-turn-queued prompts, which
  appear as `queue-operation` records, never `type:user` records; session liveness =
  pid AND procStart==ps lstart (pids recycle).
- New `tests/test_memory_primers_20261125.py` pins both trigger tokens in the hook output
  on both lanes (localhost proxy + gateway URL), against a seeded sandbox store.
  RED before the edit (4 failed); mutation-checked (remove one line → red, restore
  byte-identical → green).

## [0.20.2] — 2026-11-25 — triage refuses a target or reason it would silently discard

- Fixed: on an untriaged item, `triage <id> --waiting-on X` (or `--gate-reason Y`) without its
  `--tier` stored nothing, printed `triaged [<id>] untriaged` and exited 0. `set_verdict` now
  refuses it (exit 2, `refused: … pass --tier waiting|gated …`), so the store is left untouched
  and the message names the missing flag. Retargeting an item that is ALREADY waiting/gated
  without repeating its tier still works.
- Tests: 3 CLI-level cases in `tests/test_hook_and_cli.py` (2 red first, both guards
  mutation-checked; 1 positive control for the legitimate tier-less retarget).

## [0.20.1] — 2026-11-22 — waypoints-pane as a markdown command (desktop autocomplete)

- Ship `commands/waypoints-pane.md` so the desktop apps' `/`-autocomplete lists the pane command (previously only the TUI showed mod-registered commands; the desktop suggested only markdown commands). The pane mod still intercepts `command.run` where mods run, so no inference is started there.

## [0.20.1] — 2026-11-22 — Seat-aware pane launch (terminal opt-in, desktop on by default)

- waypoints-pane as a markdown command (desktop autocomplete)

## [0.20.0] — 2026-11-22 — Seat-aware pane launch (terminal opt-in, desktop on by default)

### Changed
- The pane mod now reads `session.start`'s `surface`: in the desktop apps (Claude desktop Code tab, ChatGPT desktop Codex mode where mods run) the panel still opens at launch in every `display` mode; in the terminal TUI it no longer auto-opens — `/waypoints-pane` opens it on demand. Implements Playbook-seat-aware-pane-mod. Engine mod suite: 30 pass incl. a new terminal-opt-in test.

## [0.20.0] — 2026-11-22

- Seat-aware pane launch (terminal opt-in, desktop on by default)

## [0.19.0] — 2026-11-19

### Changed — the pane is opt-in where it is obtrusive; the banner is the default again
- **`display` defaults back to `banner`** (0.17.0 had made `pane` the default). In window mode the pane is now opt-in: it stays closed at launch and the printed banner carries the queue. In the fullscreen layout the docked panel still opens at launch in every `display` mode — the redundancy there is accepted.
- **Seat-driven launch**: every `display` mode opens the pane at session start to learn its seat; under `display=banner` the first render closes it again where the surface will not dock it (inline above the prompt, desktop widget). `display=pane`/`both` keep it at every seat. A manual `/waypoints-pane` open never auto-closes.
- **The inline pane opens collapsed**: the one-line row (`🧭 N open · ▶ A · ⛔ G · ⏳ W`) is the default above the prompt — full only at the dock seat. `Collapse to one line` / press-to-expand (≥ 3 rows) unchanged.
- **The banner carries a switch hint line**: `pane: /waypoints-pane · banner off: ask Claude to set display=pane` (no console command in the user-visible banner, per the standing UX rule).

### Changed — accordion groups, and the full queue
- **Pinned waypoints are now a group** (`▸ 📌 Pinned (N)`), alongside Actionable, Gated, Waiting. **All four groups start collapsed.** `Expand all` opens every row in every group and opens Actionable if closed (never a visible no-op); other groups keep their state, their rows carry the expanded state. `Collapse all` closes rows only, touches no group.
- **No truncation**: the 40-row cap and the viewport-height cut are gone; every row of every open group renders and the pane body scrolls (the engine owns the scroll window). No more "… and N more".

### Tests and tooling
- `tests/mod/register.test.tsx`: 27 engine tests — seat-driven launch (auto-open + first-render close under banner in window mode and on the desktop widget; dock stays; manual open stays), seat-dependent height (dock full / inline one-line), four collapsed groups incl. Pinned, Expand-all/Collapse-all semantics, and a 60-item no-truncation test. Mutation-checked at each step (launch close, compact seat default, accordion handlers, 40-cap all turn their tests red when reverted).
- `tests/test_banner_display_gating.py` / `test_display_setting.py`: default is `banner`; the banner carries the hint line (and no console command).

## [0.18.0] — 2026-11-19

### Removed — the status-line summary and every pane position
- **The status-line summary is gone.** The mod never writes a status line anymore: no one-line band under the prompt, none under the logo notice (0.17.0's `top`/`bottom` positions drew them).
- **`pane-position` is removed entirely** — the setting, the `WAYPOINTS_PANE_POSITION` env var, and the `/waypoints-pane <position>` argument. Claude Code does not let a mod choose where a pane sits, so the argument was a no-op and the setting only an honest mapping; both are dropped. `/waypoints-pane` is now a plain open/close toggle and takes no argument — any argument is refused with a message and nothing is saved. A settings file that still holds `pane-position` loads fine and is ignored with a one-line note (`note: pane-position is no longer used (removed in 0.18.0) and is ignored`); `waypoints.py config get|set|unset pane-position` exits 2 naming the removal.
- The mod's `InfoNotice` hook and the unplaced-summary fallback are removed with them; an unplaced pane just waits and `/waypoints-pane` says `No surface draws the panel here yet (<reason>).`

### Changed — the pane always opens full
- **One-line mode is no longer automatic.** The panel opens FULL at every seat (docked beside the transcript in the fullscreen layout, inline above the prompt, or a desktop widget). `Collapse to one line` still shrinks it to one row and pressing that row expands it back (at least 3 rows); the desktop widget still shows its glance line. In 0.17.0 an inline seat started as that one line.

### Tests and tooling
- `tests/mod/register.test.tsx` rewritten for 0.18.0: 18 behavior tests on the real engine (`claude plugin test .`) — no status-line call ever (launch, toggle, refresh), `/waypoints-pane <arg>` refused with nothing saved, the pane full by default at both inline and dock seats, collapse → one line → expand (rows ≥ 3), widget glance line. Mutation-checked: forcing the compact default to `true` turns the opens-full tests red.
- `tests/test_pane_position_setting.py` now covers the ignored-key note and the exit-2 removal; `tests/test_panel_positions.py` keeps a static no-leftovers guard on the mod source plus the mod-suite parity floor.

## [0.17.0] — 2026-11-19

### Changed — the panel is the default; the banner is off while it shows

- **`display` now defaults to `pane`**: the waypoints panel opens at launch with no slash
  command, and the printed SessionStart banner is off so the list never shows twice (the model
  still receives the full banner as context). **To get the banner back:**
  `waypoints.py config set display banner`.
- **The one-line band above the prompt is gone.** It repeated the counts and sat in the seat
  above the prompt; the panel's one-line mode and the summary line replace it.

### Added — group titles, one-line mode, positions that say what they really do

- **Collapsible group titles**: `▶ Actionable (N)` (open by default), `⛔ Gated (N)` and
  `⏳ Waiting (N)` — press a title to expand or collapse it. Gated and waiting rows show their
  gate reason / what they wait on. One implementation for the terminal and the desktop Code tab.
- **One-line mode**: `Collapse to one line` shrinks the panel to one status-line row
  (`🧭 N open · ▶ A · ⛔ G · ⏳ W`); pressing it expands back to at least 3 rows. Wherever the
  terminal seats the panel above the prompt, it starts as that one line; a desktop widget shows
  it as a glance line.
- **`pane-position`** (`top | bottom | left | right`, default `right`; env
  `WAYPOINTS_PANE_POSITION`; `/waypoints-pane <position>` saves it). Claude Code does not let a
  mod choose a pane's seat, so the values map honestly: `left`/`right` = the panel (docked beside
  the transcript in the fullscreen layout — the engine picks the side, so they behave the same —
  one line above the prompt otherwise); `bottom` = a one-line summary under the prompt (nothing
  can be placed below the statusline); `top` = a one-line summary under the logo notice when one
  shows, else under the prompt. `/waypoints-pane` reports exactly which of these you got;
  with no argument it toggles the full panel for every position.
- A panel no surface can place yet (a narrow terminal at launch) leaves the one-line summary
  under the prompt, so the queue is never silently invisible.

### Tests and tooling

- `tests/mod/register.test.tsx`: 26 behavior tests on the real engine (`claude plugin test .`),
  every UI test run on the terminal and the desktop surface; pytest runs them, so the ship gate
  does. Replaces the text-matching tsx checks (one of which could not fail).
- `tsconfig.json` + `scripts/lay-mod-types.sh` (`--help`): lays the mod API types into the
  gitignored `.claude-plugin/types/` so `tsc -p .` and the TypeScript language server resolve
  `'claude-code'` instead of flagging every JSX line.

## [0.16.0] — 2026-11-18

### Added — Display setting: banner, pane or both

- **New `display` setting** with three values: `banner` (default, the printed SessionStart
  banner exactly as before), `pane`, or `both`. Set it with
  `waypoints.py config set display pane|banner|both`, through the interactive menu's `settings`
  group, or with `WAYPOINTS_DISPLAY` (env > settings file > default). `config get display --raw`
  prints just the value.
- **`pane` mode** drops only the printed banner (`systemMessage`); the model still receives
  the full banner as context, plus a line saying the user sees the queue in the pane.
- **Pane and band mod** (`hooks/register.tsx`, bundled; Claude Code terminal and the desktop
  app's Code tab, on builds that support mods): a side pane with collapsible rows (press a row
  to show its summary bullets and id; Expand all / Collapse all) and a one-line band above
  the prompt with the counts. Read-only: it reads the queue only through
  `waypoints.py list --open --json`, refreshes every 60 seconds and after any Bash call that
  mentions `waypoints`. `/waypoints-pane` opens the pane at any width; a pane the mod opens by
  itself draws from 144 terminal columns. Builds without mod support ignore the mod; keep
  `display` at `banner` there.
- **`pane-style` setting** picks the collapsed-row look: `plain` (default: chrome-free, dim rows), `native`, `secondary`, `links` (markdown links, no boxes), `dark` (near-black rows) or `static` (text rows plus the shared Expand/Collapse buttons). A desktop draws every `Button` natively, so the looks differ in structure, not only colour. `/waypoints-style` previews all six with your own waypoints; set one with `waypoints.py config set pane-style <name>` (env `WAYPOINTS_PANE_STYLE`, also in the menu).
- `portable/` rebuilt and now carries the mod and its types.

## [0.15.3] — 2026-11-16

### Fixed — pyright clean (0 errors repo-wide)

- `bin/waypoints.py`: removed the 14 obscured duplicate function definitions
  (a copy-pasted block at old lines 115–709; the later definitions were already the
  live ones, and all 13 helpers were AST-verified byte-identical, `main` differed but
  was equally superseded — zero behavior change). Fixed the `--set-point` optional
  narrowing with an explicit `assert`.
- `waypoints_core.py`: guard the `fcntl.flock` unlock behind `fcntl is not None`
  (the import is guarded for non-POSIX); `set_pinned(reason=...)` annotated
  `str | None` and the pin_reason assignment uses `(reason or "").strip()`;
  `edit_item` asserts the summary argument is a list/tuple before `list()`.
- `tests/`: narrow optional returns with explicit `assert ... is not None` before
  subscripting (`get_item`, `edit_item`, `set_priority`, `_backup_before_write`,
  `re.search(...).group`), renamed an ambiguous `l` loop variable (E741).
- `portable/` rebuilt (build-portable.py) so the shipped copy is byte-current.
- Gates: pyright 0 errors (pytest venv pythonpath), `pytest -n auto` 454/454.

## [0.15.2] — 2026-11-15

### Fixed — Phase 5 Wave C: waypoints writer safety

- **Single-writer lock.** `waypoints_core.store_lock()` takes an advisory fcntl lock on
  `<store>.lock` around every mutating command (dispatch choke point in main); it is
  cross-process, re-entrant within one process (the menu re-enters main per action), and
  refuses loudly (StoreBusy) past a timeout instead of stalling. Read-only commands never
  take it. Without it, two concurrent sessions could lose an update (read-modify-write race).
- **Corrupt archive is refused, not silently empty.** `load_archive()` is strict by
  default now: an existing but corrupt archive is quarantined and raised as StoreCorrupt
  (same as the live store), and `archive` commands report it and exit 2. Cosmetic readers
  (the resolve promotion check) pass strict=False explicitly. Before, a corrupt archive
  read as "no archived items".
- Re-derived and already-resolved: the never-hand-edit-JSON rule is stated consistently and
  no code path bypasses the module; backup/journal/atomic-write were already in place.
- New tests/test_writer_safety.py pins lock serialization across processes, re-entrancy,
  read-only commands running lock-free, mutating commands waiting, and the corrupt-archive
  refusal. Suite 454/454.

## [0.15.1] — 2026-11-14

### Added — Phase 2: committed portable package + published record schema (C1/C2/C4)

- `scripts/build-portable.py` generates the committed `portable/` package: same-name
  manifest, skill + slash command (CLI refs rewritten `bin/` -> `scripts/`), the
  SessionStart hook, and the CLI moved to `scripts/waypoints.py` with its import closure
  (`waypoints_core.py`, `waypoints_menu.py`, `__init__.py`) copied to the portable ROOT
  where the CLI's sys.path insert looks for them. Emits `PORTABLE-BUILD.json`
  (haiggoh-portable-build/1) and a deterministic `dist/waypoints-portable.zip`.
- `docs/record-schema.md` publishes the C4 record schema (store/item/change fields,
  single-writer + atomic-write transport rules, absence-is-not-deletion).
- `tests/test_portable.py` pins freshness, same-name manifest, no `bin/`, no stale refs,
  closure completeness, C2 schema, deterministic side-effect-free zip — and a FUNCTIONAL
  test that runs the portable CLI against a WAYPOINTS_FILE-isolated store (a smoke run
  without that override once wrote a test item into the real store; cleaned via the CLI).

## [0.15.0] — 2026-11-14

### Changed — 🧭 shorter banner: pinned section + user-settable limits

- The banner now lists **5** unpinned items by default (was 10).
- 📌 Pinned items are their **own section**, listed first with their own cap (default 5), so
  five pins can no longer fill every slot and hide the unpinned list. Pins beyond the cap are
  counted (`… and N more pinned`), like the open residue.
- Pin reasons are trimmed to **2 lines** by default, ending `…`; the compact-mode note says so,
  and `show <id>` has the full reason.

### Added — banner settings (`config`, menu **settings** group)

- `waypoints.py config get [key] | set <key> <value> | unset <key>` for `banner-items`,
  `banner-pinned` and `pin-lines` (a number, or `full`). Persisted in
  `~/.claude/waypoints-settings.json` beside the store (follows `$WAYPOINTS_FILE`).
- Resolution is env var > settings file > default; new env overrides
  `$WAYPOINTS_BANNER_MAX_PINNED` and `$WAYPOINTS_BANNER_PIN_LINES` join the existing
  `$WAYPOINTS_BANNER_MAX_ITEMS`. A set-but-invalid value is refused loudly (CLI exit 2; the
  SessionStart banner is replaced by an error naming the setting), never silently defaulted.
- The interactive menu gains a **settings** group: show all settings with their source, and
  change each one (current value and source shown before the prompt).
- `config` runs before the store is loaded, so it works even when the store is damaged.

## [0.14.4] — 2026-11-06

### Added — 🧭 native date/recency filter on `list` and `search`

- `--since YYYY-MM-DD` and `--age Nd` (mutually exclusive) filter by the item's `created`
  date, composing with the views, `--open`, `--repo`, paging and `--json` (whose payload
  records the active filter like `--repo`'s). Done items stay hidden without `--all`, as
  always. `--age` resolves on the `WAYPOINTS_TODAY`-overridable clock, so replays and
  tests stay deterministic. Malformed values exit non-zero naming the flag.
  Documented in the usage block and SKILL.md, so "waypoints from the last 7 days" works
  as a plain prompt via `waypoints.py list --open --age 7d`.

## [0.14.4] — 2026-11-06

- (release notes go here)

## [0.14.3] — 2026-11-03

### Added — 🧭 branded menu header (menu-restyle batch, user spec 2026-11-03)

- The interactive selector (`waypoints menu`; bare `waypoints` on a TTY) opens with a
  csl-style header — 🧭 Waypoints / subtitle / `=` rule — before the action prompt, so
  the menu names its plugin the way the csl picker and get-haiggoh-menu do. Pinned by
  `tests/test_menu.py` (exact block + ordering against the prompt line), mutation-checked.

## [0.14.2] — 2026-10-31

### Changed — description rewritten to current capabilities (rtc-1.0.0 plan, Part B2)

- plugin.json description set to the user-approved text
  (2026-10-31-approved-plugin-descriptions.json); identical text lands in the
  get-haiggoh catalog in the same rollout. Version 0.14.1 → 0.14.2.

All notable changes to `waypoints` are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.14.1] — 2026-10-31

### Changed — reference-implementation branding completed (emoji rollout, Task 15)

- `commands/waypoints-gated.md` now instructs the reply to lead with `🧭 waypoints:`
  (the SessionStart banner branding was already pinned by test_hook_and_cli.py). New
  tests/test_command_branding.py pins the instruction; mutation-checked.
- Version 0.14.0 → 0.14.1.

## [0.14.0] — 2026-10-28

### Added — `repos`: a repo/project category per item, and `--repo` filters for it

- Items may carry `repos`, a LIST of bare repo directory names: `add --repo NAME` (repeatable),
  `edit <id> --repo NAME` (APPENDS and dedupes — re-adding is a safe no-op, the property a
  backfill sweep needs), `edit <id> --clear-repo` to remove it. Absent by default, never
  defaulted, no migration: an item nobody categorises is byte-identical to a pre-0.14.0 item.
- Malformed values are REFUSED at write, never repaired — empty/blank names, surrounding
  whitespace (refused rather than stripped), `/`-paths (the value is a directory NAME, not a
  path), non-strings, duplicates within one write — because the value is the join key for the
  `--repo` filters and the changelog sweep, and a typo'd entry would silently place an item
  outside every filter, reading as "no work happened". The READ side defends instead of raising
  (the waiting-target precedent): a hand-edited legacy string coerces to one repo, anything
  unwritable degrades to `[]`, so one malformed field cannot break every view.
- `list --repo NAME` matches when NAME is ANY element (an umbrella item surfaces under each repo
  it names), composes with the verdict views and `--open`, survives `--json` (the payload gains a
  `repo` key naming the filter and narrows `items`; `view` stays null rather than claiming
  "open"; counts still describe the whole store), and is ECHOED by pagination — a quoted,
  re-runnable `--repo` value in the printed next-page command. `search --repo NAME` scopes every
  pool. Both NAME the filter in their empty-result output, so an empty result cannot read as
  "no waypoints exist".
- The banner gains a conditional tag: COMPACT mode only, and only when the LISTED items span
  2+ distinct repos, each repos-carrying title gets ` [repo]` (multi-repo: ` [first+N]`). The tag
  counts against `BANNER_TITLE_MAX` — the title is trimmed, never the tag. Every other banner
  renders BYTE-IDENTICAL to 0.13.0, pinned by tests that render repos-carrying items against
  their repos-stripped twins and demand exact equality.
- No LIST_CONTRACT bump: `repos` in `list --json` is purely additive (null when unset), per the
  bump policy the contract's own docstring states.
- Also in this release: the test suite's store tripwire — an autouse fixture points
  `$WAYPOINTS_FILE`/`$WAYPOINTS_CLAUDE_DIR` at tmp_path for EVERY test, so a test that forgets
  its env can no longer reach the live store (the fail-open hazard `test_menu.py` documented).
- Tests: 47 new across core, CLI and banner; every new guard mutation-verified (break → red →
  restore → green), including two vacuous tests the mutation pass itself caught and strengthened.

## [0.13.0] — 2026-10-03

### Added
- A `shortcuts` file at the plugin root declares `waypoints`, so `get-haiggoh` (0.8.0 or later)
  can put it on your own shell `PATH` through a version-independent shim. The command itself and
  the Bash-tool `PATH` entry Claude Code already adds are unchanged.

## [0.12.0] — 2026-10-02

### Added — `add --id <slug>`: choose the id up front

- Ids are slugged from titles, so a cross-reference (`--waiting-on`, a plan's link) written before
  `add` runs has to guess the slug — and dangles when the guess is wrong. Measured 2026-09-24: five
  execution plans had every reference `sed`-rewritten after the fact.
- `waypoints.py add "Title" --id my-slug` uses the id verbatim. It must be kebab-case
  (`[a-z0-9]+(-[a-z0-9]+)*`, exit 2 otherwise) and is **refused** (exit 1) if any open **or archived**
  item already has it — no silent `-2` suffix, which would defeat the pre-written link, and an
  archived id stays reserved because `reopen` would otherwise resurrect a duplicate.
- Skill: documents the create-then-link order for linking several new items.
- Tests: 4 new (verbatim id, 7 malformed shapes, open collision, archived collision); the validator
  and the archive half of the collision check were each mutation-tested (both caught).

## [0.11.0] — 2026-10-02

### Added — audit-loose-ends integration (`scripts/waypoint-reconcile.py`)

- **New `scripts/waypoint-reconcile.py`**: deterministic waypoint reconciliation that outputs a fixed-format action list (release, stale, prune). Integrates with `audit-loose-ends` wrap-up workflow.
- **Release waiting items**: `promote_landed_waiting()` releases items whose targets have landed (`waypoints.py resolve` equivalent).
- **Detect stale waiting items**: identifies waiting items whose targets no longer exist (renamed/mistyped).
- **Prune done items**: `prune()` moves completed items to archive, keeping live store clean.
- **CLI contract**: `--session`, `--transcript`, `--repo`, `--json`, `--dry-run`, `--apply` flags. Default dry-run; `--apply` executes.
- **`--from-scan` integration**: `--session <id> --from-scan --repo <dir>` runs `audit-scan.py --repos-only --session <id> --all-projects` to discover touched repos + transcript, then runs all checks.

### Added — `audit-scan.py` repo tracking enhancements

- `--repos-only` flag prints one absolute repo path per line (consumed by verify-state.py `--from-scan`).
- `--json` output includes `"repos": sorted(s.repos)`.
- Tracks repos from `cd X && git ...` and `git -C X ...` commands in transcript.

### Changed — `verify-state.py` exit code contract

- Exit code 0 = CLEAN (no FAIL), 1 = NOT CLEAN (≥1 FAIL), 2 = usage error. WARN/UNKNOWN never change exit code.
- The model must now relay the `VERDICT:` line verbatim; may not author its own verdict.

### Added — waypoint integration to audit skill

- Skill Step 0 now runs `verify-state.py --from-scan` and relays its `VERDICT:` line verbatim.
- Harvest-lessons runs by default on wrap (opt-out with `AUDIT_HARVEST=0` or "no harvest").

## [0.10.0] — 2026-09-21

### Changed (BREAKING) — `--point` now APPENDS; only `--replace-points` discards

`edit --point` used to REPLACE every bullet. It was guarded by a refusal plus a longer flag
(`--add-point`) for the safe path — but that left the **destructive** operation holding the
name people reach for first, which is the defect rather than the fix: a guard that says "no,
type more" still teaches the wrong verb.

- `--point` and `--add-point` are now the **same append**. Combining them is no longer an
  error, since they no longer mean opposite things
- `--replace-points` is the only destructive path and must be passed explicitly; it still
  echoes what it discarded
- **new** `--set-point N "TEXT"` rewrites one bullet in place, and `--rm-point N` removes one
  (1-based, as `show` numbers them). Append-only would have made a typo permanent, so removing
  `--point` outright was rejected: the answer to "this one bullet is wrong" must not be "retype
  all of them". An out-of-range index fails loudly rather than no-opping or clamping

### Added (BREAKING) — `done` now REQUIRES evidence of what was achieved

Closing an item silently is how a store fills up with ✓ marks that no longer explain
themselves. `done` now refuses unless the close records the work:

- `--evidence "…"` — what was achieved, **pointing at something concrete**: a commit sha,
  `file:line`, a version/tag, a test count, a command, a URL, or an issue/PR. Recorded as a
  `CLOSED:` bullet, so the archive says *why* each item closed
- `--no-evidence "REASON"` — closes without work evidence (duplicate, superseded, obsolete,
  mistake), recording the reason. An escape hatch is **required**: without one the gate would
  block legitimate closes and get worked around by hand-editing the store
- the interactive menu prompts for evidence, so the menu never builds a command the CLI refuses
- `rm` and `toggle` are deliberately **not** gated — they tidy, they do not claim completion

A refusal rather than a nudge on purpose: prose in a skill or banner can be skipped, a non-zero
exit cannot. And the check is for a **reference**, not a length — a minimum-characters rule is
satisfied by padding, so it would only *look* like it enforced "real work or substantial
existing evidence it can point to".

### Migration

Callers passing a bare `waypoints.py done <id>` must add `--evidence` or `--no-evidence`. The
banner, skill and README now teach the new form. Anything that closes items programmatically
(e.g. an end-of-session reconciliation) needs the same update.

## [0.9.0] - 2026-09-10

### Added - `waypoints search`: search the STORE, not a rendered view

Grepping the list view is not searching the store, and the failure is silent. The compact view
truncates titles at 96 characters, so a `waypoints list | grep -i spinner` returns nothing when the
match sits past the ellipsis - indistinguishable from a genuine absence. **That happened:** asked
whether an idea was already tracked, a session grepped the list, got nothing, and filed a
**duplicate** of an item that had been tracked for two weeks under a title whose matching words fell
past the cut. Before this, not one of 21 subcommands searched, and `list` had no `--search` either.

`waypoints search "keyword"` matches against the **title, every summary bullet, and `detail`** - the
last being where continuity dumps live, invisible to every view except `show`. Design choices that
follow directly from the bug:

- **Matching text prints UNTRUNCATED.** A search command that truncated would rebuild the very bug
  it fixes; its own output has to be safe to grep and safe to trust.
- **Exit `0` on a hit, `1` on a miss**, so it composes in a script instead of requiring the caller
  to parse prose.
- **A miss names the scope it searched** and points at the flag that widens it. An empty result that
  did not say where it looked would repeat the original false negative in a new place.
- **The archive is searchable** (`--archived`, or `--all` for both) because *"was this **ever**
  tracked?"* is precisely the question that failed, and archived items are what answer it.
- `--case`, `--regex` and `--ids-only` for scripted use. A bad `--regex` exits `2` with the error.

Read-only by contract: no journal entry, no snapshot, no mtime change on the store.

**Reachable from the selector too**, not just as a typed flag - the bare-`waypoints` command menu
gains a `search` action in its `look` group. A search you can only run by already knowing the flag
does not reach the person the incident happened to, which is the case the menu exists for. The menu
still only composes an argv for `main()`, so this is a new action entry and no new store logic.

Tests: 7 CLI checks and 2 menu checks. The first pins the **originating incident** by asserting both
halves - that grepping the rendered view still misses (a property of a display, not a bug), and that
`search` finds it - because a test asserting only the second would pass against a view that never
truncated and so would not pin what went wrong. It also self-checks that the keyword really does sit
past the cap, so it fails loudly rather than silently stopping to exercise the incident.
Mutation-tested 5/5: title-only search, truncated output, always-exit-0, ignoring `--archived`, and
case-sensitive-by-default are each caught.

## [0.8.0] — 2026-09-07

### Added
- **An interactive command selector, opened by a bare `waypoints` on a terminal.** The store must
  be maintained through the CLI and never by hand, but the commands needed for routine upkeep are
  not the ones anyone remembers: "add a bullet" is `edit <id> --add-point`, and reaching for an
  editor because you cannot recall a flag is how the store was lost on 2026-09-03. The selector
  covers the whole surface — 21 actions across look / capture / close / triage / maintain — so
  upkeep stays possible from a bare terminal with no Claude Code session available at all.
  - **It never touches the store.** Every action composes an argv and hands it to the ordinary CLI
    dispatch, so guards, confirmations, journal entries and the backup ring behave exactly as if
    the command had been typed, and the journal records the real command rather than "menu". A
    selector that reimplemented even one mutation would be a worse bug than the one it prevents.
  - **It echoes the command before running it** — for teaching, not confirmation. Each use shows
    the real invocation, so a reader graduates off the menu instead of depending on it.
  - Items are picked **by number** from a list rather than by re-typing a slug id, which is where
    a wrong-item mutation comes from on a surface with no autocomplete. Typing an id still works,
    and is necessary past the pick limit.
  - `add-point` is offered under **the name people actually reach for**, though no such subcommand
    exists. It composes `--add-point` (append), never `--point` (which replaces every bullet).
  - Safety is shaped per action: irreversible-ish prompts default to **no** so a hurried return is
    never the destructive answer; `--replace-points` is shown as destructive and needs its guard
    flag plus a confirmation; `prune` reports the count it would move first, since its effect is
    otherwise invisible until afterwards; and `recover`, which replaces the whole store file, only
    ever offers its read-only `--list` from here.
  - A command that exits non-zero ends the **action**, not the session. Being dropped back to the
    shell over one mis-typed date is the friction this exists to remove.
- `waypoints menu` runs the selector explicitly, and says why when it cannot.

### Changed
- **A bare `waypoints` on a terminal now prints the dashboard and then the selector.** The
  dashboard is the context you need in order to choose an action, so the selector adds to it rather
  than replacing it — but its trailing "Commands:" hint block is suppressed when the menu is about
  to list the same commands as a numbered menu, which would otherwise say everything twice and push
  the prompt off a short terminal. With no menu following, the hints print exactly as before.
- The README no longer says the store can be edited directly — it contradicted rule zero on the
  page that introduces the CLI.

### Unchanged on purpose
- **Non-interactive behaviour is byte-identical.** The selector is gated on **both** stdin and
  stdout being a TTY, so a pipe, a script or a hook running bare `waypoints` gets the same plain
  dashboard it always did. Blocking any of those forever on input that will never arrive would be a
  far worse regression than a missing convenience. `waypoints dashboard` remains the explicit
  non-interactive form, and `WAYPOINTS_NO_MENU=1` is the opt-out for a terminal that does not want
  the prompt.

### Tests
- `tests/test_menu.py` — 48 tests in two halves. Unit tests drive the loop with a fake dispatch and
  assert the **argv** a keystroke sequence composes, which is the contract that matters. A **pty**
  test runs the real launcher under a pseudo-terminal, because every non-pty invocation takes the
  other branch by definition, so a suite without one would assert the fallback forever and never
  prove the feature runs. It caught a real wiring bug (`c.load` does not exist) that all 45
  composition tests passed straight over.
- Store-touching tests assert the sandbox **by outcome** — the live store's mtime is untouched —
  because `WAYPOINTS_FILE` fails open, and a typo'd variable name writes to the real store.
- Mutation-tested 12/12, including the TTY gate, the `--add-point`-not-`--point` composition, the
  `recover` read-only routing and the no-by-default confirmations.

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

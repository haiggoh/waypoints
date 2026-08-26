---
name: waypoints
description: Use to manage the user's persistent open-items reminder ("waypoints") — the SessionStart banner that lists unfinished tasks/follow-ups and stays until each is marked done. Invoke when adding a follow-up you want surfaced next session, marking one done, listing what's open, or reconciling the store during a session wrap-up. Also invoke on generic open-item language even when the user doesn't say "waypoint" — "add this to my to-do list", "track this as a loose end", "remind me about X next time", "don't let me forget this", "keep this on my radar". Also read this when you see the "waypoints:" startup banner and want to know how to act on or clear its items.
---

# waypoints — persistent open-items reminder

A "waypoint" is a point still **ahead** of you on the journey — an unfinished task/follow-up you
want surfaced at the start of every session **until you reach (complete) it**. Unlike Claude Code's
native *checkpoints* (`/rewind` — an undo/restore snapshot you go *backward* to), waypoints are
**forward-looking** and **persist until marked done**. And unlike anything that detects an
*accidentally* cut-off session — which self-denoises once you've had a clean one — waypoints track
**deliberate** open items and do **not** self-denoise.

## The store

`~/.claude/waypoints.json` (override with `$WAYPOINTS_FILE`), a user file **outside** this plugin so
updates never touch it:
```json
{ "version": 1, "items": [
  { "id": "kebab-slug", "title": "one-line headline (banner)",
    "summary": ["key point", "another"], "detail": "full continuity dump (on-demand only)",
    "surface_on": "YYYY-MM-DD or null", "created": "YYYY-MM-DD", "done": false } ] }
```
`surface_on` is the **earliest** date an item appears — NOT an expiry. Undated items show every
session; dated ones show on and after that date, and both persist until done.

**Optional verdict fields.** An item may also carry `tier` (`do-now` | `heavy` | `gated`) and, when
gated, `gate_reason`. Both are **absent unless set** — an untriaged item has neither key, so nothing
written before verdicts existed needs migrating, and `untriaged` stays a real third state rather
than a silent synonym for "actionable". An item nobody has assessed is not thereby known to be
unblocked.

## Reading the queue programmatically

`waypoints.py list --json` emits a **documented contract** — use it instead of parsing the store
file, which is free to change shape:

```json
{ "contract": 1, "generated": "YYYY-MM-DD",
  "counts": { "total": 0, "open": 0, "done": 0, "surfaceable": 0,
              "gated": 0, "actionable": 0, "untriaged": 0 },
  "items": [ { "id": "…", "title": "…", "summary": [], "detail": "…",
               "created": "YYYY-MM-DD", "surface_on": null, "done": false, "priority": 0,
               "surfaceable": true, "tier": null, "gate_reason": null } ] }
```

- `contract` versions the **output**, independently of the store's `version`.
- `tier`/`gate_reason` are always present here and `null` when unset — a consumer never has to tell
  a missing key from a null one, even though the store itself omits them.
- `gated + actionable + untriaged == open`, so you can verify nothing was dropped.
- A filtered view adds `"view"` and narrows `items`, but `counts` still describe the **whole**
  store — a subset should never be mistakable for the total.

**Symmetric views, equal citizens:** `--gated`, `--actionable`, `--untriaged` (add `--open` to drop
done items). None is the default and none is privileged. In particular the store does **not** sort
gated items last: a gate reason is a question you owe yourself, and burying it would assume some
*other* tool is consuming the rest of the list.

**Three tiers, so the banner stays tidy without discarding context:** `title` (headline, always
shown) + `summary` (a few short bullets, shown under the title) + `detail` (the full dump, **never**
in the banner — read on demand with `show`). Keep `title` short and push specifics into `--point`
bullets; put the long "reconstitute this after a /clear" context in `--detail`. `id` and `created`
are immutable across edits — a stable id is why `edit` exists.

## Managing waypoints

The user manages waypoints **by talking to you** — they do not type a console command. You add and
close items on their behalf and surface the open ones in conversation. Use the bundled CLI:
```sh
waypoints.py list                       # Claude Code v2.1.91+ puts the plugin's bin/ on the Bash-tool PATH
waypoints.py list --json                # the documented contract above (for reading, not parsing the store)
waypoints.py list --gated|--actionable|--untriaged [--open]   # symmetric views
waypoints.py triage <id> --tier do-now|heavy|gated [--gate-reason "…"] | --clear
waypoints.py add "Title" [--point "key pt" ...] [--detail "…"] [--surface-on YYYY-MM-DD]
waypoints.py edit <id> [--title "…"] [--add-point "…" ...] [--clear-summary] [--detail "…"] [--surface-on YYYY-MM-DD] [--clear-surface-on]
#   --add-point APPENDS a bullet, keeping the existing ones — this is what you want when recording new information.
#   --point REPLACES the entire bullet list. It is REFUSED when the item already has bullets unless you
#   also pass --replace-points; the refusal prints the bullets it would have discarded.
waypoints.py show <id>                  # print title + summary + full detail (the "pick it up" view)
waypoints.py done <id> [--as "outcome"] # mark done; --as rewrites the title to the resolution
waypoints.py reopen <id>                # undo done (inverse of `done`)
waypoints.py toggle <id>                # flip an item's done state in one call
waypoints.py priority <id> <level>      # int; higher sorts earlier in the banner (default 0)
waypoints.py reorder <id> <position>    # move to an explicit 0-based position in the list
waypoints.py prune                      # drop done items
```
Prefer **`edit`** to fix or enrich an existing item — it keeps the `id` and `created`. Never
`done`+re-`add` to "update" (that regenerates the id, drops `created`, and leaves a false ✓). When
picking an item back up, `show <id>` to read its full `detail` (the banner only carries title +
summary bullets). If the user says "actually that's not done" (marked done in error, or the fix
didn't hold), use `reopen` rather than re-`add`ing — same reason as `edit`: keeps the id.
`toggle` is a one-call convenience when you don't know or care which state it's currently in.
Use `priority` when an item should consistently jump the queue (urgent/blocking); use `reorder`
only for a one-off manual ordering that doesn't fit the priority model.

**Record a blocker as a blocker.** When you find that an item can't move — it needs a decision only
the user can make, a credential, them to be physically present, or an external system to be up —
`triage <id> --tier gated --gate-reason "<what it's waiting on>"` instead of leaving it looking
actionable. Write the reason as *the thing that would unblock it*, not as a restatement of the task
("needs the user to choose between A and B", not "blocked"). When the blocker clears, retier it
(`--tier do-now`) — that drops the stale reason in the same call. Past a few gated items the banner
collapses them into one counted line with `/waypoints-gated` to expand, so the reason is what makes
that line worth expanding.

**Resolve before you close.** When a waypoint's title reads as an open question or pending decision
("Confirm X works", "Decide + open the PRs", "Test whether Y…"), a bare `done` leaves the ✓ next to
an unanswered question — the record then contradicts itself and the *outcome* is lost. Close it with
`done <id> --as "what actually happened"` so the title states the resolution in one atomic call
(keeps the `id`/`created`, no separate `edit` needed). Plain task imperatives ("Fix the bug",
"Publish the PR") read fine as done and need no `--as`. If you `done` an open-question title without
`--as`, the CLI prints a non-blocking ⚠️ reminder with the exact `--as` re-run — heed it rather than
leaving the stale question closed.
The bare command is **`waypoints.py`** — that's the shipped filename; note the `.py` (bare
`waypoints` will not resolve). If it isn't on PATH (older Claude Code), fall back to
`python3 "$CLAUDE_PLUGIN_ROOT/bin/waypoints.py"` while a skill/hook is running, or edit
`~/.claude/waypoints.json` directly.

## When to act

- **You see the `waypoints:` startup banner** → those are the user's open items. Help progress the
  relevant one(s); when one is genuinely finished, mark it done (`waypoints.py done <id>`).
- **You create a follow-up** the user should not lose (a deferred task, a blocked item, a "later"
  decision) → `add` it, with a `--surface-on` date if it only becomes relevant later.
- **Session wrap-up** → reconcile the store *against itself*: `done` what's finished, `edit` titles
  that no longer describe reality, `add` follow-ups this session created, and re-`triage` anything
  whose blocker has cleared. The question this answers is **"is my queue accurate?"**

  **Scope note:** this is store-local. Scanning *other* surfaces — memories, project notes, plan
  files — for pending markers that were never tracked here is a different job: it belongs to
  whatever cross-surface reconciliation discipline you have, not to this store. Keeping the two
  apart is deliberate; a queue that also claims to audit everything else ends up doing both badly.
  If nothing in your setup owns that sweep, do it deliberately and feed the results in via `add`.

## Keep it the single source of truth for the *reminder*

When an open item also has a detailed memory (the how-to, rationale), keep the **reminder** in the
waypoints store and the **detail** in the memory, with the store item's `detail`/title pointing at
the memory — don't duplicate the full content in both.

## Branding (🧭)

This feature has a visual identity — the compass **🧭**. When you refer to the waypoints *feature*
in prose, mark genuine references to it with 🧭 on the first/prominent mention in a message (not
incidental uses of the word "waypoint"). The SessionStart banner leads with 🧭 for the same reason,
and the model-facing context re-states this each session, so the mark ships with the plugin for
every user rather than depending on any one machine's config.

## Disabling

It's a plugin — if the banner is ever too naggy, disable or uninstall it via `/plugin`. Your store
file is left intact.

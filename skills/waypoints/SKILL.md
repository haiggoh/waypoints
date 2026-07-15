---
name: waypoints
description: Use to manage the user's persistent open-items reminder ("waypoints") — the SessionStart banner that lists unfinished tasks/follow-ups and stays until each is marked done. Invoke when adding a follow-up you want surfaced next session, marking one done, listing what's open, or reconciling the store during a session wrap-up. Also invoke on generic open-item language even when the user doesn't say "waypoint" — "add this to my to-do list", "track this as a loose end", "remind me about X next time", "don't let me forget this", "keep this on my radar". Also read this when you see the "waypoints:" startup banner and want to know how to act on or clear its items.
---

# waypoints — persistent open-items reminder

A "waypoint" is a point still **ahead** of you on the journey — an unfinished task/follow-up you
want surfaced at the start of every session **until you reach (complete) it**. Unlike Claude Code's
native *checkpoints* (`/rewind` — an undo/restore snapshot you go *backward* to), waypoints are
**forward-looking** and **persist until marked done**. Unlike `resume-interrupted` (which flags a
cut-off session and self-denoises after a clean one), waypoints do **not** self-denoise.

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
waypoints.py add "Title" [--point "key pt" ...] [--detail "…"] [--surface-on YYYY-MM-DD]
waypoints.py edit <id> [--title "…"] [--point "…" ...] [--clear-summary] [--detail "…"] [--surface-on YYYY-MM-DD] [--clear-surface-on]
waypoints.py show <id>                  # print title + summary + full detail (the "pick it up" view)
waypoints.py done <id>                  # marking done removes it from the banner
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
The bare command is **`waypoints.py`** — that's the shipped filename; note the `.py` (bare
`waypoints` will not resolve). If it isn't on PATH (older Claude Code), fall back to
`python3 "$CLAUDE_PLUGIN_ROOT/bin/waypoints.py"` while a skill/hook is running, or edit
`~/.claude/waypoints.json` directly.

## When to act

- **You see the `waypoints:` startup banner** → those are the user's open items. Help progress the
  relevant one(s); when one is genuinely finished, mark it done (`waypoints.py done <id>`).
- **You create a follow-up** the user should not lose (a deferred task, a blocked item, a "later"
  decision) → `add` it, with a `--surface-on` date if it only becomes relevant later.
- **Session wrap-up** → reconcile the
  store: `done` finished items, `add` newly-created follow-ups, and sweep memories/project-notes for
  pending markers (`⏳`, `REMAINING`, `TODO`) not yet tracked and add them. This memory-scan
  "hybrid" discovery is deliberately done **here, agent-side** — never in the startup hook — so the
  banner stays precise and free of false positives.

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

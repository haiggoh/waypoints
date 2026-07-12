---
name: waypoints
description: Use to manage the user's persistent open-items reminder ("waypoints") — the SessionStart banner that lists unfinished tasks/follow-ups and stays until each is marked done. Invoke when adding a follow-up you want surfaced next session, marking one done, listing what's open, or reconciling the store during a session wrap-up. Also read this when you see the "waypoints:" startup banner and want to know how to act on or clear its items.
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
  { "id": "kebab-slug", "title": "one-line (shown in banner)", "detail": "context / pointer",
    "surface_on": "YYYY-MM-DD or null", "created": "YYYY-MM-DD", "done": false } ] }
```
`surface_on` is the **earliest** date an item appears — NOT an expiry. Undated items show every
session; dated ones show on and after that date, and both persist until done.

## Managing waypoints (CLI)

Run the bundled CLI (`$CLAUDE_PLUGIN_ROOT/bin/waypoints.py`), or edit the JSON directly:
```sh
python3 "$CLAUDE_PLUGIN_ROOT/bin/waypoints.py" list
python3 "$CLAUDE_PLUGIN_ROOT/bin/waypoints.py" add "Title" [--detail "…"] [--surface-on YYYY-MM-DD]
python3 "$CLAUDE_PLUGIN_ROOT/bin/waypoints.py" done <id>
python3 "$CLAUDE_PLUGIN_ROOT/bin/waypoints.py" prune      # drop done items
```
Marking an item **done** is what removes it from the banner.

## When to act

- **You see the `waypoints:` startup banner** → those are the user's open items. Help progress the
  relevant one(s); when one is genuinely finished, mark it done (`waypoints done <id>`).
- **You create a follow-up** the user should not lose (a deferred task, a blocked item, a "later"
  decision) → `add` it, with a `--surface-on` date if it only becomes relevant later.
- **Session wrap-up** (the CLAUDE.md "Wrapping up — reconcile checkpoints" rule) → reconcile the
  store: `done` finished items, `add` newly-created follow-ups, and sweep memories/project-notes for
  pending markers (`⏳`, `REMAINING`, `TODO`) not yet tracked and add them. This memory-scan
  "hybrid" discovery is deliberately done **here, agent-side** — never in the startup hook — so the
  banner stays precise and free of false positives.

## Keep it the single source of truth for the *reminder*

When an open item also has a detailed memory (the how-to, rationale), keep the **reminder** in the
waypoints store and the **detail** in the memory, with the store item's `detail`/title pointing at
the memory — don't duplicate the full content in both.

## Disabling

It's a plugin — if the banner is ever too naggy, disable or uninstall it via `/plugin`. Your store
file is left intact.

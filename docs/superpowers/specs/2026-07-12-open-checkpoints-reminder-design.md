# open-checkpoints — persistent open-items startup reminder — Design

**Date:** 2026-07-12
**Status:** Approved (design)
**Author:** Claude (with user)

---

## 1. Overview

A Claude Code plugin that surfaces **open tasks / to-dos / checkpoints** as a SessionStart banner —
the same `additionalContext` banner mechanism the `resume-interrupted` plugin uses — but as a
**distinctly separate mechanism** with two crucial differences:

1. It **does not self-denoise.** resume-interrupted goes quiet after a clean session; this one
   **persists until each item is explicitly marked done**.
2. It reads an **explicit store** of open items (not session transcripts), maintained by the CLAUDE.md
   "wrap up" rule (and directly by the user).

It must **not interfere** with resume-interrupted (separate plugin, separate store, separate banner
label; both SessionStart hooks fire independently). It is **optional** — deactivating = disabling or
uninstalling the plugin via `/plugin`.

## 2. Non-goals (YAGNI)

- No modification to resume-interrupted.
- No scanning of memories/transcripts *inside the hook* (that would reintroduce false-positive
  nagging). Discovery from memory is an agent-side wrap-up action (see §6).
- No GUI/TUI; management is a small CLI + direct file edits.
- No cross-machine sync of the store (it's a local user file).

## 3. Architecture

Three units, each independently understandable/testable:

- **Store** — `~/.claude/open-checkpoints.json`, a user-level file **outside** the versioned plugin
  (so plugin updates/reinstalls never wipe it). Schema:
  ```json
  {
    "version": 1,
    "items": [
      {
        "id": "kebab-slug",
        "title": "one-line summary (shown in the banner)",
        "detail": "optional longer context / pointer to a memory or repo",
        "surface_on": "YYYY-MM-DD or null",
        "created": "YYYY-MM-DD",
        "done": false
      }
    ]
  }
  ```
- **Hook** — `hooks/open-checkpoints.py`, wired via `hooks/hooks.json` on `SessionStart` (matcher
  `startup`). Reads the store, keeps items where `done == false AND (surface_on is null OR
  surface_on <= today)`, and emits a banner via
  `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": <banner>}}`.
  Emits **nothing** when there are no surfaceable items (no empty banner). Never self-denoises.
  Fail-safe: any error → exit 0 with no output (never block a session).
- **CLI** — `checkpoints.py` (shipped in the plugin, also runnable directly): `list`, `add`,
  `done <id>`, `prune` (remove done items). Atomic writes, schema validation, stable ids.
- **Skill** — `skills/open-checkpoints/SKILL.md`: documents the store + CLI and the wrap-up tie-in.

### Pure, unit-testable core (`checkpoints_core.py`)
`surfaceable(items, today) -> list`, `format_banner(items) -> str`, `add_item(...)`,
`mark_done(items, id)`, `prune(items)`. No I/O, deterministic given an injected `today`.

## 4. Banner format

```
⏳ Open checkpoints (N) — persist until marked done (`checkpoints done <id>`), or disable this plugin:
  • <title>  [<id>]
  • <title>  (since YYYY-MM-DD)  [<id>]
```
Distinct label ("Open checkpoints") so it's never confused with the resume-interrupted banner.

## 5. Data flow

- **Startup:** SessionStart → hook reads store → filters → emits banner (or nothing).
- **Management:** the CLAUDE.md wrap-up rule (and the user) run `checkpoints add/done/prune`, or edit
  the JSON. Marking done is what removes an item from the banner.

## 6. Wrap-up tie-in + hybrid discovery (agent-side)

The CLAUDE.md "Wrapping up — reconcile checkpoints" rule gains one step: reconcile the
open-checkpoints store — `done` finished items, `add` newly-created follow-ups, and (the *hybrid*
part) sweep memories/project-notes for pending markers (`⏳`, `REMAINING`, `TODO`) not yet in the
store and add them. This discovery is deliberately **agent-side at wrap-up**, never in the hook, so
the startup banner stays precise and false-positive-free.

## 7. Optionality / non-interference

- **Optional:** it's a plugin — disable/uninstall via `/plugin`. No other kill-switch needed.
- **Separate from resume-interrupted:** own plugin, own store file, own banner label; resume-interrupted
  is not touched. Both SessionStart hooks run independently; showing both banners on one startup is
  acceptable (distinct concerns).

## 8. Seed (initial store)

Seed with the currently-known open items, moving the *reminder* to the store as single source of truth
(the how-to detail stays in the referenced memory, avoiding duplication):
- `skill-restart-load` — confirm `mcp-smoke-test` auto-loads/triggers after a restart.
- `adobe-publish` — decide/open the Adobe upstream PRs (see adobe-mcp PROJECT-NOTES §5).
- `adobe-artwork` — surreal-waterfall, once the Photoshop panel/proxy are up.
- `corporate-wifi-retest` — `surface_on: 2026-07-13`; re-run Adobe cutout tests on corporate wifi.

## 9. Testing

- Unit (pytest): `surfaceable` (done + date boundaries incl. surface_on == today), `format_banner`
  (empty → no banner; dated vs undated), CLI `add/done/prune` on a temp store, schema round-trip.
- Integration: run the hook against a fixture store with a fixed `OPEN_CHECKPOINTS_TODAY` override and
  assert the emitted `additionalContext` JSON; run against an empty store and assert no output.

## 10. Publish

Follow the canonical-marketplace workflow: `gh repo create haiggoh/open-checkpoints`, add ONE entry to
the sync repo's `marketplace.json`, push, `claude plugin marketplace update`, install. Bump
`plugin.json` version on every change.

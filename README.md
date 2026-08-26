# waypoints

A Claude Code plugin that surfaces your **open tasks / to-dos / waypoints** as a SessionStart
banner — and, unlike [`resume-interrupted`](https://github.com/haiggoh/resume-interrupted), it
**persists until each item is explicitly marked done** (it does not self-denoise). It reads an
explicit store you maintain, so the banner shows exactly what you logged — no false positives.

## What it does

At session start, a hook reads `~/.claude/waypoints.json`, keeps the items that are **not
done** and **past any `surface_on` date**, and prints a banner:

```
🧭 waypoints: 2 open waypoint(s) still ahead — they persist until done. Just ask me to add or complete one; disable via /plugin if unwanted:
  • Publish the Adobe upstream PRs
    (since 2026-07-12)
      - branch fix/place-image; re-verify live first
      - decide: one PR or two
  • Re-test cutouts on corporate wifi
    (since 2026-07-12)
```

The `(since DATE)` annotation always gets its own line, hanging-indented under the title —
regardless of title length or terminal width — so indentation stays consistent everywhere.

If there are no surfaceable items, it prints nothing (no empty banner).

## Managing items

You don't need a console command: **just ask Claude** to add, complete, or list waypoints — it
surfaces the open ones each session and closes them for you (at the latest when you wrap up). Under
the hood it uses the bundled CLI, which you can also run yourself (or edit the JSON directly):

```sh
waypoints.py list
waypoints.py add "Publish the PR" --point "branch fix/x" --point "re-verify first" --detail "see repo X" --surface-on 2026-07-13
waypoints.py edit adobe-publish --title "Publish the PR (rebased)" --add-point "branch fix/x2"   # APPENDS
waypoints.py edit adobe-publish --replace-points --point "only bullet now"                       # REPLACES (must be explicit)
waypoints.py show adobe-publish     # title + summary + full detail — the "pick it up" view
waypoints.py done adobe-publish
waypoints.py reopen adobe-publish   # undo a mistaken done
waypoints.py toggle adobe-publish   # flip done state in one call
waypoints.py priority adobe-publish 5   # bump it ahead of others in the banner
waypoints.py reorder adobe-publish 0    # or move it to an explicit position
waypoints.py prune
waypoints.py triage adobe-publish --tier gated --gate-reason "needs your call on A vs B"
waypoints.py list --gated               # also --actionable / --untriaged, plus --open
waypoints.py list --json                # documented machine-readable contract
```

The command is `waypoints.py` (Claude Code v2.1.91+ adds the plugin's `bin/` to the Bash-tool PATH).

Each item has **three tiers** so the banner stays tidy without losing context: a short `title`
(headline), a few `summary` bullets (`--add-point` to append, `--point` to replace the whole list — the latter is refused on an item that already has bullets unless `--replace-points` is given), and a full `detail` dump
(on-demand only — read it with `show`). Use `edit` to change an item **in place**: it keeps the `id`
and `created` date, unlike a `done`+re-`add`.

`--surface-on` is the **earliest** date an item appears — **not an expiry**. An item surfaces on and
after that date and keeps showing every session until you mark it done.

## Blocked items

Some open items aren't waiting on effort, they're waiting on *something*. Mark those and say what:

```sh
waypoints.py triage adobe-publish --tier gated --gate-reason "needs your call on A vs B"
```

`--tier` is `do-now` (bounded, self-contained), `heavy` (doable alone but liable to sprawl), or
`gated`. Retiering away from `gated` drops the reason in the same call, so unblocking is one command.

In the banner, gated items are marked `⛔` in place. Once there are more than a few, the group
collapses to one counted line naming `/waypoints-gated` to expand it — the **count is always
stated**, so a collapsed group is disclosed, not hidden.

Two things this deliberately does *not* do:

- **It does not sort gated items last.** A gate reason is a question you owe yourself; burying it
  would assume some other tool is working through the rest of the list for you. Collapse triggers on
  group *length*, never on preference.
- **It does not treat "untriaged" as "actionable".** An item nobody has assessed is not thereby
  unblocked, so it gets its own view (`--untriaged`) instead of quietly padding the actionable pile.

Triaging is entirely optional — leave it alone and the plugin behaves exactly as before.

## Store

`~/.claude/waypoints.json` (override with `$WAYPOINTS_FILE`). It lives **outside** the
plugin so updates/reinstalls never touch your data.

```json
{ "version": 1, "items": [
  { "id": "adobe-publish", "title": "…", "summary": ["key point", "another"], "detail": "…",
    "surface_on": null, "created": "2026-07-12", "done": false }
] }
```

`tier` and `gate_reason` are added only when you triage an item, and removed again by `--clear` — a
store where you never triage anything is byte-identical to one from before the feature existed.

**To read the queue from a script, use `list --json`, not this file.** It emits a contract versioned
independently of the store, so the on-disk shape stays free to change:

```json
{ "contract": 1, "generated": "2026-08-14",
  "counts": { "total": 12, "open": 9, "done": 3, "surfaceable": 9,
              "gated": 2, "actionable": 4, "untriaged": 3 },
  "items": [ { "id": "…", "title": "…", "summary": [], "detail": "…", "created": "…",
               "surface_on": null, "done": false, "priority": 0, "surfaceable": true,
               "tier": null, "gate_reason": null } ] }
```

`tier`/`gate_reason` are always present here and `null` when unset, so a consumer never has to tell
a missing key from a null one. `gated + actionable + untriaged == open` — check it and you know
nothing was dropped. Filtered views add `"view"` and narrow `items`, but `counts` keep describing the
whole store.

## Install

```
/plugin marketplace add haiggoh/get-haiggoh
/plugin install waypoints@haiggoh
```

## Optional / disabling

It's a plugin — if you find it too naggy, disable or uninstall it via `/plugin`. Nothing else to
undo; your store file stays.

## Relationship to resume-interrupted

Distinct mechanism: separate plugin, separate store, separate banner label. resume-interrupted
answers "was my last session cut off?"; waypoints answers "what did I leave open that isn't done
yet?". No code-level dependency either way — but since resume-interrupted's banner is meant to
read as more urgent, waypoints optionally sequences after it: if resume-interrupted is installed
and enabled (detected via `~/.claude/settings.json`, not an import), waypoints briefly polls a
session-scoped flag resume-interrupted writes unconditionally on exit, capped at ~0.75s, and
always prints its own banner regardless of whether that flag showed up in time. If
resume-interrupted isn't installed, this adds zero latency and never runs at all.

## Tests

```
pytest tests/ -q
```

## License

MIT — see [LICENSE](LICENSE).

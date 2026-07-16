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
waypoints.py edit adobe-publish --title "Publish the PR (rebased)" --point "branch fix/x2"
waypoints.py show adobe-publish     # title + summary + full detail — the "pick it up" view
waypoints.py done adobe-publish
waypoints.py reopen adobe-publish   # undo a mistaken done
waypoints.py toggle adobe-publish   # flip done state in one call
waypoints.py priority adobe-publish 5   # bump it ahead of others in the banner
waypoints.py reorder adobe-publish 0    # or move it to an explicit position
waypoints.py prune
```

The command is `waypoints.py` (Claude Code v2.1.91+ adds the plugin's `bin/` to the Bash-tool PATH).

Each item has **three tiers** so the banner stays tidy without losing context: a short `title`
(headline), a few `summary` bullets (`--point`, shown under the title), and a full `detail` dump
(on-demand only — read it with `show`). Use `edit` to change an item **in place**: it keeps the `id`
and `created` date, unlike a `done`+re-`add`.

`--surface-on` is the **earliest** date an item appears — **not an expiry**. An item surfaces on and
after that date and keeps showing every session until you mark it done.

## Store

`~/.claude/waypoints.json` (override with `$WAYPOINTS_FILE`). It lives **outside** the
plugin so updates/reinstalls never touch your data.

```json
{ "version": 1, "items": [
  { "id": "adobe-publish", "title": "…", "summary": ["key point", "another"], "detail": "…",
    "surface_on": null, "created": "2026-07-12", "done": false }
] }
```

## Install

```
/plugin marketplace add haiggoh/claude-code-desktop-sync
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

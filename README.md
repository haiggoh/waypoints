# waypoints

A Claude Code plugin that surfaces your **open tasks / to-dos / waypoints** as a SessionStart
banner — and, unlike [`resume-interrupted`](https://github.com/haiggoh/resume-interrupted), it
**persists until each item is explicitly marked done** (it does not self-denoise). It reads an
explicit store you maintain, so the banner shows exactly what you logged — no false positives.

## What it does

At session start, a hook reads `~/.claude/waypoints.json`, keeps the items that are **not
done** and **past any `surface_on` date**, and prints a banner:

```
waypoints: Open waypoints (2) — these persist until marked done (`waypoints done <id>`), or disable this plugin if unwanted:
  • Publish the Adobe upstream PRs  (since 2026-07-12)  [adobe-publish]
  • Re-test cutouts on corporate wifi  (since 2026-07-12)  [corporate-wifi-retest]
```

If there are no surfaceable items, it prints nothing (no empty banner).

## Managing items

Use the bundled CLI (or edit the JSON directly):

```sh
python3 "$CLAUDE_PLUGIN_ROOT/bin/waypoints.py" list
python3 "$CLAUDE_PLUGIN_ROOT/bin/waypoints.py" add "Publish the PR" --detail "see repo X" --surface-on 2026-07-13
python3 "$CLAUDE_PLUGIN_ROOT/bin/waypoints.py" done adobe-publish
python3 "$CLAUDE_PLUGIN_ROOT/bin/waypoints.py" prune
```

`--surface-on` is the **earliest** date an item appears — **not an expiry**. An item surfaces on and
after that date and keeps showing every session until you mark it done.

## Store

`~/.claude/waypoints.json` (override with `$WAYPOINTS_FILE`). It lives **outside** the
plugin so updates/reinstalls never touch your data.

```json
{ "version": 1, "items": [
  { "id": "adobe-publish", "title": "…", "detail": "…", "surface_on": null, "created": "2026-07-12", "done": false }
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

Distinct, non-interfering mechanism: separate plugin, separate store, separate banner label. Both
SessionStart hooks run independently. resume-interrupted answers "was my last session cut off?";
waypoints answers "what did I leave open that isn't done yet?".

## Tests

```
pytest tests/ -q
```

## License

MIT — see [LICENSE](LICENSE).

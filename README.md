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
waypoints.py prune                  # MOVE every done item to the archive (destroys nothing)
waypoints.py rm adobe-publish       # remove ONE item from the live store, into the archive
waypoints.py restore adobe-publish  # bring an archived item back (still done)
waypoints.py archive list           # the closed-item paper trail (--json for the contract)
waypoints.py archive show adobe-publish
waypoints.py rm adobe-publish --delete --confirm   # permanent deletion: archive-only, two flags
waypoints.py triage adobe-publish --tier gated --gate-reason "needs your call on A vs B"
waypoints.py list --gated               # also --actionable / --untriaged, plus --open
waypoints.py list --json                # documented machine-readable contract
```

The command is `waypoints.py` (Claude Code v2.1.91+ adds the plugin's `bin/` to the Bash-tool PATH).

## Four tiers of record-keeping

```
open      → shown in the SessionStart banner
done      → in the live store, hidden from the banner, reopenable
archived  → moved out to ~/.claude/waypoints-archive.json, still readable, restorable
deleted   → gone; reachable only from `archived`, only via `rm <id> --delete --confirm`
```

The closed list is a deliberate **paper trail** — it is how you reconstruct, after the fact, where
an error slipped in. So nothing that runs routinely destroys it: `prune` and `rm` both *move* items
to the archive, and permanent deletion takes two explicit flags, works only on an already-archived
item, and accepts one exact id (no `--all`, no globs). `reopen <id>` auto-restores from the archive
in a single step, because reopen is the safety net that catches a premature close and friction
belongs nowhere near it.

**Every write is backed up first.** Before overwriting the store or the archive, the current file is
copied (never moved) into `~/.claude/waypoints-backups/`. Atomic writes already survive a crash;
these snapshots additionally survive a *correct-but-mistaken* command, which is the difference
between irreversible and recoverable. Retention keeps the last 10 snapshots plus the first of each
of the last 30 days — the daily tier is what stops one busy wrap-up from evicting the state the day
began in. Retention only ever deletes files it created itself (strict name matching), so hand-made
backups sitting nearby are never touched.

## The journal

Three records with three different jobs. Reach for the right one:

| | answers | kept |
|---|---|---|
| `journal` | *which command changed what, when* | append-only, **never pruned** |
| `archive list` | *how did this item resolve* | until you explicitly delete it |
| `waypoints-backups/` | *put the whole file back* | bounded ring (10 + 30 dailies) |

```
waypoints.py journal                        # the whole history
waypoints.py journal --id some-waypoint     # one item's life story
waypoints.py journal --since 2026-08-01     # from a date (or a full ISO stamp)
```

`~/.claude/waypoints-journal.jsonl` gets **one line per mutation**: the ISO timestamp, the raw
`argv`, and the before/after of each item that actually changed. Raw argv because the literal
command is the forensic artifact — a prettified description reflects what the code *believed* it was
doing, which is the very thing in question when you are reading back through history.

An entry costs from ~0.5 KB for a terse item up to a few KB for one with a long `detail` (which is
stored twice — before *and* after), against ~200 KB for a full-store snapshot of a busy store. So
between one and two orders of magnitude cheaper, and that ratio is the whole design: the journal can
afford to be permanent, which is what frees the snapshot ring to be small. Store + journal replayed
backwards reconstructs any earlier state, including one whose snapshot has long since aged out.

Two properties worth knowing:

- **It cannot cost you a waypoint.** Recording is wrapped so a failure to journal (full disk,
  read-only home) returns quietly and the mutation still lands. Insurance must never break the
  thing it insures.
- **A corrupt line costs one entry, not the file.** Every mutation appends here, so a crash
  mid-write can leave a partial tail; unparseable lines are skipped on read. Reading history is
  exactly when a truncated tail must not be fatal.

Journalling is wired into the two save functions, not into each subcommand — so a command nobody
thought about is still recorded. Permanent deletion is journalled too, which means the journal ends
up holding the only surviving copy of a deleted item.

## Banner size

The banner is injected into **every** session's context, so it is capped: it lists the
`BANNER_MAX_ITEMS` (default 10) highest-priority items, trims over-long titles to one line, and
discloses the rest as a count rather than listing them. Nothing is hidden — the header counts all
open items, the residue is counted explicitly, and `waypoints.py list` shows everything. Tune with
`$WAYPOINTS_BANNER_MAX_ITEMS` and `$WAYPOINTS_BANNER_TITLE_MAX`.

**No hard dependencies.** When more than a few items are gated, the summary line offers
`/ungate-queue` — a command from the separate `run-to-completion` plugin — but only after checking
that it is installed *and* enabled. Without it, the line simply points at this plugin's own
`/waypoints-gated`. The check fails closed, so waypoints never advertises a command your machine
does not have.

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

The journal is machine-readable by construction — one JSON object per line, each carrying its own
`"contract"` — so a consumer reads it directly rather than through a flag:

```json
{"argv": ["done", "some-id"], "at": "2026-08-27T13:53:37", "contract": 1, "source": "store",
 "changes": [{"id": "some-id", "before": {"done": false, "…": "…"},
                                "after": {"done": true, "…": "…"}}]}
```

`source` is `"store"` or `"archive"`, which is how a **move** (one line leaving the store, one
arriving in the archive) is told apart from a **loss**. A change with `"before": null` is an
addition, `"after": null` a removal, and `"moved": [from, to]` a pure reordering.

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

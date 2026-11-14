# Record schema — the waypoints store (C4, FLEET-owned)

Published 2026-11-14 per COORDINATION C4: FLEET owns the record/proposal schema, piloted on
this repo, and publishes it here + in COORDINATION §6 FLEET. SYNC's Phase 9 builds a generic
allowlisted record adapter and adds the waypoints mapping from THIS document; it never
blocks on it. Additive changes only — a breaking change needs a COORDINATION §6 entry.

## Store

- One file: `~/.claude/waypoints.json` (override `WAYPOINTS_FILE`). NEVER hand-edit it;
  every change goes through `waypoints.py` (one bad escape makes `json.load` fail for the
  WHOLE file). If it looks broken: `waypoints.py recover`.
- Shape: `{"items": [item, ...], "changes": [change, ...]}` — see `waypoints_core.py`
  (`ITEM_KEYS`, the journal writer) for the exact field sets.

## Item (one open or done record)

| field | type | meaning |
|---|---|---|
| `id` | string | stable kebab-case identity; never re-issued (the journal + archive key on it) |
| `title` | string | one-line summary shown in banners/lists |
| `detail` | string | long continuity dump, NOT shown in the banner |
| `points` | [string] | short sub-bullets appended in order (`--point` appends) |
| `surface_on` | YYYY-MM-DD \| null | date the item becomes visible (banner), else null |
| `created` | YYYY-MM-DD | creation date |
| `done` | bool | closed (evidence required) vs open |
| `tier` | `do-now` \| `heavy` \| `gated` \| `waiting` | actionability tier (`TIERS`) |
| `waiting_on` | [id] | only when tier == waiting: ids whose done/milestone releases it |
| `evidence` | string | what a reader can open to verify a done claim |
| `archived` | bool + archive move | closed items move to `waypoints-archive.json` by `prune` |

## Change (journal entry, append-only)

`{"id": item_id, "before": …, "after": …}` plus a timestamp — the recovery trail for
`recover`/`journal`. Never edited or reordered.

## Transport notes for adapters

- Single writer first: the CLI serialises writes (lock + atomic replace); a portable/SYNC
  adapter must do the same, never write the file concurrently.
- Absence/offline is not deletion: a missing store means UNKNOWN, never an empty list
  presented as "no open items".
- Completion evidence is scoped: `done` requires `evidence` naming a commit/file/test
  count; `--no-evidence` is for superseded/duplicate closures only.

# Record schema — the waypoints store (C4, FLEET-owned)

Published 2026-11-14 per COORDINATION C4: FLEET owns the record/proposal schema, piloted on
this repo, and publishes it here + in COORDINATION §6 FLEET. SYNC's Phase 9 builds a generic
allowlisted record adapter and adds the waypoints mapping from THIS document; it never
blocks on it. Additive changes only — a breaking change needs a COORDINATION §6 entry.
Verified against `waypoints_core.py` / `bin/waypoints.py` at df1e748.

## Store

- One file: `~/.claude/waypoints.json` (override `WAYPOINTS_FILE`). NEVER hand-edit it;
  every change goes through the CLI (one bad escape makes `json.load` fail for the WHOLE
  file). If it looks broken: `waypoints.py recover`.
- Shape: `{"version": 1, "items": [item, ...]}` — `version` is the store contract version
  (`waypoints_core.VERSION`).
- The journal is a SEPARATE append-only file derived from the store path:
  `waypoints-journal.jsonl`, one JSON object per line recording the command (`argv` tokens
  stay raw in the file) and the change (`before`/`after`, plus `moved: [a, b]` for
  reorders, and a timestamp). The archive is likewise a separate file
  (`waypoints-archive.json`, items carry `archived_at`/`restored_at`).

## Item (one live or done record)

| field | type | meaning |
|---|---|---|
| `id` | string | stable kebab-case identity; never re-issued (journal + archive key on it) |
| `title` | string | one-line summary shown in banners/lists |
| `summary` | [string] | short banner bullets — `--point` appends here; a close appends `CLOSED: <evidence>` (or `CLOSED WITHOUT EVIDENCE OF WORK: …`) to this list |
| `detail` | string | long continuity dump, NOT shown in the banner |
| `surface_on` | YYYY-MM-DD \| null | date the item becomes visible in banners |
| `created` | YYYY-MM-DD | creation date |
| `done` | bool | closed vs open |
| `tier` | `do-now` \| `heavy` \| `gated` \| `waiting` | actionability (`TIERS`); `gated`/`waiting` carry the gate text in `gate_reason` |
| `priority` | int | ordering weight inside a tier |
| `repos` | [string] | repo scoping for repo-local items |
| `pin_reason` | string \| null | user-pinned items carry the reason |
| `waiting` | [string] | only when tier == waiting: `"<item-id> @ <milestone>"` strings, released when the target lands |

## Transport rules for adapters

- Single writer first: the CLI serialises writes (lock + atomic replace) and journals every
  command; a portable/SYNC adapter must do the same, never write the store concurrently.
- Absence/offline is not deletion: a missing store means UNKNOWN, never an empty list
  presented as "no open items".
- Completion evidence is scoped: `done --evidence` requires a checkable pointer (commit sha,
  file:line, version/tag, test count, command, URL) — the CLI rejects prose; `--no-evidence`
  is for superseded/duplicate closures only, and records why.

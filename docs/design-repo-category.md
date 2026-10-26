# Design — repo category + filter for waypoints (2026-10-26)

Phase 1 output of `HANDOFF-repo-category.md`. Survey only; nothing implemented.
Design decisions are NOT final until the user picks — see "Decisions the user owns".

## Problem (verbatim, waypoint `waypoints-repo-category-and-changelog-sweep`)

> "waypoints: give every item a repo/project category + a filter for it, then sweep all
> items against those repos' changelogs to close the ones already built"

User request 2026-10-26: no clear/obvious way to see only one repo's waypoints; most items
belong to a repo. Two deliverables: (1) a schema+CLI change in this plugin, (2) a one-off
data pass over the ~225 open items, cross-checked against each repo's CHANGELOG.

## What the survey found (facts this design stands on)

- Items are plain dicts in `waypoints.json` v1
  (`waypoints_core.py:10-16`): `id, title, summary, detail, surface_on, created, done,
  priority` + optional `tier, gate_reason, waiting_on, pinned, pin_reason`. **No repo field.**
- Optional fields are **absent by default, never defaulted** (`waypoints_core.py:640-651`,
  the tier comment): an old store stays valid with NO migration. Any new field must follow
  this idiom.
- `list_payload` (`waypoints_core.py:1211`, LIST_CONTRACT=3) documents the bump policy:
  *additive fields alone do not justify a contract bump; a changed invariant does*
  (`waypoints_core.py:1231-1240`). View keys are always PRESENT, null when unset.
- The `waiting` tier is the precedent for a structured, validated field: free prose is
  normalized to ONE shape on disk (`normalize_waiting_on`, `waypoints_core.py:668`), malformed
  input is REFUSED at write (`validate_verdict` → `VerdictError`), and a reference that points
  at nothing is SURFACED at read (`WAITING_STALE`, `waypoints_core.py:807-852`) — never guessed,
  never repaired silently.
- `list` filters along one axis (verdict views, mutually exclusive) plus `--open`;
  pagination echoes the options in force (`_next_page_cmd`, `bin/waypoints.py:311`) and
  measures page size in bytes, never estimates (`bin/waypoints.py:233`). A new filter must
  join both mechanisms or paginated filtered views silently lose the filter.
- The banner is injected into EVERY session and is deliberately capped
  (`BANNER_MAX_ITEMS=10`, compact mode, `waypoints_core.py:1345-1359`); its per-session cost
  is the reason `list` exists. Banner changes are the most expensive place to add anything.
- `search` greps the DATA (title, bullets, detail) untruncated — the anti-`list|grep` command
  (`bin/waypoints.py:869-932`). The journal diffs whole items (`diff_items`), so a repo
  change on an existing item is journaled for free once the field exists.
- The changelog side: repos are directories under `~/ClaudeWorkspace/`; a repo's changelog is
  `~/ClaudeWorkspace/<repo>/CHANGELOG.md`. No registry exists — the directory list IS the
  registry (verified by listing: free-agents, run-to-completion, waypoints, cost-tracker, …).

## Options

### A — Single optional `repo` string; `--repo` filter; banner untouched

`add --repo free-agents`, `edit --repo/--clear-repo`, `list --repo free-agents`
(composes with verdict views), `search --repo`. Banner shows nothing.

- Smallest diff: one field, one filter flag, three commands touched.
- Two-repo items degenerate to prose in `detail` — invisible to the filter. The user said
  "most items belong to a repo", not all; umbrella/index items (the master indexes) belong to
  none. The degenerate case is real but rare.
- No banner cost at all.

### B — List-normalized `repo` field (the `waiting_on` precedent); `--repo`; minimal banner tag

Store as a LIST of strings on disk, accepting a single string at write
(`add --repo free-agents` → `repos: ["free-agents"]`), exactly like `normalize_waiting_on`.
`list --repo X` matches when X is ANY element. Banner: in compact mode only, when the
listed items span ≥2 repos, append a short `[repo]` tag to each listed title; single-repo
or non-compact banners render exactly as today.

- Handles the two-repo and none cases natively; one shape on disk; matches the field idiom
  already in the codebase.
- Banner change is opt-in-by-condition (multi-repo spans only) — the common session sees
  nothing new.
- Slightly larger diff than A: normalization + filter-matches-any + banner condition.

### C — B + filesystem validation and stale-repo surfacing; banner grouping

On top of B: repo values are checked against `~/ClaudeWorkspace/` at read time; a repo that
matches no directory is surfaced like `WAITING_STALE` (`⚠ no such repo: X`) in `list` and
`resolve`; the banner gains optional per-repo group headers; a `--list-repos` helper prints
the derived repo list (dirs with a CHANGELOG.md) for the sweep.

- Strongest consistency story: a typo'd repo is visible, not silently unfilterable.
- But unlike `waiting` (whose targets live IN the store), a repo lives on the FILESYSTEM:
  validation couples the store to one machine's directory layout and breaks the
  env-overridable test seams ($WAYPOINTS_CLAUDE_DIR exists for this). Also the heaviest
  banner change — group headers restructure the one surface paid on every session.

## Recommendation: **B**, with C's stale-repo report as a follow-up gated on the user

- B matches the codebase's strongest precedent (waiting_on) at moderate cost, solves the
  actual request ("see only one repo's waypoints" → `list --repo X`), and keeps the banner
  cost conditional. A is a subset of B that fails the two-repo case structurally; C's
  filesystem validation can be layered later without reworking B (the read-time check is
  additive), so deferring it loses nothing.
- Contract: **no LIST_CONTRACT bump** — additive `repos` (null when unset) changes no
  invariant, per the policy the file itself documents.
- Migration: none — absent by default; the Phase 2 sweep backfills existing items via
  `waypoints.py edit <id> --repo …` (one journal entry each, no bulk writer).

## Sweep mechanics (Phase 2 preview, unchanged from the handoff)

- Repo list: directories under `~/ClaudeWorkspace/` containing `CHANGELOG.md`.
- Output `docs/sweep-candidates.tsv`: `id → inferred_repo (or ?) → evidence →
  changelog_hit (quoted line + version, or none) → verdict (likely-built|unclear|still-open)`.
- Handoff rule 7 governs verdicts: a "built" claim needs a QUOTED changelog line or a code
  path; changelog silence = UNKNOWN, not open and not done. Umbrella/index items get `?`,
  never a guessed repo.
- Bulk classification may be dispatched to a free model; 10 verdicts spot-checked against
  source before anything is trusted.

## Decisions the user owns (Phase 3 STOP list)

1. **Option A, B, or C** — recommendation B.
2. **Banner treatment** — none (A) / conditional tag (B) / group headers (C). This surface is
   paid every session; the default recommendation is the conditional tag only.
3. **Repo name convention** — the `~/ClaudeWorkspace/<repo>` dir name as the canonical value
   (recommended), vs. a friendlier alias layer (adds a mapping nobody maintains).
4. **Filesystem validation** (C's piece) — defer (recommended) or include now.
5. Whether the Phase 2 sweep may **auto-close** any `likely-built` items after user review of
   the TSV, or only propose (the handoff says propose — stands unless overridden).

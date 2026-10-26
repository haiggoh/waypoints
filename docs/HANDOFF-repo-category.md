# Handoff — waypoints: repo category + changelog sweep (2026-10-26)

## Why this exists
The paid Opus/Sonnet session that started this was asked (by the user) to hand the task to a free
session. It had only reached the START of brainstorming: it read the waypoint, found no repo field in
the schema, and asked the user "walk me through the last time you wanted one repo's waypoints" —
**that question is still UNANSWERED.** So design decisions are NOT made. Do not invent them as final.

## Goal (verbatim, from waypoint `waypoints-repo-category-and-changelog-sweep`)
"waypoints: give every item a repo/project category + a filter for it, then sweep all items against
those repos' changelogs to close the ones already built"
- User request 2026-10-26: no clear/obvious way to see only one repo's waypoints; most items belong to a repo.
- Current schema has NO repo field (only id/title/summary/detail/tier/priority/pin/waiting_on) — so this
  is (1) a schema+CLI change in the waypoints plugin and (2) a one-off data pass over ~225 open items.
- Same sweep: check each item's requirements against its repo's CHANGELOG to find resolved-but-never-closed
  items (the user expects many).

Read it yourself: `waypoints.py show waypoints-repo-category-and-changelog-sweep`.

## State
- Worktree: `~/ClaudeWorkspace/.wt/waypoints-repo-category`, branch `feat/repo-category`, from main `21135ae` (plugin v0.13.0).
- Source files: `waypoints_core.py` (store/schema), `waypoints_menu.py`, `bin/`, `commands/`, `tests/`, `CHANGELOG.md`.
- Nothing implemented. Nothing changed in the live waypoints store.

## Standing rules
1. Autonomous within the scope below; decide and record. Stop only for forks that cannot be weighed.
2. Work only in the worktree above. Never switch the branch of `~/ClaudeWorkspace/waypoints` (main checkout).
3. Commit each milestone staged BY PATH (never `git add -A`), with the running model's co-author trailer
   (identity from memory `commit-attribution-by-model`). Do not push, merge, tag or release.
4. NEVER hand-edit `~/.claude/waypoints.json` or the archive; every store change goes through `waypoints.py`.
   NEVER run `waypoints.py done/rm/prune/edit/add` in THIS task's phase 1/2 — read-only (`list`, `show`, `search`) only.
5. Write home paths as `~/...` or `$HOME/...`, never expanded. A hook blocks the expanded form.
6. Never run `remote-session.sh` (no stop, no new session) and never kill anything on ports 4141-4151.
7. Resolve facts from the real code/CHANGELOG, never memory. A "built" verdict needs a quoted CHANGELOG
   line or a code path — "looks done" is not evidence. Silence in a changelog means UNKNOWN, not open or done.
8. Record progress by appending one line to the Progress section below at each milestone, committed with it.
9. Any new script supports `--help` (run it to verify).

## Scope for THIS session (read-only + proposal; implementation is gated on the user)
**Phase 1 — survey (no code changes).** Read `waypoints_core.py`: how items are stored, loaded, listed,
filtered, migrated; how the SessionStart banner picks items. Write `docs/design-repo-category.md` with
2-3 concrete options (e.g. single `repo` string vs list `repos`; `--repo` filter on `list`/`search`;
banner grouping; handling items touching two repos or none; backward-compat for existing stores;
how repo names map to `~/ClaudeWorkspace/<repo>` dirs and their CHANGELOGs) and a RECOMMENDATION with
trade-offs. Mark clearly which choices need the user.

**Phase 2 — inference + sweep candidates (read-only).** Run `waypoints.py list` and `show` to read the open
items. Produce `docs/sweep-candidates.tsv` with columns: id, inferred_repo (or `?` — never guess for
umbrella/index items), evidence_for_repo, changelog_hit (quoted line + version, or `none`), verdict
(`likely-built` | `unclear` | `still-open`). Batch the reading; the repo list is the dirs under
`~/ClaudeWorkspace` with a `CHANGELOG.md`. For each `likely-built`, quote the changelog line AND the
waypoint requirement it satisfies side by side. Dispatch bulk classification to a free model via
`bin/free-agent-tool.py` if useful (attach the files), and spot-check 10 of its verdicts against source —
reviewers hallucinate.

**Phase 3 — STOP.** Commit the two docs, append progress, and end with a summary for the user: the
recommended design, counts per verdict, and the list of `likely-built` ids proposed for closing.
The user decides the design and approves closes. Do not implement or close anything.

## Next action
Phase 1: read `waypoints_core.py` and write `docs/design-repo-category.md`.

## Progress
- 2026-10-26 Phase 1 done: `docs/design-repo-category.md` — 3 options (A single string / B list-normalized /
  C + filesystem validation), recommendation B, user-owned decisions listed.
- 2026-10-26 Phase 2 done: `docs/sweep-candidates.tsv` — 228 open items vs 19 canonical repos. Mechanical
  pre-pass (umbrella + self-declared filters, identifier + document-frequency changelog matching) measured
  ~25% precision over 3 spot-check rounds; cross-family validator dispatch attempted and FAILED (Gemini 3.8
  Flash + DeepSeek V4.1 Flash read-timeouts, 600s wall-clock cap), so the 109 candidates were judged
  in-session (GLM) with drop-when-unsure: 9 keep / 100 drop / 119 not candidates; all 9 kept quotes verified
  verbatim in their CHANGELOGs. Provenance per row in the judge_note column.
- 2026-10-26 Phase 3 done: committed. STOPPING — the user decides the design (A/B/C) and approves any
  closes. Nothing was closed, nothing pushed, the live store was never written.

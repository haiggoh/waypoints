# Handoff — waypoints: IMPLEMENT repo category, design B (2026-10-27)

## Why this exists
Phases 1-3 (survey, design options, sweep) are done and committed (`810e294`, see
`docs/HANDOFF-repo-category.md` for that history). On 2026-10-27 the user PICKED **design B**.
The paid session that reviewed it handed the IMPLEMENTATION to this free session (user request:
"free-session-handover for waypoints repo-category design B"). Nothing of B is implemented yet.

## Goal (verbatim, waypoint `waypoints-repo-category-and-changelog-sweep`)
"waypoints: give every item a repo/project category + a filter for it, then sweep all items
against those repos' changelogs to close the ones already built"
- User request 2026-10-26: no clear/obvious way to see only one repo's waypoints; most items belong to a repo.
- THIS session's scope is the schema + CLI half ONLY (design B). The data backfill and the
  changelog sweep are NOT in scope (see Out of scope).

## The decided design — read `docs/design-repo-category.md`, section "B", and follow it
User decision 2026-10-27: **Option B**. The defaults recommended in "Decisions the user owns"
apply, because the user took B as recommended:
1. Field: optional `repos` on an item, a LIST of strings on disk. Absent by default, never
   defaulted, no migration, no LIST_CONTRACT bump (additive; `list_payload` view key present,
   null when unset) — the idiom documented at `waypoints_core.py` (tier comment, ~640-651;
   contract policy ~1231-1240).
2. Write: `add --repo X` (repeatable) and `edit <id> --repo X` (repeatable, APPENDS like
   `--point`) plus `edit <id> --clear-repo`. A single string normalizes to a one-element list,
   exactly like `normalize_waiting_on` (~668). Malformed input (empty, whitespace, a `/`,
   duplicates) is REFUSED at write with a clear error, never repaired silently. Dedupe within an
   item. Values are the `~/ClaudeWorkspace/<repo>` DIRECTORY NAME; no alias layer.
3. Read: `list --repo X` and `search --repo X` match when X is ANY element. `--repo` must COMPOSE
   with the verdict views and `--open`, and must be ECHOED by pagination (`_next_page_cmd`,
   `bin/waypoints.py` ~311) or a paginated filtered view silently loses the filter.
   `show` prints the repos line when set.
4. Banner: in COMPACT mode only, and only when the LISTED items span 2+ distinct repos, append a
   short `[repo]` tag to each listed title that has one (multi-repo item: first repo + `+N`).
   Single-repo or non-compact banners render BYTE-IDENTICAL to today — assert that in a test.
   The tag counts against `BANNER_TITLE_MAX` (trim the title, never the tag).
5. NOT now: filesystem validation of repo names (option C), banner group headers, a
   `--list-repos` helper. Do not build them.

## State
- Worktree: `~/ClaudeWorkspace/.wt/waypoints-repo-category`, branch `feat/repo-category`,
  based on origin/main `21135ae` (plugin v0.13.0). Phase 1-3 commit `810e294` is docs only.
- Code: `waypoints_core.py` (store/schema/banner), `bin/waypoints.py` (CLI), `waypoints_menu.py`,
  `tests/` (pytest + `tests/test_version_consistency.sh`), `CHANGELOG.md`, `README.md`,
  `skills/` (the waypoints skill documents the CLI — update it for `--repo`).

## Standing rules
1. Autonomous: decide and record instead of asking; stop only for forks that cannot be weighed.
2. Work ONLY in the worktree above. Never touch or switch the branch of `~/ClaudeWorkspace/waypoints`.
3. Commit every milestone, staged BY PATH (never `git add -A`), with the RUNNING model's co-author
   trailer (memory `commit-attribution-by-model`; e.g. GLM 5.3 → `Co-Authored-By: GLM 5.3 <noreply@z.ai>`).
   Push the branch `feat/repo-category` to origin at the end. NEVER merge, tag or release.
4. TDD every change: the test fails for the right reason first, then passes. Mutation-check each
   new validation/guard (break it, see the test go red, restore — confirm the break APPLIED).
   Never weaken an existing test to get green.
5. ★ THE LIVE STORE IS SACRED. NEVER run `waypoints.py` against `~/.claude/waypoints.json`
   except the read-only `list`/`show`/`search`. Never hand-edit it or the archive. Every test runs
   against a temp store (`WAYPOINTS_FILE`, `WAYPOINTS_CLAUDE_DIR` → tmp). Milestone 0 enforces it.
6. Review each milestone with an independent dispatch (`bin/free-agent-tool.py` in the
   free-agents plugin; attach the changed files) and check every finding against the real code:
   reviewers hallucinate.
7. Never run `remote-session.sh --stop`, never start another remote session, never kill anything
   listening on 4141-4151: one of them is the proxy you run on.
8. Record progress below at each milestone, in the same commit.
9. Write home paths as `~/...` or `$HOME/...`, never expanded.
10. Full suite: `pytest -n auto` with the pipx pytest (`~/.local/bin/pytest`; system python3 has
    no xdist), plus `bash tests/test_version_consistency.sh`.

## Milestones
- **M0 — store tripwire (test-only).** Add an autouse fixture in `tests/conftest.py` that points
  `WAYPOINTS_FILE` and `WAYPOINTS_CLAUDE_DIR` at `tmp_path` for EVERY test (subprocess children
  inherit the env), plus a test proving a test that sets nothing cannot reach the real path.
  Full suite must stay green.
- **M1 — schema + normalize/validate** (`waypoints_core.py`): `normalize_repos`, refusal errors,
  journal diff covers the field, `list_payload` view key.
- **M2 — CLI write side**: `add --repo`, `edit --repo / --clear-repo`, `show`.
- **M3 — CLI read side**: `list --repo`, `search --repo`, composition, pagination echo.
- **M4 — banner tag** with the byte-identical-otherwise test.
- **M5 — docs + version**: CHANGELOG entry, README + skill docs for `--repo`, bump 0.13.0 →
  0.14.0 in EVERY version surface (`tests/test_version_consistency.sh` lists them). Full suite
  green, then push the branch and STOP with a summary: tests (counts), what each commit did,
  anything deferred.

## Out of scope (do NOT do)
- Backfilling `repos` onto the live items, closing items, or acting on `docs/sweep-candidates.tsv`.
  Those need the user and the live store.
- Merge/tag/release/plugin refresh — the paid session ships after review.

## Next action
M0: read `tests/conftest.py` and `waypoints_core.py:store_path`/`claude_dir`, then write the
failing tripwire test.

## Progress
- 2026-10-27 handoff written by the paid session (Opus 5.5). Nothing implemented yet.

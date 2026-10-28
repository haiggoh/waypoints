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
- 2026-10-27 M0 done (free session, GLM 5.3): autouse `_isolated_store` fixture in
  `tests/conftest.py` ($WAYPOINTS_FILE + $WAYPOINTS_CLAUDE_DIR → tmp_path for EVERY test;
  subprocess children inherit via `dict(os.environ, …)` helpers, tests that set their own
  env still win). Tripwire `test_unprotected_test_cannot_reach_the_real_store` in
  `tests/test_hook_and_cli.py`: asserts in-process + subprocess path RESOLUTION before any
  write, so its own red state is side-effect-free. Mutations verified: typo'd
  `WAYPOINT_FILE` → red at the store_path assert; `WAYPOINTS_CLAUDE_DIR` setenv removed →
  red at the claude_dir assert; both restored → green. Suite 353 passed (`pytest -n auto`),
  `test_version_consistency.sh` ALL PASS. Decisions recorded: (a) no real-store mtime
  comparison in the tripwire — resolution-proof is airtight (all writes derive from
  store_path) and an mtime check would false-red if a live session writes the real store
  mid-test; (b) pre-existing E401 on conftest L1 left as-is (repo test style).
- 2026-10-27 M1 done (free session, GLM 5.3): core repo machinery in `waypoints_core.py` —
  `RepoError(ValueError)`, `normalize_repos` (single string → one-element list like
  `normalize_waiting_on`; REFUSES empty/blank, surrounding whitespace, `/`-paths, non-strings,
  duplicates within one write — never silently repaired), `merge_repos` (order-preserving
  union = the "dedupe within an item" append semantics: input duplicates refused, union
  deduped so `edit --repo X` is idempotent and a no-op append earns no journal entry),
  `repos_of` accessor; `add_item(repos=…)`, `edit_item(repos=…)` (_UNSET = leave, empty =
  clear back to ABSENT per the set_verdict idiom); `list_payload` carries `repos`
  (null-when-unset view key), LIST_CONTRACT stays 3 (additive — pinned by a test).
  17 tests in `tests/test_waypoints.py` incl. journal-diff-covers-repos proof. Mutations
  verified (9 guard tests went red, breaks applied jointly): all per-value refusals,
  edit-clear, merge-dedupe, plus `revalidates` (note: `-k repos` DESELECTS that test —
  "revalidates" lacks the substring; run it by full name). Suite 370 passed. Decision
  recorded: handoff bullet 2 read as "duplicates IN ONE WRITE refused; duplicates vs the
  item's existing list deduped" — both sentences get distinct referents, matches the
  --point append precedent, and makes the Phase-2 backfill idempotent. Reviews: M0/M1
  independent dispatch BLOCKED so far (remote free lane: gemini 503 ×2, nvidia timeouts ×3;
  local Laguna S: hotswap failure) — retrying via local DeepSeek V4 Flash (reasoner,
  cross-family); if every free route fails, reviews must happen in the paid session before
  merge (flagged in the final summary).
- 2026-10-27 M0+M1 review DONE (free session, GLM 5.3): remote lane failed twice (gemini 503
  ×2, nvidia timeouts ×3) and local Laguna hotswap failed, so the review ran via local
  DeepSeek V4 Flash (deepseek family — cross-family vs zhipu, `role_matched: true`,
  `family_avoided: true`; task JSON /tmp/m0m1-review-local.json, result
  /tmp/m0m1-review-local-result.json). 15 findings, every one checked against the code.
  Disposition: F1 (tripwire "cannot distinguish fixture present/absent") — disproven by the
  M0 mutations, which turned the test red with the fixture broken both ways. F2 (a test
  could `delenv` its way to the real path) — real but out of the threat model (the hazard is
  forgetting; no such test exists; a fixture cannot defend against deliberate un-setting).
  F3 (xdist) — reviewer constructed no scenario; none exists. F4 (no real-store mtime check)
  — the documented M0 decision (resolution proof is airtight; mtime would false-red against
  live sessions). F5/F6/F8/F9/F11-14 — reviewer themselves marked not-defects (design
  choices); F7 (add-`[]`-absent vs edit-`[]`-cleares "asymmetry") — the INVARIANT is
  consistent (empty ⇒ absent on both paths); not a defect. F10/F15 — REAL: a hand-edited or
  legacy `repos: "foo"` (string) char-split through the read path
  (`list("foo") → ['f','o','o']`) and `list_payload` would emit a bare string against the
  array-or-null contract. FIXED FORWARD: `_read_repos` defensive reader (legacy string
  coerces to one repo — the normalize_waiting_on precedent; anything the tool would refuse
  to write degrades to [] — the waiting_targets precedent); `merge_repos` reads its existing
  side defensively and tolerates a bare-string new; `list_payload` emits `repos_of(i) or
  None`. While fixing, a WORSE variant surfaced than the reviewer's: `normalize_repos`
  ACCEPTED a dict (iterating it silently stored its KEYS as repos) — now only str/list/tuple
  are accepted, everything else refused (write) / degraded (read). 6 new tests, all
  mutation-verified (container refusal + read degrade jointly broken → 3 red, restored →
  green). Suite 376 passed; version check ALL PASS.
- 2026-10-27 M2 done (free session, GLM 5.3): CLI write side in `bin/waypoints.py` —
  `add --repo NAME` (repeatable, order-preserving), `edit <id> --repo NAME` (append via
  `merge_repos`, so re-adding is a no-op and the journal stays silent on it),
  `edit <id> --clear-repo` (conflicts with `--repo`, exit 2, mirroring --clear-summary's
  refusal pattern), `show` prints `repos: a + b` (through `repos_of`, so legacy values
  cannot char-split in the display). Refusals are CAUGHT in both add and edit branches and
  print `refused: …` + exit 2 — never a traceback; a refused edit returns BEFORE
  `save_store`, so nothing is written. Module docstring usage lines updated. 8 CLI tests in
  `tests/test_hook_and_cli.py`; test-design rule: refusal tests assert on the MESSAGE and
  store state, never rc alone (argparse's unknown-flag error also exits 2). Mutations
  verified jointly (6 guards broken at once: add-catch, edit-catch, conflict check,
  merge→raw append, clear wiring, show line → 7 attributable reds; restored → green).
  During restore one `return 2` was briefly dropped from the edit except-block — caught by
  the collect-green-after-restore rule before commit; suite 384 passed, version ALL PASS.
- 2026-10-27 M2 review DONE (local DeepSeek V4 Flash; first attempt hit `Hotswap failed:`
  — the local inference server was wedged by a stuck 40 GB model process; the USER evicted
  it with la-evict.sh and the re-dispatch succeeded). 29 numbered findings reduce to ~6
  unique; every one checked against the code, ZERO actionable: title-discarded-on-refused-
  repo is the atomic-refusal contract itself; no-op edits printing "edited" is pre-existing
  CLI-wide behavior (the journal — the authoritative record — is correctly silent, and rc
  still separates refusal from no-op); the stdout/stderr split matches each message's
  nearest sibling (conflict→stdout like --clear-summary, validation-refusal→stderr like
  pin); "no such id"→stdout/rc 1 is the every-command convention. The reviewer INDEPENDENTLY
  CONFIRMED the safety properties: no path from a refused edit to save_store, no malformed
  value reaching the store, correct journal silence on idempotent appends.
- 2026-10-27 M3 done (free session, GLM 5.3): read side in `bin/waypoints.py` —
  `list --repo NAME` (ANY-element membership; composes with the verdict views and --open;
  applies to `--json`, which now filters its items AND records `payload["repo"]` while
  counts stay whole-store, and sets `payload["view"]` to None rather than a lying "open"
  when only the repo filter is active), pagination echoes `--repo` in `_next_page_cmd`,
  `search --repo NAME` (per-pool filter + the empty-result footer names the repo scope),
  empty `list --repo` results NAME the filter (scope honesty). Two process catches worth
  recording: (1) Pyright caught a real nesting bug from a mid-indent Edit substring match
  (the `if args.repo:` scope-suffix landed as a sibling of `if not args.ids_only:` and
  swallowed the search footer — the old search tests caught it in the full suite; lesson:
  Edit anchors need surrounding-context lines, and the full-suite run after every edit is
  the backstop); (2) the M3 mutation check exposed two VACUOUS tests (composes/any-element
  fixtures had no item the filter would exclude) — both strengthened with discriminator
  items, re-verified red under the mutations. Mutations verified: list filter, json filter,
  pagination echo, search filter, scope suffix — all 5 jointly broken → 8 red; restored →
  green. Suite 392 passed; version check ALL PASS.
- 2026-10-28 M3 review DONE (local DeepSeek V4 Flash, cross-family): ~22 numbered items
  reducing to ~8 unique. TWO REAL, both fixed forward: (1) the pagination echo did not
  QUOTE a repo name containing spaces (legal values) — the printed Next: command would
  split `--repo free agents` into two tokens and break on re-run; fixed with
  shlex.quote in `_next_page_cmd`; (2) `list --repo X --open` over a repo whose items
  are all done printed "(no waypoints for repo X)", implying the repo has none at all —
  now "(no OPEN waypoints for repo X)". REJECTED with reasons: making a repo-scoped
  empty `search` exit 0 (uniform rc semantics is what scripts key on — an empty search
  is rc 1 today in every scope); the payload `view` collapsing view+`--open` to the
  view name (pre-existing behavior, preserved byte-identically by M3 — the payload never
  described --open separately). The reviewer self-verified the rest as non-defects
  (view key honest in all combos, scope lines accurate, no filter dropped in --json).
  Both fixes TDD'd (red first) and mutation-verified jointly with M4's guards.
- 2026-10-28 M4 done (free session, GLM 5.3): the conditional banner tag in
  `waypoints_core.py` `format_banner` — compact mode only, and only when the LISTED
  (post-cap) items span 2+ distinct repos; each repos-carrying title gains ` [repo]`
  (multi-repo: ` [first+N]`); items without repos get no tag even in tag mode. The tag
  counts against BANNER_TITLE_MAX (title trimmed, tag never). BYTE-IDENTICAL otherwise,
  proven by two pins that render repos-carrying items against their repos-stripped twins
  and demand exact equality (non-compact; compact single-repo span) — these passed BEFORE
  the implementation and stayed green after. Mutations verified jointly with the M3 fixes:
  always-tag (condition dropped) → both byte-identity pins red; no-budget → budget test
  red; unquoted echo; dropped open-word → both fix tests red. Suite 399 passed; version
  check ALL PASS. Design note: the span is computed over `shown` (post-BANNER_MAX_ITEMS
  cap) — "the LISTED items" per the handoff; unlisted tail items do not trigger tagging.

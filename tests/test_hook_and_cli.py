import json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(ROOT, "hooks", "waypoints.py")
CLI = os.path.join(ROOT, "bin", "waypoints.py")


def _env(store, today=None):
    e = dict(os.environ, WAYPOINTS_FILE=str(store))
    if today:
        e["WAYPOINTS_TODAY"] = today
    return e


def _run(argv, store, today=None, stdin="", env_extra=None):
    env = _env(store, today)
    if env_extra:
        env.update(env_extra)
    return subprocess.run([sys.executable] + argv, input=stdin, capture_output=True,
                           text=True, env=env)


def test_hook_empty_store_emits_nothing(tmp_path):
    store = tmp_path / "s.json"
    r = _run([HOOK], store, "2026-07-12")
    assert r.returncode == 0
    assert r.stdout.strip() == ""  # no empty banner


def test_hook_emits_additionalcontext_for_surfaceable(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "Publish the PR"], store, "2026-07-12")
    r = _run([HOOK], store, "2026-07-12")
    assert r.returncode == 0
    payload = json.loads(r.stdout)
    ctx = payload["hookSpecificOutput"]["additionalContext"]
    assert payload["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "Publish the PR" in ctx and "waypoint" in ctx.lower()


def test_hook_usermsg_hides_cli_but_model_ctx_keeps_invocation_and_branding(tmp_path):
    # UX: users manage waypoints by talking to Claude, not a console command. The visible
    # systemMessage must not show a CLI invocation; the model-facing context must keep the
    # correct one (`waypoints.py`, not bare `waypoints`) plus the 🧭 prose-branding instruction.
    store = tmp_path / "s.json"
    _run([CLI, "add", "Publish the PR"], store, "2026-07-12")
    payload = json.loads(_run([HOOK], store, "2026-07-12").stdout)
    user_msg = payload["systemMessage"]
    ctx = payload["hookSpecificOutput"]["additionalContext"]
    assert "waypoints done" not in user_msg and "waypoints.py" not in user_msg
    assert "waypoints.py done <id>" in ctx  # correct bare command via bin/ PATH injection
    assert "🧭" in ctx and "prose" in ctx    # branding instruction ships to all users


def test_hook_respects_future_surface_on(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "Later thing", "--surface-on", "2026-07-13"], store, "2026-07-12")
    # before the date → nothing
    assert _run([HOOK], store, "2026-07-12").stdout.strip() == ""
    # on the date → shows (persists after, too)
    assert "Later thing" in _run([HOOK], store, "2026-07-13").stdout
    assert "Later thing" in _run([HOOK], store, "2026-07-20").stdout


def test_cli_add_list_done_prune(tmp_path):
    store = tmp_path / "s.json"
    add = _run([CLI, "add", "Do X"], store, "2026-07-12")
    assert "added [do-x]" in add.stdout
    assert "[do-x] Do X" in _run([CLI, "list"], store, "2026-07-12").stdout
    # done removes it from the hook banner
    _run([CLI, "done", "do-x"], store, "2026-07-12")
    assert _run([HOOK], store, "2026-07-12").stdout.strip() == ""
    # prune MOVES the done item out of the live store (0.4.0: it no longer destroys it)
    _run([CLI, "prune"], store, "2026-07-12")
    assert "(no open waypoints)" in _run([CLI, "list"], store, "2026-07-12").stdout


def test_hook_survives_corrupt_store(tmp_path):
    store = tmp_path / "s.json"
    store.write_text("{ this is not valid json ")
    r = _run([HOOK], store, "2026-07-12")
    assert r.returncode == 0 and r.stdout.strip() == ""  # fail-safe, no crash


# ---- v0.1.3: add --point, edit, show ----

def test_cli_add_with_points_and_banner_shows_them(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "Do X", "--point", "first", "--point", "second"], store, "2026-07-14")
    out = _run([HOOK], store, "2026-07-14").stdout
    assert "first" in out and "second" in out


def test_cli_edit_retitles_but_keeps_id(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "Old name"], store, "2026-07-14")
    edit = _run([CLI, "edit", "old-name", "--title", "New name"], store, "2026-07-14")
    assert edit.returncode == 0
    lst = _run([CLI, "list"], store, "2026-07-14").stdout
    assert "[old-name] New name" in lst   # same id, new title (this is the whole point of edit)


def test_cli_edit_sets_summary_points(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "Task"], store, "2026-07-14")
    _run([CLI, "edit", "task", "--point", "alpha", "--point", "beta"], store, "2026-07-14")
    out = _run([HOOK], store, "2026-07-14").stdout
    assert "alpha" in out and "beta" in out


def test_cli_edit_missing_id_errors(tmp_path):
    store = tmp_path / "s.json"
    r = _run([CLI, "edit", "nope", "--title", "x"], store, "2026-07-14")
    assert r.returncode == 1


def test_cli_show_prints_title_summary_detail(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "Task", "--detail", "the full context dump", "--point", "k1"], store, "2026-07-14")
    r = _run([CLI, "show", "task"], store, "2026-07-14")
    assert r.returncode == 0
    assert "the full context dump" in r.stdout and "k1" in r.stdout and "Task" in r.stdout


def test_cli_edit_clear_surface_on(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "Later", "--surface-on", "2026-08-01"], store, "2026-07-14")
    assert _run([HOOK], store, "2026-07-14").stdout.strip() == ""     # hidden before date
    _run([CLI, "edit", "later", "--clear-surface-on"], store, "2026-07-14")
    assert "Later" in _run([HOOK], store, "2026-07-14").stdout        # cleared → surfaces now


# ---- v0.1.4: reopen, toggle, priority, reorder ----

def test_cli_reopen_undoes_done(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "Task"], store, "2026-07-15")
    _run([CLI, "done", "task"], store, "2026-07-15")
    assert _run([HOOK], store, "2026-07-15").stdout.strip() == ""      # gone once done
    r = _run([CLI, "reopen", "task"], store, "2026-07-15")
    assert r.returncode == 0 and "reopened" in r.stdout
    assert "Task" in _run([HOOK], store, "2026-07-15").stdout          # back once reopened


def test_cli_reopen_missing_id_errors(tmp_path):
    store = tmp_path / "s.json"
    r = _run([CLI, "reopen", "nope"], store, "2026-07-15")
    assert r.returncode == 1


def test_cli_toggle_flips_done_state(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "Task"], store, "2026-07-15")
    r1 = _run([CLI, "toggle", "task"], store, "2026-07-15")
    assert "now done" in r1.stdout
    assert _run([HOOK], store, "2026-07-15").stdout.strip() == ""
    r2 = _run([CLI, "toggle", "task"], store, "2026-07-15")
    assert "now open" in r2.stdout
    assert "Task" in _run([HOOK], store, "2026-07-15").stdout


def test_cli_priority_changes_banner_order(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "First added"], store, "2026-07-15")
    _run([CLI, "add", "Second added"], store, "2026-07-15")
    _run([CLI, "priority", "second-added", "5"], store, "2026-07-15")
    out = _run([HOOK], store, "2026-07-15").stdout
    assert out.index("Second added") < out.index("First added")       # bumped ahead


def test_cli_priority_missing_id_errors(tmp_path):
    store = tmp_path / "s.json"
    r = _run([CLI, "priority", "nope", "3"], store, "2026-07-15")
    assert r.returncode == 1


def test_cli_reorder_moves_item_in_list(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "A"], store, "2026-07-15")
    _run([CLI, "add", "B"], store, "2026-07-15")
    _run([CLI, "add", "C"], store, "2026-07-15")
    r = _run([CLI, "reorder", "c", "0"], store, "2026-07-15")
    assert r.returncode == 0
    lst = _run([CLI, "list"], store, "2026-07-15").stdout
    assert lst.index("[c]") < lst.index("[a]") < lst.index("[b]")


def test_cli_reorder_missing_id_errors(tmp_path):
    store = tmp_path / "s.json"
    r = _run([CLI, "reorder", "nope", "0"], store, "2026-07-15")
    assert r.returncode == 1


# ---- v0.1.12: done --as + unresolved-title guard ----

def test_cli_done_as_rewrites_title_and_closes(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "Confirm qwen thinking works"], store, "2026-08-01")
    r = _run([CLI, "done", "confirm-qwen-thinking-works", "--as",
              "Confirmed: qwen thinking + native tools work"], store, "2026-08-01")
    assert r.returncode == 0
    lst = _run([CLI, "list"], store, "2026-08-01").stdout
    assert "✓ [confirm-qwen-thinking-works] Confirmed: qwen thinking" in lst  # retitled + done
    assert "Confirm qwen thinking works" not in lst                          # old question gone
    assert _run([HOOK], store, "2026-08-01").stdout.strip() == ""            # closed → no banner


def test_cli_done_warns_on_unresolved_title_without_as(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "Decide + open the PRs"], store, "2026-08-01")
    r = _run([CLI, "done", "decide-open-the-prs"], store, "2026-08-01")
    assert r.returncode == 0                       # still closes (non-blocking guard)
    assert "marked done" in r.stdout
    assert "⚠️" in r.stderr and "--as" in r.stderr  # nudge on stderr with the fix


def test_cli_done_quiet_when_as_given_on_unresolved_title(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "Verify the fix holds"], store, "2026-08-01")
    r = _run([CLI, "done", "verify-the-fix-holds", "--as", "Verified: fix holds"], store, "2026-08-01")
    assert r.returncode == 0
    assert "⚠️" not in r.stderr                     # resolution recorded → no nudge


def test_cli_done_quiet_on_plain_imperative_title(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "Publish the PR"], store, "2026-08-01")
    r = _run([CLI, "done", "publish-the-pr"], store, "2026-08-01")
    assert r.returncode == 0
    assert "⚠️" not in r.stderr                     # plain task imperative reads fine as done


def test_cli_done_missing_id_still_errors(tmp_path):
    store = tmp_path / "s.json"
    r = _run([CLI, "done", "nope"], store, "2026-08-01")
    assert r.returncode == 1 and "no such id" in r.stdout


def _settings(tmp_path, enabled):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"enabledPlugins": enabled}))
    return str(p)


def test_hook_skips_wait_when_resume_interrupted_not_installed(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "Publish the PR"], store, "2026-07-12")
    settings = _settings(tmp_path, {"waypoints@haiggoh": True})
    r = _run([HOOK], store, "2026-07-12", stdin=json.dumps({"session_id": "s1"}),
              env_extra={"CLAUDE_SETTINGS_FILE": settings, "TMPDIR": str(tmp_path)})
    assert r.returncode == 0
    assert "Publish the PR" in r.stdout


def test_hook_waits_then_prints_when_flag_never_appears(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "Publish the PR"], store, "2026-07-12")
    settings = _settings(tmp_path, {"resume-interrupted@haiggoh": True, "waypoints@haiggoh": True})
    r = _run([HOOK], store, "2026-07-12", stdin=json.dumps({"session_id": "s2"}),
              env_extra={"CLAUDE_SETTINGS_FILE": settings, "TMPDIR": str(tmp_path),
                         "WAYPOINTS_BANNER_WAIT_S": "0.2", "WAYPOINTS_BANNER_POLL_S": "0.05"})
    assert r.returncode == 0
    assert "Publish the PR" in r.stdout  # falls through and prints anyway, never suppressed


def test_hook_resolves_fast_when_flag_already_present(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "Publish the PR"], store, "2026-07-12")
    settings = _settings(tmp_path, {"resume-interrupted@haiggoh": True, "waypoints@haiggoh": True})
    flag_dir = tmp_path / "claude-sessionstart-banners"
    flag_dir.mkdir()
    (flag_dir / "s3.resume-interrupted.done").write_text("producer=resume-interrupted printed=0\n")
    r = _run([HOOK], store, "2026-07-12", stdin=json.dumps({"session_id": "s3"}),
              env_extra={"CLAUDE_SETTINGS_FILE": settings, "TMPDIR": str(tmp_path),
                         "WAYPOINTS_BANNER_WAIT_S": "5", "WAYPOINTS_BANNER_POLL_S": "0.05"})
    assert r.returncode == 0
    assert "Publish the PR" in r.stdout


def test_hook_malformed_settings_file_disables_wait(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "Publish the PR"], store, "2026-07-12")
    settings = tmp_path / "settings.json"
    settings.write_text("not json")
    r = _run([HOOK], store, "2026-07-12", stdin=json.dumps({"session_id": "s4"}),
              env_extra={"CLAUDE_SETTINGS_FILE": str(settings), "TMPDIR": str(tmp_path)})
    assert r.returncode == 0
    assert "Publish the PR" in r.stdout


# ---- list --json contract + symmetric views + triage ----

def test_list_json_emits_the_documented_contract(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "Ship it"], store, "2026-07-12")
    r = _run([CLI, "list", "--json"], store, "2026-07-12")
    assert r.returncode == 0
    p = json.loads(r.stdout)
    # Contract 2 added the `waiting` count and `waiting_on`. The bump is deliberate: the
    # documented sum invariant changed from gated+actionable+untriaged to
    # gated+waiting+actionable+untriaged, so a consumer auditing the old sum would break.
    assert p["contract"] == 2
    assert "waiting" in p["counts"]
    assert (p["counts"]["gated"] + p["counts"]["waiting"] + p["counts"]["actionable"]
            + p["counts"]["untriaged"]) == p["counts"]["open"]
    assert p["generated"] == "2026-07-12"
    assert set(p["counts"]) == {"total", "open", "done", "surfaceable", "gated",
                                "waiting", "actionable", "untriaged"}
    row = p["items"][0]
    # Every documented field is present, and the verdict fields are null rather than missing.
    for key in ("id", "title", "summary", "detail", "created", "surface_on", "done",
                "priority", "surfaceable", "tier", "gate_reason"):
        assert key in row, key
    assert row["tier"] is None and row["gate_reason"] is None


def test_list_json_counts_describe_the_whole_store_even_in_a_filtered_view(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "A"], store, "2026-07-12")
    _run([CLI, "add", "B"], store, "2026-07-12")
    _run([CLI, "triage", "b", "--tier", "gated", "--gate-reason", "needs a decision"],
         store, "2026-07-12")
    r = _run([CLI, "list", "--json", "--gated"], store, "2026-07-12")
    p = json.loads(r.stdout)
    assert p["view"] == "gated"
    assert len(p["items"]) == 1 and p["items"][0]["title"] == "B"
    # A filtered view still reports the totals it is a subset of.
    assert p["counts"]["open"] == 2 and p["counts"]["gated"] == 1


def test_symmetric_views_partition_the_open_items(tmp_path):
    store = tmp_path / "s.json"
    for t in ("A", "B", "C"):
        _run([CLI, "add", t], store, "2026-07-12")
    _run([CLI, "triage", "a", "--tier", "do-now"], store, "2026-07-12")
    _run([CLI, "triage", "b", "--tier", "gated", "--gate-reason", "waiting on the vendor"],
         store, "2026-07-12")
    counts = {}
    for view in ("actionable", "gated", "untriaged"):
        r = _run([CLI, "list", "--json", f"--{view}"], store, "2026-07-12")
        counts[view] = len(json.loads(r.stdout)["items"])
    assert counts == {"actionable": 1, "gated": 1, "untriaged": 1}
    # C is untriaged and must NOT be absorbed into actionable -- unassessed != unblocked.
    r = _run([CLI, "list", "--json", "--actionable"], store, "2026-07-12")
    assert [i["title"] for i in json.loads(r.stdout)["items"]] == ["A"]


def test_list_text_view_reports_the_group_tally(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "A"], store, "2026-07-12")
    _run([CLI, "triage", "a", "--tier", "heavy"], store, "2026-07-12")
    r = _run([CLI, "list"], store, "2026-07-12")
    assert "1 actionable" in r.stdout and "0 gated" in r.stdout
    assert "--gated" in r.stdout          # the other views are discoverable from the default one


def test_triage_refuses_a_gate_reason_on_a_non_gated_tier(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "A"], store, "2026-07-12")
    r = _run([CLI, "triage", "a", "--tier", "do-now", "--gate-reason", "nope"],
             store, "2026-07-12")
    assert r.returncode == 2 and "refused" in r.stdout


def test_triage_clear_returns_an_item_to_untriaged(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "A"], store, "2026-07-12")
    _run([CLI, "triage", "a", "--tier", "gated", "--gate-reason", "blocked"], store, "2026-07-12")
    r = _run([CLI, "triage", "a", "--clear"], store, "2026-07-12")
    assert r.returncode == 0 and "untriaged" in r.stdout
    saved = json.loads(store.read_text())["items"][0]
    assert "tier" not in saved and "gate_reason" not in saved


def test_triage_rejects_an_unknown_tier(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "A"], store, "2026-07-12")
    r = _run([CLI, "triage", "a", "--tier", "urgent"], store, "2026-07-12")
    assert r.returncode != 0          # argparse choices rejects it before it reaches the store


def test_views_are_mutually_exclusive(tmp_path):
    store = tmp_path / "s.json"
    r = _run([CLI, "list", "--gated", "--actionable"], store, "2026-07-12")
    assert r.returncode != 0


def test_show_prints_the_verdict_and_gate_reason(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "A"], store, "2026-07-12")
    _run([CLI, "triage", "a", "--tier", "gated", "--gate-reason", "needs you present"],
         store, "2026-07-12")
    r = _run([CLI, "show", "a"], store, "2026-07-12")
    assert "gated" in r.stdout and "needs you present" in r.stdout


def test_hook_banner_collapses_many_gated_items(tmp_path):
    store = tmp_path / "s.json"
    for k in range(5):
        _run([CLI, "add", f"Blocked {k}"], store, "2026-07-12")
        _run([CLI, "triage", f"blocked-{k}" if k else "blocked-0", "--tier", "gated",
              "--gate-reason", "waiting"], store, "2026-07-12")
    r = _run([HOOK], store, "2026-07-12")
    payload = json.loads(r.stdout)
    msg = payload["systemMessage"]
    assert "gated" in msg
    assert "5 open waypoint(s)" in msg      # total still stated


# --- guarded summary mutation (0.3.0) -------------------------------------
# Regression cover for a real incident: `edit --point` REPLACES the bullet list, but
# every doc surface (including the SessionStart banner) taught it as the way to record
# new information, so agents used it as if it appended and silently destroyed bullets
# on 8 items. `--point` must now fail closed; `--add-point` is the appending verb.

def _bullets(store, wid):
    items = json.load(open(store))
    items = items["items"] if isinstance(items, dict) and "items" in items else items
    return [i for i in items if i["id"] == wid][0].get("summary") or []


def _seed(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "Test item", "--point", "bullet A", "--point", "bullet B"], store)
    return store


def test_edit_point_refuses_to_discard_existing_bullets(tmp_path):
    store = _seed(tmp_path)
    r = _run([CLI, "edit", "test-item", "--point", "new only"], store)
    assert r.returncode == 2, r.stdout
    assert "refusing to discard 2" in r.stdout
    # the discarded text is echoed so it stays recoverable from the transcript
    assert "bullet A" in r.stdout and "bullet B" in r.stdout
    assert "--add-point" in r.stdout and "--replace-points" in r.stdout
    assert _bullets(store, "test-item") == ["bullet A", "bullet B"]  # untouched


def test_edit_add_point_appends(tmp_path):
    store = _seed(tmp_path)
    r = _run([CLI, "edit", "test-item", "--add-point", "bullet C"], store)
    assert r.returncode == 0
    assert _bullets(store, "test-item") == ["bullet A", "bullet B", "bullet C"]


def test_edit_replace_points_confirms_and_echoes(tmp_path):
    store = _seed(tmp_path)
    r = _run([CLI, "edit", "test-item", "--replace-points", "--point", "replaced"], store)
    assert r.returncode == 0
    assert "replacing 2" in r.stdout and "bullet A" in r.stdout
    assert _bullets(store, "test-item") == ["replaced"]


def test_edit_point_still_works_when_no_bullets_exist(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "Bare item"], store)
    r = _run([CLI, "edit", "bare-item", "--point", "first bullet"], store)
    assert r.returncode == 0, r.stdout
    assert _bullets(store, "bare-item") == ["first bullet"]


def test_edit_rejects_point_and_add_point_together(tmp_path):
    store = _seed(tmp_path)
    r = _run([CLI, "edit", "test-item", "--point", "x", "--add-point", "y"], store)
    assert r.returncode == 2
    assert _bullets(store, "test-item") == ["bullet A", "bullet B"]


def test_clear_summary_echoes_what_it_dropped(tmp_path):
    store = _seed(tmp_path)
    r = _run([CLI, "edit", "test-item", "--clear-summary"], store)
    assert r.returncode == 0
    assert "clearing 2" in r.stdout and "bullet A" in r.stdout
    assert _bullets(store, "test-item") == []


def test_add_accepts_add_point_alias(tmp_path):
    store = tmp_path / "s.json"
    r = _run([CLI, "add", "Alias item", "--add-point", "a1"], store)
    assert r.returncode == 0
    assert _bullets(store, "alias-item") == ["a1"]


def test_edit_missing_id_reports_before_touching_summary(tmp_path):
    store = _seed(tmp_path)
    r = _run([CLI, "edit", "no-such-item", "--add-point", "x"], store)
    assert r.returncode == 1 and "no such id" in r.stdout


def test_banner_teaches_add_point_not_bare_point_for_edits(tmp_path):
    # The banner is where the wrong verb was learned; it must now teach the safe one.
    store = tmp_path / "s.json"
    _run([CLI, "add", "Something open"], store)
    r = _run([HOOK], store, "2026-07-12")
    ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "--add-point" in ctx
    assert "--replace-points" in ctx


# ---- v0.4.0: archive tier, rm, restore, and the deletion two-step ----

def _archive_file(store):
    return os.path.splitext(str(store))[0] + "-archive.json"


def _read(path):
    """Re-read state from DISK. The house rule: never verify a state change from the CLI's echo,
    which can claim success it did not achieve."""
    if not os.path.exists(path):
        return {"items": []}
    with open(path) as f:
        return json.load(f)


def _ids(path):
    return [i["id"] for i in _read(path)["items"]]


def test_prune_archives_rather_than_destroying(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "Keep me"], store, "2026-08-27")
    _run([CLI, "add", "Close me"], store, "2026-08-27")
    _run([CLI, "done", "close-me"], store, "2026-08-27")
    _run([CLI, "prune"], store, "2026-08-27")
    # the item left the live store AND arrived in the archive — asserted on both files
    assert _ids(store) == ["keep-me"]
    assert _ids(_archive_file(store)) == ["close-me"]
    archived = _read(_archive_file(store))["items"][0]
    assert archived["archived_at"] == "2026-08-27"
    assert archived["title"] == "Close me"  # the record survives intact, not just the id


def test_prune_is_idempotent_and_does_not_duplicate_the_archive(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "Close me"], store, "2026-08-27")
    _run([CLI, "done", "close-me"], store, "2026-08-27")
    _run([CLI, "prune"], store, "2026-08-27")
    _run([CLI, "restore", "close-me"], store, "2026-08-27")
    _run([CLI, "prune"], store, "2026-08-28")
    assert _ids(_archive_file(store)) == ["close-me"]


def test_rm_archives_an_open_item_which_is_why_rm_exists(tmp_path):
    # The 08-26 case: a stray OPEN test probe had to be cleared by hand-editing the store.
    store = tmp_path / "s.json"
    _run([CLI, "add", "Stray probe"], store, "2026-08-27")
    r = _run([CLI, "rm", "stray-probe"], store, "2026-08-27")
    assert r.returncode == 0
    assert _ids(store) == []
    assert _ids(_archive_file(store)) == ["stray-probe"]
    assert "OPEN" in r.stdout  # closing an open item must be stated, not silent


def test_rm_delete_without_confirm_refuses_and_changes_nothing(tmp_path):
    # THE GUARD. Mutation-tested: removing the `if not args.confirm` branch in bin/waypoints.py
    # must make THIS test fail.
    store = tmp_path / "s.json"
    _run([CLI, "add", "Close me"], store, "2026-08-27")
    _run([CLI, "done", "close-me"], store, "2026-08-27")
    _run([CLI, "prune"], store, "2026-08-27")
    before = _read(_archive_file(store))
    r = _run([CLI, "rm", "close-me", "--delete"], store, "2026-08-27")
    assert r.returncode == 2, "a bare --delete must fail closed"
    assert "refusing" in r.stdout and "--confirm" in r.stdout  # names the flag it needs
    assert _read(_archive_file(store)) == before, "the archive was modified despite the refusal"


def test_rm_delete_confirm_destroys_only_from_the_archive(tmp_path):
    store = tmp_path / "s.json"
    for title in ("Close me", "Keep me"):
        _run([CLI, "add", title], store, "2026-08-27")
        _run([CLI, "done", title.lower().replace(" ", "-")], store, "2026-08-27")
    _run([CLI, "prune"], store, "2026-08-27")
    r = _run([CLI, "rm", "close-me", "--delete", "--confirm"], store, "2026-08-27")
    assert r.returncode == 0
    assert _ids(_archive_file(store)) == ["keep-me"], "deleted the wrong item, or too many"


def test_rm_delete_refuses_a_live_item_and_prints_the_two_step(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "Live one"], store, "2026-08-27")
    r = _run([CLI, "rm", "live-one", "--delete", "--confirm"], store, "2026-08-27")
    assert r.returncode == 2
    assert "LIVE store" in r.stdout
    assert "Step 1" in r.stdout and "Step 2" in r.stdout
    assert _ids(store) == ["live-one"], "a refused delete must leave the live store untouched"


def test_reopen_auto_restores_from_the_archive_in_one_step(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "Premature close"], store, "2026-08-27")
    _run([CLI, "done", "premature-close"], store, "2026-08-27")
    _run([CLI, "prune"], store, "2026-08-27")
    r = _run([CLI, "reopen", "premature-close"], store, "2026-08-28")
    assert r.returncode == 0
    assert "restored" in r.stdout.lower()
    # it moved BACK: present and open in the live store, gone from the archive
    live = _read(store)["items"]
    assert [i["id"] for i in live] == ["premature-close"]
    assert live[0]["done"] is False
    assert _ids(_archive_file(store)) == []
    # and the banner surfaces it again — the safety net actually works end to end
    assert "Premature close" in _run([HOOK], store, "2026-08-28").stdout


def test_reopen_and_restore_keep_archived_at(tmp_path):
    # The trail must carry WHEN it closed; a restore adds a fact, it does not erase one.
    store = tmp_path / "s.json"
    _run([CLI, "add", "Round trip"], store, "2026-08-27")
    _run([CLI, "done", "round-trip"], store, "2026-08-27")
    _run([CLI, "prune"], store, "2026-08-27")
    _run([CLI, "reopen", "round-trip"], store, "2026-08-28")
    item = _read(store)["items"][0]
    assert item["archived_at"] == "2026-08-27"
    assert item["restored_at"] == "2026-08-28"


def test_restore_brings_it_back_still_done(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "Closed thing"], store, "2026-08-27")
    _run([CLI, "done", "closed-thing"], store, "2026-08-27")
    _run([CLI, "prune"], store, "2026-08-27")
    r = _run([CLI, "restore", "closed-thing"], store, "2026-08-28")
    assert r.returncode == 0
    assert _read(store)["items"][0]["done"] is True, "restore is a move, not a reopen"
    assert _ids(_archive_file(store)) == []
    assert _run([HOOK], store, "2026-08-28").stdout.strip() == ""  # still out of the banner


def test_restore_refuses_when_the_id_is_already_live(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "Same name"], store, "2026-08-27")
    _run([CLI, "done", "same-name"], store, "2026-08-27")
    _run([CLI, "prune"], store, "2026-08-27")
    _run([CLI, "add", "Same name"], store, "2026-08-28")  # mints the same slug
    r = _run([CLI, "restore", "same-name"], store, "2026-08-28")
    assert r.returncode == 2
    assert _ids(_archive_file(store)) == ["same-name"], "the archived copy must be left alone"


def test_reopen_prefers_the_live_copy_and_warns_about_the_archived_namesake(tmp_path):
    # ids are slugs, so a new item can mint an id the archive already holds.
    store = tmp_path / "s.json"
    _run([CLI, "add", "Same name"], store, "2026-08-27")
    _run([CLI, "done", "same-name"], store, "2026-08-27")
    _run([CLI, "prune"], store, "2026-08-27")
    _run([CLI, "add", "Same name"], store, "2026-08-28")
    _run([CLI, "done", "same-name"], store, "2026-08-28")
    r = _run([CLI, "reopen", "same-name"], store, "2026-08-29")
    assert r.returncode == 0
    assert "archived item with the same id" in r.stderr  # named, not silently disambiguated
    assert _read(store)["items"][0]["done"] is False     # the LIVE copy was reopened
    assert _ids(_archive_file(store)) == ["same-name"]   # the archived one stayed put


def test_archive_list_and_show_read_the_trail(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "Trail item", "--point", "a bullet", "--detail", "the long dump"],
         store, "2026-08-27")
    _run([CLI, "done", "trail-item"], store, "2026-08-27")
    _run([CLI, "prune"], store, "2026-08-27")
    lst = _run([CLI, "archive", "list"], store, "2026-08-28")
    assert "trail-item" in lst.stdout and "archived 2026-08-27" in lst.stdout
    show = _run([CLI, "archive", "show", "trail-item"], store, "2026-08-28")
    assert "a bullet" in show.stdout and "the long dump" in show.stdout
    assert _run([CLI, "archive", "show", "nope"], store, "2026-08-28").returncode == 1


def test_archive_list_json_emits_the_documented_contract(tmp_path):
    # This path crashed outright in the 0.4.0 draft (archive_payload was never defined), and a
    # test that only checked the exit code of `archive list` would never have caught it.
    store = tmp_path / "s.json"
    _run([CLI, "add", "Trail item"], store, "2026-08-27")
    _run([CLI, "done", "trail-item"], store, "2026-08-27")
    _run([CLI, "prune"], store, "2026-08-27")
    r = _run([CLI, "archive", "list", "--json"], store, "2026-08-28")
    assert r.returncode == 0, r.stderr
    pay = json.loads(r.stdout)
    assert pay["contract"] == 1
    assert pay["counts"]["total"] == 1
    assert pay["items"][0]["id"] == "trail-item"
    assert pay["items"][0]["archived_at"] == "2026-08-27"


def test_every_write_leaves_a_recoverable_snapshot_on_disk(tmp_path):
    store = tmp_path / "waypoints.json"
    bdir = tmp_path / "waypoints-backups"
    _run([CLI, "add", "First"], store, "2026-08-27")
    _run([CLI, "add", "Second"], store, "2026-08-27")
    _run([CLI, "add", "Third"], store, "2026-08-27")
    snaps = sorted(p for p in os.listdir(bdir) if p.startswith("waypoints."))
    assert len(snaps) >= 2, "writes after the first must be recoverable: %r" % snaps
    # the oldest snapshot holds the pre-second-add state, i.e. genuinely a prior generation
    oldest = json.load(open(os.path.join(bdir, snaps[0])))
    assert [i["id"] for i in oldest["items"]] == ["first"]


def test_the_store_survives_its_own_backup_via_the_cli(tmp_path):
    store = tmp_path / "waypoints.json"
    _run([CLI, "add", "First"], store, "2026-08-27")
    _run([CLI, "add", "Second"], store, "2026-08-27")
    assert store.exists()
    assert sorted(_ids(store)) == ["first", "second"]


def test_hook_note_teaches_the_archive_verbs_and_the_capped_banner(tmp_path):
    # Agents are the primary users of these commands; a verb absent from the note is a verb no
    # session discovers. Assert it ships through the HOOK, not by reading the source.
    store = tmp_path / "s.json"
    _run([CLI, "add", "Something open"], store, "2026-08-27")
    ctx = json.loads(_run([HOOK], store, "2026-08-27").stdout)[
        "hookSpecificOutput"]["additionalContext"]
    assert "waypoints.py rm <id>" in ctx           # the per-item removal, over hand-editing
    assert "ARCHIVES, never deletes" in ctx        # and that it is non-destructive
    assert "archive list" in ctx                   # the paper trail is discoverable
    assert "--delete --confirm" in ctx             # deletion is named as the user's call
    assert "waypoints.py list" in ctx              # the banner is capped, so list is the full view


# ---- the journal, end to end through the CLI (0.5.0) ----

def _journal_file(store):
    return os.path.splitext(str(store))[0] + "-journal.jsonl"


def _jlines(store):
    """Re-read the journal from DISK, skipping nothing silently: any unparseable line fails the
    test loudly here, which is the opposite of what the reader does on purpose."""
    path = _journal_file(store)
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def test_every_mutating_command_leaves_a_journal_entry(tmp_path):
    """The coverage test. Journalling is wired into save_store/save_archive rather than into
    each subcommand precisely so this can hold for commands nobody thought about."""
    store = tmp_path / "s.json"
    _run([CLI, "add", "One"], store, "2026-08-27")
    _run([CLI, "add", "Two"], store, "2026-08-27")
    mutations = [
        ["edit", "one", "--add-point", "a point"],
        ["priority", "one", "5"],
        ["reorder", "two", "0"],
        ["triage", "one", "--tier", "do-now"],
        ["done", "two"],
        ["reopen", "two"],
        ["toggle", "two"],
        ["prune"],
        ["rm", "one"],
    ]
    for argv in mutations:
        before = len(_jlines(store))
        r = _run([CLI] + argv, store, "2026-08-27")
        assert r.returncode == 0, (argv, r.stderr)
        after = _jlines(store)
        assert len(after) > before, "%s left no journal entry" % " ".join(argv)
        assert after[-1]["argv"][0] == argv[0]


def test_journal_records_the_before_and_after_of_the_touched_item(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "Fix the thing"], store, "2026-08-27")
    _run([CLI, "done", "fix-the-thing", "--as", "Fixed the thing"], store, "2026-08-27")
    entry = _jlines(store)[-1]
    change = [ch for ch in entry["changes"] if ch["id"] == "fix-the-thing"][0]
    assert change["before"]["done"] is False and change["before"]["title"] == "Fix the thing"
    assert change["after"]["done"] is True and change["after"]["title"] == "Fixed the thing"


def test_journal_records_argv_not_a_rendered_description(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "Some title", "--point", "a bullet"], store, "2026-08-27")
    assert _jlines(store)[-1]["argv"] == ["add", "Some title", "--point", "a bullet"]


def test_rm_journals_the_move_as_removal_plus_archive_addition(tmp_path):
    # Two entries, two sources: this is how a MOVE is distinguished from a LOSS after the fact.
    store = tmp_path / "s.json"
    _run([CLI, "add", "Stray"], store, "2026-08-27")
    _run([CLI, "rm", "stray"], store, "2026-08-27")
    tail = _jlines(store)[-2:]
    assert [e["source"] for e in tail] == ["store", "archive"]
    assert tail[0]["changes"][0]["after"] is None       # left the live store
    assert tail[1]["changes"][0]["before"] is None      # arrived in the archive


def test_permanent_deletion_is_itself_journalled(tmp_path):
    """The one destructive path must be the best-recorded one: after a real delete the item is
    gone from every store, so the journal holds the only copy of what it said."""
    store = tmp_path / "s.json"
    _run([CLI, "add", "Doomed", "--point", "why it existed"], store, "2026-08-27")
    _run([CLI, "rm", "doomed"], store, "2026-08-27")
    _run([CLI, "rm", "doomed", "--delete", "--confirm"], store, "2026-08-27")
    assert _ids(_archive_file(store)) == [] and _ids(store) == []
    gone = [e for e in _jlines(store) if "--delete" in (e.get("argv") or [])]
    assert len(gone) == 1
    recovered = gone[0]["changes"][0]["before"]
    assert recovered["title"] == "Doomed" and recovered["summary"] == ["why it existed"]


def test_cli_journal_reads_back_the_history(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "Readable"], store, "2026-08-27")
    r = _run([CLI, "journal"], store, "2026-08-27")
    assert r.returncode == 0
    assert "add Readable" in r.stdout and "+ readable: added" in r.stdout


def test_cli_journal_filters_by_id(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "Alpha"], store, "2026-08-27")
    _run([CLI, "add", "Beta"], store, "2026-08-27")
    r = _run([CLI, "journal", "--id", "beta"], store, "2026-08-27")
    assert "Beta" in r.stdout and "Alpha" not in r.stdout


def test_cli_journal_filters_by_since(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "Old news"], store, "2026-08-01")
    _run([CLI, "add", "Fresh"], store, "2026-08-27")
    r = _run([CLI, "journal", "--since", "2026-08-27"], store, "2026-08-27")
    assert "Fresh" in r.stdout and "Old news" not in r.stdout


def test_cli_journal_names_the_field_that_changed(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "Thing"], store, "2026-08-27")
    _run([CLI, "priority", "thing", "3"], store, "2026-08-27")
    r = _run([CLI, "journal", "--id", "thing"], store, "2026-08-27")
    assert "~ thing: priority" in r.stdout


def test_cli_journal_on_an_empty_history_explains_itself(tmp_path):
    store = tmp_path / "s.json"
    r = _run([CLI, "journal"], store, "2026-08-27")
    assert r.returncode == 0 and "no journal yet" in r.stdout


def test_cli_journal_survives_a_corrupt_line(tmp_path):
    # Reading history is exactly when a truncated tail must not be fatal.
    store = tmp_path / "s.json"
    _run([CLI, "add", "Survivor"], store, "2026-08-27")
    with open(_journal_file(store), "a") as f:
        f.write("{ truncated\n")
    r = _run([CLI, "journal"], store, "2026-08-27")
    assert r.returncode == 0 and "Survivor" in r.stdout


def test_journal_is_reachable_by_the_env_var_that_moves_the_store(tmp_path, monkeypatch):
    """If $WAYPOINTS_FILE does not redirect the journal too, a test appends to the REAL one.

    This asserts the RESOLVED path, not merely that a file appeared in tmp_path. An earlier
    version checked for the absence of `~/.claude/s-journal.jsonl` — a name nothing would ever
    write — so a redirect straight to the real journal passed it. Verified by mutation: point
    journal_path() at a hardcoded ~/.claude path and this test must go red.
    """
    import waypoints_core as core
    store = tmp_path / "s.json"
    monkeypatch.setenv("WAYPOINTS_FILE", str(store))
    resolved = core.journal_path()
    assert resolved == _journal_file(store)
    assert str(tmp_path) in resolved, "the journal escaped the test sandbox: %s" % resolved
    _run([CLI, "add", "Contained"], store, "2026-08-27")
    assert os.path.exists(_journal_file(store))


def test_journal_survives_the_backup_ring_evicting_snapshots(tmp_path):
    """The whole point of 0.5.0: snapshots may be evicted, history may not. Writes enough to
    overflow the (now smaller) ring, then asserts the oldest state is still recoverable from
    the journal even though its snapshot is gone."""
    import waypoints_core as core
    store = tmp_path / "s.json"
    _run([CLI, "add", "Original title"], store, "2026-08-27")
    for n in range(core.BACKUP_KEEP_RECENT + 5):
        _run([CLI, "edit", "original-title", "--title", "Rewrite %d" % n], store, "2026-08-27")
    snaps = os.listdir(os.path.splitext(str(store))[0] + "-backups")
    assert len(snaps) <= core.BACKUP_KEEP_RECENT + 1        # ring bounded (+ the day baseline)
    first = [e for e in _jlines(store) if e["changes"][0]["before"] is None][0]
    assert first["changes"][0]["after"]["title"] == "Original title"


def test_cli_journal_keeps_one_line_per_entry_despite_a_multiline_detail(tmp_path):
    """A --detail value is often paragraphs long. Printed verbatim it buries the timestamps and
    destroys the scannable layout, so the DISPLAY is shortened while the file keeps the raw argv."""
    store = tmp_path / "s.json"
    detail = "line one\n\nline two is quite a bit longer than sixty characters, easily so\nline three"
    _run([CLI, "add", "Big item", "--detail", detail], store, "2026-08-27")
    r = _run([CLI, "journal"], store, "2026-08-27")
    body = [l for l in r.stdout.split("\n") if "waypoints add" in l]
    assert len(body) == 1 and "line three" not in body[0] and "…" in body[0]
    # the raw value is untouched on disk -- shortening is a rendering choice, not a data loss
    assert _jlines(store)[-1]["argv"][-1] == detail


# ---------------------------------------------------------------------------------------
# 0.6.0 -- the public CLI: an extensionless launcher, a dashboard for the bare command, a
# compact title-only list, and pagination bounded by output size as well as item count.
#
# The compact default exists because the verbose render crossed Claude Code's inline-output
# ceiling: at ~148 items it was ~32.5 KB against a fixed ~30 KB boundary, so the tail became a
# saved file instead of something readable in place.
# ---------------------------------------------------------------------------------------

LAUNCHER = os.path.join(ROOT, "bin", "waypoints")


def _sh(argv, store, today=None):
    """Run the extensionless launcher (not python + the .py) so the shim itself is tested."""
    env = _env(store, today)
    return subprocess.run(argv, capture_output=True, text=True, env=env)


def _seed_tiers(store):
    _run([CLI, "add", "Decide the matrix"], store, "2026-08-31")
    _run([CLI, "add", "Phase 3 migration"], store, "2026-08-31")
    _run([CLI, "add", "Needs Photoshop"], store, "2026-08-31")
    _run([CLI, "triage", "decide-the-matrix", "--tier", "do-now"], store, "2026-08-31")
    _run([CLI, "triage", "needs-photoshop", "--tier", "gated",
          "--gate-reason", "ENV: Photoshop must be running"], store, "2026-08-31")
    _run([CLI, "triage", "phase-3-migration", "--tier", "waiting",
          "--waiting-on", "decide-the-matrix @ the matrix is decided"], store, "2026-08-31")


def test_extensionless_launcher_matches_the_py_entry_point(tmp_path):
    store = tmp_path / "s.json"
    _seed_tiers(store)
    assert os.access(LAUNCHER, os.X_OK)
    mode = subprocess.run(["git", "ls-files", "-s", "bin/waypoints"], cwd=ROOT,
                          capture_output=True, text=True).stdout
    assert mode.startswith("100755"), "the launcher must be mode 100755 in git, not just on disk"
    via_sh = _sh([LAUNCHER, "list"], store, "2026-08-31")
    via_py = _run([CLI, "list"], store, "2026-08-31")
    assert via_sh.returncode == 0
    assert via_sh.stdout == via_py.stdout, "waypoints.py stays a compatibility entry point"


def test_launcher_resolves_through_a_symlink_chain(tmp_path):
    store = tmp_path / "s.json"
    _seed_tiers(store)
    direct = _sh([LAUNCHER, "list"], store, "2026-08-31").stdout
    link = tmp_path / "abs-waypoints"
    link.symlink_to(LAUNCHER)
    chain = tmp_path / "chain-waypoints"
    chain.symlink_to(link)
    spaced_dir = tmp_path / "dir with spaces"
    spaced_dir.mkdir()
    spaced = spaced_dir / "waypoints"
    spaced.symlink_to(LAUNCHER)
    for label, l in (("absolute", link), ("two-deep chain", chain), ("path with spaces", spaced)):
        assert _sh([str(l), "list"], store, "2026-08-31").stdout == direct, label


def test_bare_command_is_a_dashboard_not_an_error(tmp_path):
    store = tmp_path / "s.json"
    _seed_tiers(store)
    r = _sh([LAUNCHER], store, "2026-08-31")
    assert r.returncode == 0, "a bare `waypoints` used to be an argparse error"
    assert "1 gated" in r.stdout and "1 waiting" in r.stdout
    assert "Commands:" in r.stdout and "waypoints show ID" in r.stdout
    # It must stay SMALL -- growing into the full list would hit the ceiling that made the
    # compact list necessary in the first place.
    assert len(r.stdout) < 2000
    assert r.stdout == _run([CLI, "dashboard"], store, "2026-08-31").stdout


def test_bare_command_on_an_empty_store_says_how_to_start(tmp_path):
    store = tmp_path / "s.json"
    r = _sh([LAUNCHER], store, "2026-08-31")
    assert r.returncode == 0 and "waypoints add" in r.stdout


def test_compact_list_is_grouped_with_waiting_in_its_own_section(tmp_path):
    store = tmp_path / "s.json"
    _seed_tiers(store)
    out = _run([CLI, "list"], store, "2026-08-31").stdout
    assert "ACTIONABLE" in out and "WAITING" in out and "GATED" in out
    # waiting sits BETWEEN actionable and gated -- not absorbed into either.
    assert out.index("ACTIONABLE") < out.index("WAITING") < out.index("GATED")
    # Compact means the gate reason is NOT in the default view...
    assert "Photoshop must be running" not in out
    # ...but the waiting TARGET is, because it is the whole value of the state.
    assert "decide-the-matrix @ the matrix is decided" in out
    assert "1 actionable" in out and "1 waiting" in out and "1 gated" in out
    assert "--waiting" in out, "the views stay discoverable from the default one"


def test_verbose_restores_everything_the_compact_view_moved(tmp_path):
    store = tmp_path / "s.json"
    _seed_tiers(store)
    out = _run([CLI, "list", "--verbose"], store, "2026-08-31").stdout
    assert "Photoshop must be running" in out
    assert "[gated]" in out


def test_long_titles_are_trimmed_in_compact_and_whole_in_verbose(tmp_path):
    store = tmp_path / "s.json"
    long_title = "T" + "i" * 300
    _run([CLI, "add", long_title], store, "2026-08-31")
    compact = _run([CLI, "list"], store, "2026-08-31").stdout
    verbose = _run([CLI, "list", "--verbose"], store, "2026-08-31").stdout
    assert "…" in compact and long_title not in compact
    assert long_title in verbose, "--verbose must not lose information"


def test_waiting_view_is_symmetric_with_the_other_views(tmp_path):
    store = tmp_path / "s.json"
    _seed_tiers(store)
    out = _run([CLI, "list", "--waiting"], store, "2026-08-31").stdout
    assert "phase-3-migration" in out
    assert "decide-the-matrix]" not in out and "needs-photoshop" not in out
    j = json.loads(_run([CLI, "list", "--json", "--waiting"], store, "2026-08-31").stdout)
    assert j["view"] == "waiting" and [i["id"] for i in j["items"]] == ["phase-3-migration"]
    # Counts still describe the WHOLE store, so a filtered view says what it is a subset of.
    assert j["counts"]["open"] == 3


def test_a_valid_target_outside_the_current_view_is_not_called_missing(tmp_path):
    # Regression: resolving a target against the FILTERED list reported a perfectly good
    # dependency as nonexistent, because the target sat outside the view.
    store = tmp_path / "s.json"
    _seed_tiers(store)
    out = _run([CLI, "list", "--waiting"], store, "2026-08-31").stdout
    assert "no such target" not in out and "does not exist" not in out


def test_triage_to_waiting_requires_a_milestone(tmp_path):
    store = tmp_path / "s.json"
    _seed_tiers(store)
    _run([CLI, "add", "Another"], store, "2026-08-31")
    bare = _run([CLI, "triage", "another", "--tier", "waiting"], store, "2026-08-31")
    assert bare.returncode == 2 and "refused" in bare.stdout
    no_milestone = _run([CLI, "triage", "another", "--tier", "waiting",
                         "--waiting-on", "decide-the-matrix"], store, "2026-08-31")
    assert no_milestone.returncode == 2 and "milestone" in no_milestone.stdout


def test_triage_warns_when_the_named_target_does_not_exist(tmp_path):
    store = tmp_path / "s.json"
    _seed_tiers(store)
    _run([CLI, "add", "Orphan"], store, "2026-08-31")
    r = _run([CLI, "triage", "orphan", "--tier", "waiting",
              "--waiting-on", "ghost-item @ never"], store, "2026-08-31")
    assert r.returncode == 0, "recorded, not refused -- the target may be added later"
    assert "no item with that id" in r.stdout


def test_closing_a_target_releases_what_waited_on_it(tmp_path):
    store = tmp_path / "s.json"
    _seed_tiers(store)
    r = _run([CLI, "done", "decide-the-matrix"], store, "2026-08-31")
    assert "released 1 item(s)" in r.stdout and "phase-3-migration" in r.stdout
    assert "UNTRIAGED on purpose" in r.stdout
    j = json.loads(_run([CLI, "list", "--json"], store, "2026-08-31").stdout)
    dep = [i for i in j["items"] if i["id"] == "phase-3-migration"][0]
    assert dep["tier"] is None and dep["waiting_on"] is None
    assert any("RELEASED" in b for b in dep["summary"])


def test_resolve_reports_stale_targets_and_releases_nothing_prematurely(tmp_path):
    store = tmp_path / "s.json"
    _seed_tiers(store)
    _run([CLI, "add", "Orphan"], store, "2026-08-31")
    _run([CLI, "triage", "orphan", "--tier", "waiting",
          "--waiting-on", "ghost-item @ never"], store, "2026-08-31")
    r = _run([CLI, "resolve"], store, "2026-08-31")
    assert r.returncode == 0
    assert "nothing released" in r.stdout
    assert "ghost-item" in r.stdout and "Not repaired" in r.stdout
    # Untouched.
    j = json.loads(_run([CLI, "list", "--json"], store, "2026-08-31").stdout)
    assert [i for i in j["items"] if i["id"] == "orphan"][0]["tier"] == "waiting"


def test_resolve_releases_a_target_that_landed_by_other_means(tmp_path):
    store = tmp_path / "s.json"
    _seed_tiers(store)
    # Simulate the store drifting (an older version, or a hand edit) rather than a `done` call.
    raw = json.loads(store.read_text())
    for i in raw["items"]:
        if i["id"] == "decide-the-matrix":
            i["done"] = True
    store.write_text(json.dumps(raw))
    r = _run([CLI, "resolve"], store, "2026-08-31")
    assert "released 1 waiting item(s)" in r.stdout and "phase-3-migration" in r.stdout


def _walk_pages(store, extra, budget):
    """Every page at a given budget: (pages, items_seen, silent_breaches, multi_breaches)."""
    page, seen, silent, multi = 1, 0, 0, 0
    while True:
        out = _run([CLI, "list", "--max-chars", str(budget), "--page", str(page)] + extra,
                   store, "2026-08-31").stdout
        if "past the end" in out:
            break
        size = len(out.rstrip("\n").encode("utf-8"))
        if size > budget:
            if "could not be honoured for these" in out:
                multi += 1
            elif "could not be honoured for this single item" not in out:
                silent += 1
        seen += sum(1 for l in out.splitlines()
                    if l.startswith(("  ▶ [", "  · [", "  ⏳ [", "  ⛔ [", "  ✓ [")))
        if "Next: " not in out:
            break
        page += 1
    return page, seen, silent, multi


def test_pagination_never_loses_an_item_and_never_breaches_silently(tmp_path):
    store = tmp_path / "s.json"
    for n in range(40):
        _run([CLI, "add", f"Item {n} " + "padding " * (n % 7)], store, "2026-08-31")
    for budget in (600, 1200, 4000, 26000):
        pages, seen, silent, multi = _walk_pages(store, [], budget)
        assert seen == 40, f"budget {budget} lost items ({seen} of 40)"
        assert silent == 0, f"budget {budget} breached its ceiling without saying so"
        assert multi == 0, f"budget {budget} put several items on an over-budget page"


def test_a_page_carries_at_least_one_whole_item_even_under_an_absurd_budget(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "A" * 400], store, "2026-08-31")
    out = _run([CLI, "list", "--max-chars", "1"], store, "2026-08-31").stdout
    assert "[a" in out or "AAAA" in out, "the item must still ship -- never unreachable"
    assert "could not be honoured" in out, "and the breach must be stated, not hidden"


def test_limit_and_page_and_the_next_page_command(tmp_path):
    store = tmp_path / "s.json"
    for n in range(10):
        _run([CLI, "add", f"Item {n}"], store, "2026-08-31")
    p1 = _run([CLI, "list", "--limit", "4"], store, "2026-08-31").stdout
    assert p1.count("] Item ") == 4
    assert "Showing 1-4 of 10." in p1
    assert "--limit 4 --page 2" in p1, "the footer gives the exact next-page command"
    p3 = _run([CLI, "list", "--limit", "4", "--page", "3"], store, "2026-08-31").stdout
    assert p3.count("] Item ") == 2 and "Showing 9-10 of 10." in p3
    assert "Next: " not in p3
    past = _run([CLI, "list", "--limit", "4", "--page", "9"], store, "2026-08-31").stdout
    assert "past the end" in past and "10 item(s)" in past


def test_a_split_section_is_marked_continued(tmp_path):
    store = tmp_path / "s.json"
    for n in range(6):
        _run([CLI, "add", f"Item {n}"], store, "2026-08-31")
    p2 = _run([CLI, "list", "--limit", "3", "--page", "2"], store, "2026-08-31").stdout
    assert "(continued)" in p2, "a page must not be mistaken for the whole group"


def test_all_removes_both_limits(tmp_path):
    store = tmp_path / "s.json"
    for n in range(10):
        _run([CLI, "add", f"Item {n}"], store, "2026-08-31")
    out = _run([CLI, "list", "--all"], store, "2026-08-31").stdout
    assert out.count("] Item ") == 10 and "Showing" not in out


def test_json_is_never_paginated(tmp_path):
    store = tmp_path / "s.json"
    for n in range(10):
        _run([CLI, "add", f"Item {n}"], store, "2026-08-31")
    j = json.loads(_run([CLI, "list", "--json", "--limit", "2", "--max-chars", "50"],
                        store, "2026-08-31").stdout)
    assert len(j["items"]) == 10, "silently paginated JSON would not be a contract"


def test_banner_marks_waiting_items_and_names_their_target(tmp_path):
    store = tmp_path / "s.json"
    _seed_tiers(store)
    banner = json.loads(_run([HOOK], store, "2026-08-31").stdout)["systemMessage"]
    assert "⏳" in banner
    # The target is shown even in the banner: "parked, but on what" is the whole question.
    assert "decide-the-matrix @ the matrix is decided" in banner
    # Counted SEPARATELY from gated -- gated needs the reader to act, waiting needs nobody, so
    # merging them would tell the reader they owe an answer they do not owe.
    assert "1 waiting on another item" in banner and "nothing for you to do" in banner


def test_banner_flags_a_waiting_item_whose_target_already_landed(tmp_path):
    store = tmp_path / "s.json"
    _seed_tiers(store)
    raw = json.loads(store.read_text())
    for i in raw["items"]:
        if i["id"] == "decide-the-matrix":
            i["done"] = True          # drift: closed without going through `done`
    store.write_text(json.dumps(raw))
    banner = json.loads(_run([HOOK], store, "2026-08-31").stdout)["systemMessage"]
    assert "can move NOW" in banner and "resolve" in banner


def test_banner_says_nothing_about_waiting_when_there_is_none(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "Just a thing"], store, "2026-08-31")
    banner = json.loads(_run([HOOK], store, "2026-08-31").stdout)["systemMessage"]
    assert "waiting" not in banner and "⏳" not in banner


def test_waiting_on_is_repeatable_on_the_command_line(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "Target A"], store, "2026-09-01")
    _run([CLI, "add", "Target B"], store, "2026-09-01")
    _run([CLI, "add", "Dependent"], store, "2026-09-01")
    r = _run([CLI, "triage", "dependent", "--tier", "waiting",
              "--waiting-on", "target-a @ its API freezes",
              "--waiting-on", "target-b @ the matrix is decided"], store, "2026-09-01")
    assert r.returncode == 0
    assert "target-a @ its API freezes + target-b @ the matrix is decided" in r.stdout
    j = json.loads(_run([CLI, "list", "--json"], store, "2026-09-01").stdout)
    dep = [i for i in j["items"] if i["id"] == "dependent"][0]
    assert dep["waiting_on"] == ["target-a @ its API freezes",
                                 "target-b @ the matrix is decided"]
    # Closing ONE of the two must not release it.
    _run([CLI, "done", "target-a"], store, "2026-09-01")
    j = json.loads(_run([CLI, "list", "--json"], store, "2026-09-01").stdout)
    assert [i for i in j["items"] if i["id"] == "dependent"][0]["tier"] == "waiting"
    r = _run([CLI, "done", "target-b"], store, "2026-09-01")
    assert "released 1 item(s)" in r.stdout


def test_compact_list_shows_every_target_of_a_multi_target_wait(tmp_path):
    store = tmp_path / "s.json"
    _run([CLI, "add", "Target A"], store, "2026-09-01")
    _run([CLI, "add", "Target B"], store, "2026-09-01")
    _run([CLI, "add", "Dependent"], store, "2026-09-01")
    _run([CLI, "triage", "dependent", "--tier", "waiting",
          "--waiting-on", "target-a @ freeze", "--waiting-on", "target-b @ decide"],
         store, "2026-09-01")
    out = _run([CLI, "list"], store, "2026-09-01").stdout
    assert "target-a @ freeze + target-b @ decide" in out

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
    # prune drops the done item
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
    assert p["contract"] == 1
    assert p["generated"] == "2026-07-12"
    assert set(p["counts"]) == {"total", "open", "done", "surfaceable", "gated",
                                "actionable", "untriaged"}
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

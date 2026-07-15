import json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(ROOT, "hooks", "waypoints.py")
CLI = os.path.join(ROOT, "bin", "waypoints.py")


def _env(store, today=None):
    e = dict(os.environ, WAYPOINTS_FILE=str(store))
    if today:
        e["WAYPOINTS_TODAY"] = today
    return e


def _run(argv, store, today=None):
    return subprocess.run([sys.executable] + argv, capture_output=True, text=True, env=_env(store, today))


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

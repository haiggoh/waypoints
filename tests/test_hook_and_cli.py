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

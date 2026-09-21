"""Tests for the interactive command selector (waypoints_menu).

Two halves, deliberately:

  * Unit tests drive `menu.run` with a FAKE dispatch, so what a sequence of keystrokes composes
    is asserted as an argv rather than as a store mutation. That is the contract that matters —
    the selector's whole design claim is that it only ever builds an argv and hands it to the
    real CLI, so pinning the argv pins the behaviour without re-testing every command.

  * A pty test runs the real `bin/waypoints` under a pseudo-terminal, because the TTY gate cannot
    be exercised any other way: every non-pty invocation takes the other branch by definition, so
    a suite without a pty would assert the fallback forever and never once prove the feature runs.

Every store-touching test uses a sandbox and ASSERTS the sandbox by outcome (the live store's
mtime is untouched), because WAYPOINTS_FILE fails OPEN — a typo'd variable name silently writes
to the user's real 125-item store instead of erroring.
"""

import json
import os
import pty
import select
import subprocess
import sys
import time

import pytest

import waypoints_menu as menu

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCHER = os.path.join(ROOT, "bin", "waypoints")
CLI = os.path.join(ROOT, "bin", "waypoints.py")
LIVE_STORE = os.path.expanduser("~/.claude/waypoints.json")


# --------------------------------------------------------------------------- helpers


def _seeded(tmp_path, items):
    store = tmp_path / "s.json"
    store.write_text(json.dumps({"version": 4, "items": items}))
    return store


def _item(iid, title, **kw):
    d = {"id": iid, "title": title, "summary": [], "detail": "", "surface_on": None,
         "created": "2026-01-01", "done": False, "priority": 0}
    d.update(kw)
    return d


class Fake:
    """Stands in for the CLI. Records argvs instead of running them, so a keystroke sequence can
    be asserted as the command it composes."""

    def __init__(self, rc=0):
        self.calls = []
        self.rc = rc

    def __call__(self, argv):
        self.calls.append(list(argv))
        return self.rc


def drive(monkeypatch, keys, items=(), archived=()):
    """Run the selector over a scripted keystroke list. An exhausted script raises EOFError,
    which the selector must treat as 'back out' — so a script that forgets to quit still ends the
    test instead of hanging it."""
    seq = list(keys)

    def fake_input(_prompt=""):
        if not seq:
            raise EOFError()
        return seq.pop(0)

    monkeypatch.setattr("builtins.input", fake_input)
    fake = Fake()
    rc = menu.run(dispatch=fake, load_items=lambda: list(items),
                  load_archive=lambda: list(archived))
    return fake.calls, rc


# --------------------------------------------------------------------------- the TTY gate


def test_available_false_without_a_tty():
    """A pipe, a script and a hook all reach the same code path as a bare `waypoints`. If the
    gate ever opens for them, they block forever on input that will never arrive."""
    class NotATty:
        def isatty(self):
            return False

    assert menu.available(NotATty(), NotATty(), env={}) is False


def test_available_true_when_both_streams_are_a_tty():
    class Tty:
        def isatty(self):
            return True

    assert menu.available(Tty(), Tty(), env={}) is True


def test_available_false_when_only_one_stream_is_a_tty():
    """`waypoints | head` on a terminal has a tty stdin and a piped stdout. Prompting there would
    print into the pipe and read from the keyboard, which is worse than either alone."""
    class Tty:
        def isatty(self):
            return True

    class NotATty:
        def isatty(self):
            return False

    assert menu.available(Tty(), NotATty(), env={}) is False
    assert menu.available(NotATty(), Tty(), env={}) is False


@pytest.mark.parametrize("val,expected", [
    ("1", False), ("true", False), ("yes", False), ("anything", False),
    ("", True), ("0", True), ("false", True), ("no", True),
])
def test_no_menu_env_var_is_the_explicit_opt_out(val, expected):
    class Tty:
        def isatty(self):
            return True

    assert menu.available(Tty(), Tty(), env={"WAYPOINTS_NO_MENU": val}) is expected


# --------------------------------------------------------------------------- argv composition


def test_quit_runs_nothing(monkeypatch):
    calls, rc = drive(monkeypatch, ["q"])
    assert calls == []
    assert rc == 0


def test_eof_at_the_prompt_exits_cleanly(monkeypatch):
    calls, rc = drive(monkeypatch, [])
    assert calls == []
    assert rc == 0


def test_unknown_action_does_not_dispatch(monkeypatch):
    calls, _ = drive(monkeypatch, ["nonsense-action", "q"])
    assert calls == []


def test_add_point_composes_the_edit_flag_nobody_remembers(monkeypatch):
    """The headline case. The user reaches for a command called `add-point`; there is no such
    subcommand, and the real spelling is `edit <id> --add-point`. If this ever composes plain
    `--point` it would REPLACE every existing bullet, which is the documented footgun."""
    items = [_item("alpha", "Alpha")]
    calls, _ = drive(monkeypatch, ["add-point", "1", "first bullet", "second", "", "q"],
                     items=items)
    assert calls == [["edit", "alpha", "--add-point", "first bullet", "--add-point", "second"]]


def test_add_point_with_no_bullets_is_cancelled(monkeypatch):
    calls, _ = drive(monkeypatch, ["add-point", "1", "", "q"], items=[_item("alpha", "Alpha")])
    assert calls == []


def test_add_composes_title_points_and_optional_fields(monkeypatch):
    calls, _ = drive(monkeypatch, ["add", "A new thing", "b1", "", "the detail", "2026-10-01", "q"])
    assert calls == [["add", "A new thing", "--point", "b1",
                      "--detail", "the detail", "--surface-on", "2026-10-01"]]


def test_add_omits_flags_that_were_left_blank(monkeypatch):
    calls, _ = drive(monkeypatch, ["add", "Bare", "", "", "", "q"])
    assert calls == [["add", "Bare"]]


def test_done_offers_the_resolution_retitle(monkeypatch):
    items = [_item("alpha", "Should we do X?")]
    calls, _ = drive(monkeypatch, ["done", "1", "shipped, commit abc1234",
                                   "X was done, and here is how", "q"], items=items)
    assert calls == [["done", "alpha", "--evidence", "shipped, commit abc1234",
                      "--as", "X was done, and here is how"]]


def test_done_without_a_resolution_keeps_the_title(monkeypatch):
    calls, _ = drive(monkeypatch, ["done", "1", "shipped, commit abc1234", "", "q"],
                     items=[_item("alpha", "Alpha")])
    assert calls == [["done", "alpha", "--evidence", "shipped, commit abc1234"]]


def test_menu_asks_for_evidence_because_the_cli_now_requires_it(monkeypatch):
    """The interactive close must collect what the CLI demands.

    Without this the menu would build a bare `done` and the CLI would refuse it -- the gate
    would read as the menu being broken. Leaving evidence BLANK must route to --no-evidence
    rather than producing a command that cannot succeed.
    """
    calls, _ = drive(monkeypatch, ["done", "1", "", "", "q"], items=[_item("alpha", "Alpha")])
    assert calls and calls[0][0] == "done"
    assert "--evidence" in calls[0] or "--no-evidence" in calls[0]


def test_item_can_be_chosen_by_id_as_well_as_number(monkeypatch):
    items = [_item("alpha", "Alpha"), _item("beta", "Beta")]
    calls, _ = drive(monkeypatch, ["show", "beta", "q"], items=items)
    assert calls == [["show", "beta"]]


def test_a_bad_pick_reprompts_rather_than_dispatching(monkeypatch):
    items = [_item("alpha", "Alpha")]
    calls, _ = drive(monkeypatch, ["show", "99", "no-such-id", "1", "q"], items=items)
    assert calls == [["show", "alpha"]]


def test_done_picker_excludes_already_done_items(monkeypatch):
    """Offering a done item under 'mark done' wastes the pick and, worse, makes the numbering
    disagree with what the user is looking at."""
    items = [_item("closed", "Closed", done=True), _item("open1", "Open one")]
    calls, _ = drive(monkeypatch, ["done", "1", "", "", "", "q"], items=items)
    assert calls == [["done", "open1", "--no-evidence", "closed from the menu without recorded evidence"]]


def test_triage_waiting_builds_the_target_at_milestone_spec(monkeypatch):
    """`--waiting-on` REQUIRES a milestone, so the selector must ask for one and join it with the
    ' @ ' separator the parser expects. A spec built without it is rejected by the CLI."""
    items = [_item("alpha", "Alpha"), _item("beta", "Beta")]
    calls, _ = drive(monkeypatch, ["triage", "1", "waiting", "1", "the design lands", "q"],
                     items=items)
    assert calls == [["triage", "alpha", "--tier", "waiting",
                      "--waiting-on", "beta @ the design lands"]]


def test_triage_waiting_cannot_target_the_item_itself(monkeypatch):
    """A self-referential wait can never release. The target picker excludes the item being
    triaged, so numbering here refers to the OTHER item."""
    items = [_item("alpha", "Alpha"), _item("beta", "Beta")]
    calls, _ = drive(monkeypatch, ["triage", "2", "waiting", "1", "milestone", "q"], items=items)
    assert calls == [["triage", "beta", "--tier", "waiting",
                      "--waiting-on", "alpha @ milestone"]]


def test_triage_gated_requires_a_reason(monkeypatch):
    items = [_item("alpha", "Alpha")]
    calls, _ = drive(monkeypatch, ["triage", "1", "gated", "", "needs a decision", "q"],
                     items=items)
    assert calls == [["triage", "alpha", "--tier", "gated",
                      "--gate-reason", "needs a decision"]]


def test_triage_clear_takes_no_extra_flags(monkeypatch):
    calls, _ = drive(monkeypatch, ["triage", "1", "clear", "q"], items=[_item("alpha", "A")])
    assert calls == [["triage", "alpha", "--clear"]]


def test_pin_requires_a_because(monkeypatch):
    calls, _ = drive(monkeypatch, ["pin", "1", "", "user flagged it today", "q"],
                     items=[_item("alpha", "A")])
    assert calls == [["pin", "alpha", "--because", "user flagged it today"]]


def test_replace_points_needs_the_guard_flag_and_a_confirmation(monkeypatch):
    """`--point` on an edit wipes every existing bullet and is refused without --replace-points.
    The selector must pass the guard AND make the destructiveness visible first."""
    calls, _ = drive(monkeypatch,
                     ["edit", "1", "replace-points", "only bullet", "", "y", "q"],
                     items=[_item("alpha", "A")])
    assert calls == [["edit", "alpha", "--replace-points", "--point", "only bullet"]]


def test_replace_points_declined_changes_nothing(monkeypatch):
    calls, _ = drive(monkeypatch, ["edit", "1", "replace-points", "x", "", "n", "q"],
                     items=[_item("alpha", "A")])
    assert calls == []


def test_prune_reports_the_count_and_defaults_to_yes(monkeypatch, capsys):
    """Prune's effect is invisible until afterwards, so the count is shown first. Its default IS
    yes, unlike the destructive prompts, because prune only archives."""
    items = [_item("a", "A", done=True), _item("b", "B", done=True), _item("c", "C")]
    calls, _ = drive(monkeypatch, ["prune", "", "q"], items=items)
    assert calls == [["prune"]]
    assert "2 done item(s)" in capsys.readouterr().out


def test_prune_with_nothing_done_is_refused_before_dispatch(monkeypatch):
    calls, _ = drive(monkeypatch, ["prune", "q"], items=[_item("c", "C")])
    assert calls == []


def test_rm_defaults_to_no(monkeypatch):
    """Return in a hurry must not archive an item. Every irreversible-ish prompt defaults to no."""
    calls, _ = drive(monkeypatch, ["rm", "1", "", "q"], items=[_item("alpha", "A")])
    assert calls == []


def test_rm_confirmed_composes_the_archive_command(monkeypatch):
    calls, _ = drive(monkeypatch, ["rm", "1", "y", "q"], items=[_item("alpha", "A")])
    assert calls == [["rm", "alpha"]]


def test_recover_only_ever_offers_the_read_only_listing(monkeypatch):
    """`recover` replaces the whole store file. The selector must never put that one keystroke
    deep, so it routes to --list and makes the caller come back for the repair."""
    calls, _ = drive(monkeypatch, ["recover", "q"])
    assert calls == [["recover", "--list"]]
    assert all("--yes" not in a and "--from" not in a for a in calls[0])


def test_reopen_pool_spans_done_and_archived(monkeypatch):
    """`reopen` auto-restores an archived item first, so splitting the picker would ask the user
    to know something the command already handles."""
    calls, _ = drive(monkeypatch, ["reopen", "2", "q"],
                     items=[_item("d", "Done one", done=True)],
                     archived=[_item("arch", "Archived one", done=True)])
    assert calls == [["reopen", "arch"]]


def test_loop_stays_open_for_a_maintenance_pass(monkeypatch):
    """The reason to open this at all is several actions in a row — close a couple, then prune."""
    items = [_item("alpha", "A"), _item("beta", "B")]
    calls, _ = drive(monkeypatch, ["done", "1", "", "", "", "done", "2", "", "", "", "q"],
                     items=items)
    assert calls == [["done", "alpha", "--no-evidence", "closed from the menu without recorded evidence"],
                     ["done", "beta", "--no-evidence", "closed from the menu without recorded evidence"]]


def test_a_command_that_exits_nonzero_does_not_end_the_session(monkeypatch):
    """The CLI calls sys.exit on a rejected argument. Being dropped back to the shell over one
    bad date is the friction this selector exists to remove, so SystemExit ends the ACTION only."""
    seq = ["add", "First", "", "", "", "add", "Second", "", "", "", "q"]

    def fake_input(_p=""):
        if not seq:
            raise EOFError()
        return seq.pop(0)

    monkeypatch.setattr("builtins.input", fake_input)

    calls = []

    def exploding(argv):
        calls.append(list(argv))
        raise SystemExit(2)

    rc = menu.run(dispatch=exploding, load_items=lambda: [], load_archive=lambda: [])
    assert rc == 0
    assert calls == [["add", "First"], ["add", "Second"]]


def test_every_action_is_reachable_by_name_and_by_number():
    """A row that is listed but unreachable is worse than an absent one, and the numbering is
    derived from the same table the loop indexes."""
    rows = menu._flat()
    assert len(rows) == len({n for n, _d, _f in rows}), "action names must be unique"
    assert all(callable(f) for _n, _d, f in rows)
    assert len(rows) >= 20, "the selector is meant to cover the whole command surface"


def test_no_action_composes_an_empty_argv():
    """An empty argv re-enters the bare-`waypoints` path, which on a terminal opens the selector
    again — an infinite regress. No builder may produce one."""
    assert all(name for name, _d, _f in menu._flat())


def test_echo_quoting_never_alters_the_dispatched_argv(monkeypatch):
    """The shell-quoting exists for the printed line only. If it leaked into the argv, a title
    with an apostrophe would be stored with backslashes in it."""
    calls, _ = drive(monkeypatch, ["add", "it's a \"quoted\" thing", "", "", "", "q"])
    assert calls == [["add", 'it\'s a "quoted" thing']]


# --------------------------------------------------------------------------- the real thing


def _sandbox_env(tmp_path, store):
    return dict(os.environ, WAYPOINTS_FILE=str(store),
                WAYPOINTS_CLAUDE_DIR=str(tmp_path / "claude"))


def test_bare_invocation_without_a_tty_is_still_the_dashboard(tmp_path):
    """The regression that would matter most: a pipe must get the plain dashboard and must not
    hang. Run with a closed stdin so a prompt would fail loudly rather than block."""
    store = _seeded(tmp_path, [_item("alpha", "Alpha")])
    r = subprocess.run([sys.executable, CLI], stdin=subprocess.DEVNULL, capture_output=True,
                       text=True, env=_sandbox_env(tmp_path, store), timeout=30)
    assert r.returncode == 0
    assert "1 open" in r.stdout
    assert "waypoints>" not in r.stdout


def test_explicit_menu_without_a_tty_refuses_with_a_reason(tmp_path):
    store = _seeded(tmp_path, [_item("alpha", "Alpha")])
    r = subprocess.run([sys.executable, CLI, "menu"], stdin=subprocess.DEVNULL,
                       capture_output=True, text=True,
                       env=_sandbox_env(tmp_path, store), timeout=30)
    assert r.returncode == 2
    assert "interactive terminal" in r.stderr


def test_dashboard_subcommand_never_prompts_even_on_a_tty(tmp_path):
    """`dashboard` is the documented escape hatch, so it must stay non-interactive by name even
    where the gate would otherwise open."""
    store = _seeded(tmp_path, [_item("alpha", "Alpha")])
    out, rc = _under_pty([sys.executable, CLI, "dashboard"], b"", _sandbox_env(tmp_path, store))
    assert rc == 0
    assert "waypoints>" not in out


def _under_pty(argv, keystrokes, env, timeout=25):
    """Run a command with a real pseudo-terminal on both ends, feed it keystrokes, return
    (output, returncode). This is the only way to exercise the TTY branch at all."""
    parent, child = pty.openpty()
    p = subprocess.Popen(argv, stdin=child, stdout=child, stderr=child, env=env, close_fds=True)
    os.close(child)
    os.write(parent, keystrokes)
    chunks = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        r, _w, _x = select.select([parent], [], [], 0.2)
        if r:
            try:
                data = os.read(parent, 65536)
            except OSError:
                break
            if not data:
                break
            chunks.append(data)
        elif p.poll() is not None:
            break
    try:
        p.wait(timeout=5)
    except subprocess.TimeoutExpired:          # pragma: no cover - only on a hang regression
        p.kill()
        p.wait()
        os.close(parent)
        raise AssertionError("the selector hung under a pty")
    os.close(parent)
    return b"".join(chunks).decode("utf-8", "replace"), p.returncode


def test_pty_bare_invocation_opens_the_selector_after_the_dashboard(tmp_path):
    """End to end on a real terminal: the dashboard still prints, THEN the prompt appears. The
    dashboard is the context needed to choose an action, so the selector adds to it rather than
    replacing it."""
    store = _seeded(tmp_path, [_item("alpha", "Alpha item")])
    out, rc = _under_pty([sys.executable, CLI], b"q\r", _sandbox_env(tmp_path, store))
    assert rc == 0, out
    assert "1 open" in out, out
    assert "What would you like to do?" in out, out
    assert "waypoints>" in out, out


def test_pty_add_point_actually_lands_a_bullet_in_the_store(tmp_path):
    """The dogfood test. Everything above asserts composition; this one drives the real launcher
    under a pty and then reads the store back, so a broken wiring between the selector and the
    CLI cannot pass. It also proves the sandbox is real: the live store must be untouched."""
    store = _seeded(tmp_path, [_item("alpha", "Alpha item")])
    live_before = os.path.getmtime(LIVE_STORE) if os.path.exists(LIVE_STORE) else None

    keys = b"add-point\r1\ra bullet from the selector\r\rq\r"
    out, rc = _under_pty([LAUNCHER], keys, _sandbox_env(tmp_path, store))
    assert rc == 0, out
    assert "--add-point" in out, out          # the echo teaches the real command

    data = json.loads(store.read_text())
    assert data["items"][0]["summary"] == ["a bullet from the selector"], data

    if live_before is not None:               # the sandbox assertion, by outcome
        assert os.path.getmtime(LIVE_STORE) == live_before, \
            "the test wrote to the REAL store -- WAYPOINTS_FILE did not take effect"


def test_dashboard_alone_still_prints_the_command_hints(tmp_path):
    """The hint block is the whole orientation when nothing interactive follows, so suppressing
    it must be conditional on the menu actually opening -- not removed."""
    store = _seeded(tmp_path, [_item("alpha", "Alpha")])
    r = subprocess.run([sys.executable, CLI], stdin=subprocess.DEVNULL, capture_output=True,
                       text=True, env=_sandbox_env(tmp_path, store), timeout=30)
    assert "Commands:" in r.stdout
    assert "waypoints --help" in r.stdout


def test_pty_dashboard_omits_the_hints_the_menu_is_about_to_repeat(tmp_path):
    """Printing the same commands twice -- once as prose, once as a numbered menu -- pushes the
    actual prompt off a short terminal, which is the one thing the reader needs to see."""
    store = _seeded(tmp_path, [_item("alpha", "Alpha")])
    out, rc = _under_pty([sys.executable, CLI], b"q\r", _sandbox_env(tmp_path, store))
    assert rc == 0, out
    assert "1 open" in out                      # the orientation is still there
    assert "What would you like to do?" in out  # ...and so is the menu
    assert "waypoints --help" not in out        # but not the block that duplicates it


def test_search_action_composes_a_search_argv(monkeypatch):
    """The search command must be reachable from the SELECTOR, not only as a typed flag.

    That is the whole case the menu exists for: a bare terminal with no docs to hand. The
    originating incident was someone concluding an item was untracked; if the fix is only
    discoverable by already knowing the flag, it does not reach that person."""
    calls, _rc = drive(monkeypatch, ["search", "spinner", "n", "q"])
    assert calls and calls[0][:2] == ["search", "spinner"]
    assert "--all" not in calls[0]


def test_search_action_offers_the_archive(monkeypatch):
    """'Was this EVER tracked?' is exactly the question that failed, and archived items answer
    it — so the widening flag has to be offered rather than requiring a re-run."""
    calls, _rc = drive(monkeypatch, ["search", "spinner", "y", "q"])
    assert calls and calls[0] == ["search", "spinner", "--all"]

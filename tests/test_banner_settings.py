"""0.15.0: pinned items get their own banner section with their own cap, pin reasons are trimmed
to a configurable number of lines, and all three banner limits are settable from a persisted
settings file (env var > settings file > default), surfaced in the interactive menu."""
import json
import os
import subprocess

import pytest

import waypoints_core as c
import waypoints_menu as m

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(ROOT, "bin", "waypoints.py")
HOOK = os.path.join(ROOT, "hooks", "waypoints.py")

LONG_REASON = ("the user asked for this one first because it unblocks a whole chain of later "
               "work and the cheap read-only half can start right away, while the expensive "
               "download waves stay gated behind the report it produces for later review")


def _flat(text):
    return " ".join(text.split())


def _store(n_open=0, n_pinned=0, reason="because"):
    items = []
    for k in range(n_open):
        c.add_item(items, "Open %d" % k, tier="do-now")
    for k in range(n_pinned):
        c.add_item(items, "Pinned %d" % k, tier="heavy")
        c.set_pinned(items, items[-1]["id"], True, reason)
    return items


def _banner(items, **kw):
    return c.format_banner(c.surfaceable(items, "2026-11-14"), ungate_hint=False, **kw)


def _bullets(out, marker):
    return [ln for ln in out.splitlines() if ln.startswith("  %s " % marker)]


# --- defaults ---------------------------------------------------------------------------------

def test_defaults_are_five_items_five_pins_two_pin_lines():
    assert c.get_setting("banner-items") == (5, "default")
    assert c.get_setting("banner-pinned") == (5, "default")
    assert c.get_setting("pin-lines") == (2, "default")


def test_default_banner_lists_five_unpinned_items():
    out = _banner(_store(n_open=40))
    assert len(_bullets(out, "•")) == 5
    assert "35 more open" in _flat(out)


# --- pinned section ---------------------------------------------------------------------------

def test_pinned_items_do_not_take_unpinned_slots():
    out = _banner(_store(n_open=40, n_pinned=5))
    assert len(_bullets(out, "📌")) == 5
    assert len(_bullets(out, "•")) == 5          # five pins did NOT crowd out the open list
    assert "35 more open" in _flat(out)          # residue counts unpinned items only


def test_pinned_section_has_its_own_cap_and_counts_the_rest():
    out = _banner(_store(n_open=2, n_pinned=8))
    assert len(_bullets(out, "📌")) == 5
    assert "3 more pinned" in _flat(out)
    assert "more open" not in out                # both open items are listed


def test_pinned_section_comes_before_the_open_list_regardless_of_priority():
    items = _store(n_open=3, n_pinned=1)
    items[0]["priority"] = 999                   # an unpinned item with a huge priority
    out = _banner(items).splitlines()
    first_pin = next(n for n, ln in enumerate(out) if ln.startswith("  📌 "))
    first_open = next(n for n, ln in enumerate(out) if ln.startswith("  • "))
    assert first_pin < first_open


def test_header_still_counts_every_open_item():
    out = _banner(_store(n_open=40, n_pinned=8))
    assert "48 open waypoint(s)" in out


def test_no_pinned_line_when_all_pins_fit():
    out = _banner(_store(n_open=1, n_pinned=2))
    assert "more pinned" not in out


# --- pin reason trimming ----------------------------------------------------------------------

def _pin_reason_lines(out):
    lines = out.splitlines()
    start = next(n for n, ln in enumerate(lines) if "PINNED —" in ln)
    end = next(n for n in range(start, len(lines)) if lines[n].strip().startswith("(since"))
    return lines[start:end]


def test_pin_reason_is_trimmed_to_two_lines_by_default_and_marked():
    out = _banner(_store(n_open=4, n_pinned=1, reason=LONG_REASON))
    reason = _pin_reason_lines(out)
    assert len(reason) == 2
    assert reason[-1].endswith("…")
    assert all(len(ln) <= c.BANNER_WIDTH for ln in reason)
    assert "show <id>" in _flat(out)             # the full reason is one command away


def test_pin_lines_full_keeps_the_whole_reason():
    out = _banner(_store(n_open=4, n_pinned=1, reason=LONG_REASON), pin_lines=None)
    assert "for later review" in _flat(out)
    assert not _pin_reason_lines(out)[-1].endswith("…")


def test_short_pin_reason_is_not_marked_trimmed():
    out = _banner(_store(n_open=4, n_pinned=1, reason="today"))
    assert len(_pin_reason_lines(out)) == 1
    assert "…" not in _pin_reason_lines(out)[0]


# --- settings resolution ----------------------------------------------------------------------

def test_settings_file_lives_next_to_the_store():
    assert c.settings_path() == os.path.splitext(c.store_path())[0] + "-settings.json"


def test_set_setting_persists_and_reports_file_source():
    c.set_setting("banner-items", "7")
    assert c.get_setting("banner-items") == (7, "file")
    with open(c.settings_path()) as f:
        assert json.load(f) == {"banner-items": 7}
    out = _banner(_store(n_open=40))
    assert len(_bullets(out, "•")) == 7


def test_pin_lines_full_round_trips_through_the_file():
    c.set_setting("pin-lines", "full")
    assert c.get_setting("pin-lines") == (None, "file")
    assert c.setting_display("pin-lines", None) == "full"


def test_env_overrides_the_file(monkeypatch):
    c.set_setting("banner-pinned", "4")
    monkeypatch.setenv("WAYPOINTS_BANNER_MAX_PINNED", "2")
    assert c.get_setting("banner-pinned") == (2, "env WAYPOINTS_BANNER_MAX_PINNED")


def test_empty_env_counts_as_unset(monkeypatch):
    monkeypatch.setenv("WAYPOINTS_BANNER_MAX_ITEMS", "")
    assert c.get_setting("banner-items") == (5, "default")


def test_unset_setting_returns_to_default():
    c.set_setting("banner-items", "9")
    c.unset_setting("banner-items")
    assert c.get_setting("banner-items") == (5, "default")


@pytest.mark.parametrize("key,bad", [("banner-items", "-1"), ("banner-items", "lots"),
                                     ("banner-pinned", "2.5"), ("pin-lines", "0"),
                                     ("pin-lines", "all")])
def test_set_setting_rejects_invalid_values(key, bad):
    with pytest.raises(c.SettingError) as e:
        c.set_setting(key, bad)
    assert key in str(e.value)
    assert not os.path.exists(c.settings_path())  # nothing written on a refusal


def test_unknown_key_is_refused():
    with pytest.raises(c.SettingError):
        c.set_setting("banner-colour", "3")


def test_invalid_env_fails_loudly_naming_the_variable(monkeypatch):
    monkeypatch.setenv("WAYPOINTS_BANNER_PIN_LINES", "zero")
    with pytest.raises(c.SettingError) as e:
        c.get_setting("pin-lines")
    assert "WAYPOINTS_BANNER_PIN_LINES" in str(e.value)


def test_invalid_file_value_fails_loudly_naming_file_and_key():
    with open(c.settings_path(), "w") as f:
        json.dump({"banner-items": "many"}, f)
    with pytest.raises(c.SettingError) as e:
        c.get_setting("banner-items")
    assert "banner-items" in str(e.value) and c.settings_path() in str(e.value)


def test_unparseable_settings_file_fails_loudly():
    with open(c.settings_path(), "w") as f:
        f.write("{not json")
    with pytest.raises(c.SettingError) as e:
        c.get_setting("banner-items")
    assert c.settings_path() in str(e.value)


def test_set_setting_keeps_other_keys():
    c.set_setting("banner-items", "3")
    c.set_setting("pin-lines", "4")
    with open(c.settings_path()) as f:
        assert json.load(f) == {"banner-items": 3, "pin-lines": 4}


# --- CLI + hook (subprocess) ------------------------------------------------------------------

def _run(path, *args, env=None):
    return subprocess.run([path, *args], capture_output=True, text=True,
                          env=dict(os.environ, **(env or {})), input="")


def test_cli_config_set_then_get():
    r = _run(CLI, "config", "set", "banner-items", "6")
    assert r.returncode == 0, r.stderr
    r = _run(CLI, "config", "get")
    assert r.returncode == 0, r.stderr
    assert "banner-items" in r.stdout and "6" in r.stdout and "file" in r.stdout
    assert "banner-pinned" in r.stdout and "pin-lines" in r.stdout


def test_cli_config_set_invalid_exits_nonzero():
    r = _run(CLI, "config", "set", "pin-lines", "0")
    assert r.returncode != 0
    assert "pin-lines" in r.stderr


def test_cli_config_unset():
    _run(CLI, "config", "set", "banner-items", "6")
    r = _run(CLI, "config", "unset", "banner-items")
    assert r.returncode == 0, r.stderr
    assert "default" in _run(CLI, "config", "get", "banner-items").stdout


def test_hook_refuses_loudly_on_an_invalid_setting():
    _run(CLI, "add", "something open")
    r = _run(HOOK, env={"WAYPOINTS_BANNER_MAX_ITEMS": "lots"})
    assert r.returncode == 0                     # a SessionStart hook must not break the session
    assert "WAYPOINTS_BANNER_MAX_ITEMS" in r.stdout
    assert "something open" not in r.stdout      # no silently-defaulted banner


def test_hook_uses_the_persisted_setting():
    for k in range(9):
        _run(CLI, "add", "thing %d" % k)
    _run(CLI, "config", "set", "banner-items", "2")
    r = _run(HOOK)
    assert "7 more open" in _flat(r.stdout)


# --- menu -------------------------------------------------------------------------------------

def test_menu_has_a_settings_group_with_the_three_keys():
    groups = dict(m.ACTIONS)
    names = [name for name, _d, _fn in groups["settings"]]
    for key in ("banner-items", "banner-pinned", "pin-lines"):
        assert key in names


def test_menu_setting_action_builds_a_config_set(monkeypatch, capsys):
    monkeypatch.setattr(m, "_in", lambda prompt: "8")
    fn = {name: fn for name, _d, fn in m._flat()}["banner-items"]
    assert fn([], []) == ["config", "set", "banner-items", "8"]
    assert "current: 5 (default)" in capsys.readouterr().out

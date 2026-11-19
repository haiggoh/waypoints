"""0.16.0: the 'display' setting chooses where the open queue shows (banner | pane | both,
persisted next to the store with env > file > default). 'pane' drops the printed SessionStart
systemMessage but still hands the model its additionalContext; an invalid value fails
loudly rather than silently defaulting."""
import json
import os
import subprocess

import pytest

import waypoints_core as c
import waypoints_menu as m

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(ROOT, "bin", "waypoints.py")
HOOK = os.path.join(ROOT, "hooks", "waypoints.py")


def _flat(text):
    return " ".join(text.split())


def _run(path, *args, env=None):
    return subprocess.run([path, *args], capture_output=True, text=True,
                          env=dict(os.environ, **(env or {})), input="")


# --- settings resolution ----------------------------------------------------------------------

def test_default_display_is_banner():
    # 0.19.0: the printed banner is back as the default; the panel is opt-in (fullscreen auto).
    assert c.get_setting("display") == ("banner", "default")


def test_env_display_wins_over_the_file_and_names_the_env_var(monkeypatch):
    c.set_setting("display", "both")
    monkeypatch.setenv("WAYPOINTS_DISPLAY", "pane")
    assert c.get_setting("display") == ("pane", "env WAYPOINTS_DISPLAY")


def test_set_setting_normalises_display_to_lowercase():
    c.set_setting("display", "PANE")
    assert c.get_setting("display") == ("pane", "file")
    with open(c.settings_path()) as f:
        assert json.load(f) == {"display": "pane"}


def test_set_setting_refuses_an_invalid_display_value_without_writing():
    with pytest.raises(c.SettingError) as e:
        c.set_setting("display", "bogus")
    assert "display" in str(e.value)
    assert not os.path.exists(c.settings_path())


def test_unset_setting_returns_display_to_default():
    c.set_setting("display", "both")
    c.unset_setting("display")
    assert c.get_setting("display") == ("banner", "default")


def test_invalid_display_env_fails_loudly_naming_the_variable(monkeypatch):
    monkeypatch.setenv("WAYPOINTS_DISPLAY", "bogus")
    with pytest.raises(c.SettingError) as e:
        c.get_setting("display")
    assert "WAYPOINTS_DISPLAY" in str(e.value)


# --- CLI --------------------------------------------------------------------------------------

def test_cli_config_get_display_raw_prints_only_the_value():
    c.set_setting("display", "both")
    r = _run(CLI, "config", "get", "display", "--raw")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "both"


def test_cli_config_get_raw_without_a_key_exits_two():
    r = _run(CLI, "config", "get", "--raw")
    assert r.returncode == 2
    assert "--raw" in r.stderr and "needs one key" in r.stderr


def test_cli_config_set_invalid_display_exits_two():
    r = _run(CLI, "config", "set", "display", "bogus")
    assert r.returncode == 2
    assert "display" in r.stderr


# --- hook -------------------------------------------------------------------------------------

def test_hook_in_banner_mode_prints_system_message_and_sends_model_context():
    c.set_setting("display", "banner")   # 0.17.0: banner is opt-in now; pin it for this test
    _run(CLI, "add", "open thing")
    r = _run(HOOK)
    out = json.loads(r.stdout)
    assert "open waypoint" in _flat(out["systemMessage"])
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert isinstance(out["hookSpecificOutput"]["additionalContext"], str)


def test_hook_in_both_mode_prints_system_message_and_sends_model_context():
    c.set_setting("display", "both")
    c.set_setting("display", "both")
    _run(CLI, "add", "open thing")
    r = _run(HOOK)
    out = json.loads(r.stdout)
    assert "open waypoint" in _flat(out["systemMessage"])
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert isinstance(out["hookSpecificOutput"]["additionalContext"], str)


def test_hook_in_pane_mode_omits_printed_banner_but_keeps_model_context():
    c.set_setting("display", "pane")
    _run(CLI, "add", "open thing")
    r = _run(HOOK)
    out = json.loads(r.stdout)
    assert "systemMessage" not in out
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    ctx = _flat(out["hookSpecificOutput"]["additionalContext"])
    assert "open waypoint" in ctx
    assert "Display mode is 'pane'" in ctx


def test_hook_with_invalid_display_env_fails_loudly(monkeypatch):
    monkeypatch.setenv("WAYPOINTS_DISPLAY", "bogus")
    _run(CLI, "add", "open thing")
    r = _run(HOOK)
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert "banner NOT shown" in out["systemMessage"]


# --- menu -------------------------------------------------------------------------------------

def test_menu_settings_group_contains_a_display_entry():
    groups = dict(m.ACTIONS)
    names = [name for name, _d, _fn in groups["settings"]]
    assert "display" in names

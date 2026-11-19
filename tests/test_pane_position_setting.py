"""0.18.0: `pane-position` was removed (Claude Code decides where a pane sits). A settings file
that still holds it loads fine and is IGNORED with one note line, never an error; `config
get|set|unset pane-position` exits 2 naming the removal and writes nothing."""
import json
import os
import subprocess

import pytest

import waypoints_core as c

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(ROOT, "bin", "waypoints.py")


def _cli(*args, env=None):
    return subprocess.run([CLI, *args], capture_output=True, text=True,
                          env=dict(os.environ, **(env or {})), input="")


def _seed_settings_file(data):
    path = c.settings_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def test_settings_file_still_holding_pane_position_loads_fine():
    _seed_settings_file({"pane-position": "bottom", "display": "banner"})
    # a known key still resolves from the file; the removed key does not raise on load
    assert c.get_setting("display") == ("banner", "file")
    assert c.removed_setting_notes() == [
        "note: pane-position is no longer used (removed in 0.18.0) and is ignored"
    ]


def test_removed_setting_notes_empty_when_key_absent():
    assert c.removed_setting_notes() == []


def test_removed_setting_is_not_a_readable_value():
    _seed_settings_file({"pane-position": "top"})
    with pytest.raises(c.SettingError):
        c.get_setting("pane-position")


def test_cli_config_get_pane_position_exits_2_naming_removal():
    _seed_settings_file({"pane-position": "top"})
    r = _cli("config", "get", "pane-position")
    assert r.returncode == 2
    assert "pane-position" in r.stderr and "removed in 0.18.0" in r.stderr


def test_cli_config_set_pane_position_exits_2_and_writes_nothing():
    _seed_settings_file({"pane-position": "top"})
    r = _cli("config", "set", "pane-position", "left")
    assert r.returncode == 2
    assert "removed in 0.18.0" in r.stderr
    with open(c.settings_path()) as f:
        assert json.load(f) == {"pane-position": "top"}  # unchanged


def test_cli_config_unset_pane_position_exits_2():
    _seed_settings_file({"pane-position": "top"})
    r = _cli("config", "unset", "pane-position")
    assert r.returncode == 2
    assert "removed in 0.18.0" in r.stderr


def test_cli_config_prints_the_note_and_omits_the_removed_key_from_the_listing():
    _seed_settings_file({"pane-position": "bottom"})
    r = _cli("config", "get")
    assert r.returncode == 0
    note = "note: pane-position is no longer used (removed in 0.18.0) and is ignored"
    assert note in r.stdout
    # the removed key is not listed among the live settings (strip the note line first)
    assert "pane-position" not in r.stdout.replace(note, "")

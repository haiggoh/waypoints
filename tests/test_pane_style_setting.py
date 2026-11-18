"""0.16.0: 'pane-style' chooses the collapsed-row look in the Claude Code pane. The default is
'plain' (the chrome-free dim row); all six looks stay selectable; an unknown value fails loudly."""
import os
import subprocess

import pytest

import waypoints_core as c
import waypoints_menu as m

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(ROOT, "bin", "waypoints.py")
MOD = os.path.join(ROOT, "hooks", "register.tsx")


def _cli(*args, env=None):
    return subprocess.run([CLI, *args], capture_output=True, text=True,
                          env=dict(os.environ, **(env or {})), input="")


def test_default_pane_style_is_plain():
    assert c.get_setting("pane-style") == ("plain", "default")


def test_all_six_styles_are_selectable_and_persist():
    assert c.PANE_STYLES == ("native", "secondary", "plain", "links", "dark", "static")
    for style in c.PANE_STYLES:
        c.set_setting("pane-style", style.upper())
        assert c.get_setting("pane-style") == (style, "file")


def test_unknown_pane_style_is_refused_and_writes_nothing():
    with pytest.raises(c.SettingError) as e:
        c.set_setting("pane-style", "neon")
    assert "pane-style" in str(e.value) and "plain" in str(e.value)
    assert not os.path.exists(c.settings_path())


def test_invalid_env_pane_style_names_the_variable(monkeypatch):
    monkeypatch.setenv("WAYPOINTS_PANE_STYLE", "neon")
    with pytest.raises(c.SettingError) as e:
        c.get_setting("pane-style")
    assert "WAYPOINTS_PANE_STYLE" in str(e.value)


def test_env_pane_style_wins_over_the_file(monkeypatch):
    c.set_setting("pane-style", "dark")
    monkeypatch.setenv("WAYPOINTS_PANE_STYLE", "links")
    assert c.get_setting("pane-style") == ("links", "env WAYPOINTS_PANE_STYLE")


def test_cli_raw_prints_exactly_the_style():
    r = _cli("config", "get", "pane-style", "--raw")
    assert (r.returncode, r.stdout) == (0, "plain\n")


def test_cli_rejects_a_bad_style_with_exit_2():
    assert _cli("config", "set", "pane-style", "neon").returncode == 2


def test_menu_lists_pane_style_in_the_settings_group():
    keys = [k for g, rows in m.ACTIONS if g == "settings" for k, *_ in rows]
    assert "pane-style" in keys


def test_the_mod_knows_exactly_the_styles_the_cli_accepts():
    src = open(MOD, encoding="utf-8").read()
    block = src.split("const STYLES", 1)[1].split("= [", 1)[1].split("]", 1)[0]
    in_mod = [w.strip(" '\n,") for w in block.split("\n") if "'" in w]
    assert len(in_mod) == 6  # a parse that finds nothing must not pass
    assert tuple(in_mod) == c.PANE_STYLES

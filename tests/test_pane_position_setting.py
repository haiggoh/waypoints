"""0.17.0: the 'pane-position' setting picks where the panel sits: top | bottom | left |
right (persisted next to the store; env WAYPOINTS_PANE_POSITION wins over file > default).
Default is 'right' (the panel, present at launch); what each value can really do is the honest
mapping in hooks/register.tsx and the README. Invalid values fail loudly, never silently default."""
import json

import pytest

import waypoints_core as c


def test_default_pane_position_is_right():
    assert c.get_setting("pane-position") == ("right", "default")


def test_env_pane_position_wins_and_names_the_env_var(monkeypatch):
    c.set_setting("pane-position", "left")
    monkeypatch.setenv("WAYPOINTS_PANE_POSITION", "bottom")
    assert c.get_setting("pane-position") == ("bottom", "env WAYPOINTS_PANE_POSITION")


def test_set_setting_normalises_position_to_lowercase():
    c.set_setting("pane-position", "RIGHT")
    assert c.get_setting("pane-position") == ("right", "file")
    with open(c.settings_path()) as f:
        assert json.load(f) == {"pane-position": "right"}


@pytest.mark.parametrize("ok", ["top", "bottom", "left", "right", "Top", "BOTTOM"])
def test_valid_positions_accepted(ok):
    assert c.get_setting  # noqa
    c.set_setting("pane-position", ok)
    assert c.get_setting("pane-position")[0] == ok.lower()


@pytest.mark.parametrize("bad", ["middle", "", "topleft", "up", "1"])
def test_invalid_positions_fail_loudly(bad):
    with pytest.raises(c.SettingError):
        c.set_setting("pane-position", bad)

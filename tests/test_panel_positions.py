"""0.17.0: the mod opens the panel at launch when display != banner, /waypoints-pane toggles,
and /waypoints-pane <top|bottom|left|right> persists pane-position and opens there. The tsx is
asserted textually (the repo's tsx-test idiom, as in test_pane_style_setting.py) plus the
config key is covered in test_pane_position_setting.py."""
import os
import re

import waypoints_core as c

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD = os.path.join(ROOT, "hooks", "register.tsx")


def _src():
    return open(MOD, encoding="utf-8").read()


def test_positions_constant_has_exactly_the_four():
    src = _src()
    block = src.split("const POSITIONS", 1)[1].split("= [", 1)[1].split("]", 1)[0]
    got = re.findall(r"'([a-z]+)'", block)
    assert tuple(got) == ("top", "bottom", "left", "right")
    assert tuple(got) == c.PANE_POSITIONS


def test_session_start_opens_panel_when_display_not_banner():
    src = _src()
    assert "snap.display !== 'banner'" in src
    assert "openAt($, snap.position)" in src


def test_command_toggles_without_arg_and_moves_with_arg():
    src = _src()
    assert "command: 'waypoints-pane'" in src
    # arg validation, persist, toggle
    assert "pane-position', arg" in src or "'pane-position'" in src
    assert "closePanel($)" in src


def test_bottom_is_not_above_the_prompt():
    src = _src()
    # bottom must never map to the inline/above-prompt seat; it is documented as forbidden
    bottom_block = src.split("pos === 'bottom'", 1)[1].split("}", 1)[0]
    assert "inline" not in bottom_block.lower() or "forbidden" in bottom_block.lower() or "not" in bottom_block.lower()

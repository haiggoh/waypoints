"""0.18.0 removed pane positions and the status-line summary; 0.19.0 made the pane seat-driven
and opt-in in window mode. The pane behavior is tested on the real engine by
tests/mod/register.test.tsx (`claude plugin test .`): seat-driven launch, seat-dependent
height, four accordion groups, no truncation, plain toggle, no ui.status ever. This file keeps
a static guard (the mod source carries no position/status leftovers) and makes the pytest gate
run those mod tests, so they cannot be skipped by shipping with pytest alone.
"""
import os
import re
import shutil
import subprocess

import waypoints_core as c

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD = os.path.join(ROOT, "hooks", "register.tsx")


def test_mod_source_has_no_position_or_status_leftovers():
    src = open(MOD, encoding="utf-8").read()
    for token in ["ui.status", "POSITIONS", "pane-position", "InfoNotice", "unplaced",
                  "moveTo", "applyLine", "syncPlaced"]:
        assert token not in src, f"register.tsx still contains {token!r}"
    # the removal is documented in the no-argument message, not silent
    assert "removed in 0.18.0" in src


def test_removed_setting_is_out_of_the_table_but_known_as_removed():
    assert "pane-position" not in c.SETTINGS
    assert "pane-position" in c.REMOVED_SETTINGS


def test_mod_behavior_suite_passes_on_the_engine():
    claude = shutil.which("claude")
    assert claude, "claude CLI not on PATH: the mod tests (claude plugin test .) cannot run"
    ran = subprocess.run(
        [claude, "plugin", "test", ROOT],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=240,
    )
    out = ran.stdout + ran.stderr
    assert ran.returncode == 0, out[-4000:]
    m = re.search(r"Ran (\d+) tests? across", out)
    assert m and int(m.group(1)) >= 27, f"too few mod tests ran:\n{out[-2000:]}"
    assert re.search(r"\b0 fail\b", out), out[-2000:]

"""0.17.0 pane behavior is tested on the real engine by tests/mod/register.test.tsx
(`claude plugin test .`): honest seat mapping, toggle, group titles, one-line mode and the
never-sit rule, on the terminal and desktop surfaces. This file keeps the cross-language
parity check and makes the pytest gate run those mod tests, so they cannot be skipped by
shipping with pytest alone.
"""
import os
import re
import shutil
import subprocess

import waypoints_core as c

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD = os.path.join(ROOT, "hooks", "register.tsx")


def test_positions_constant_has_exactly_the_four():
    src = open(MOD, encoding="utf-8").read()
    block = src.split("const POSITIONS", 1)[1].split("= [", 1)[1].split("]", 1)[0]
    got = re.findall(r"'([a-z]+)'", block)
    assert tuple(got) == ("top", "bottom", "left", "right")
    assert tuple(got) == c.PANE_POSITIONS


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
    assert m and int(m.group(1)) >= 20, f"too few mod tests ran:\n{out[-2000:]}"
    assert re.search(r"\b0 fail\b", out), out[-2000:]

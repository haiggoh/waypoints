"""0.17.0: the printed SessionStart banner is OFF while the panel is active (display=pane),
ON for banner/both. The model always gets additionalContext. display=pane is the new default."""
import json
import os
import subprocess

import waypoints_core as c

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(ROOT, "bin", "waypoints.py")
HOOK = os.path.join(ROOT, "hooks", "waypoints.py")


def _run(path, *args, env=None):
    return subprocess.run([path, *args], capture_output=True, text=True,
                          env=dict(os.environ, **(env or {})), input="")


def _hook_with_display(mode):
    if mode is not None:
        c.set_setting("display", mode)
    _run(CLI, "add", "gating probe item")
    return json.loads(_run(HOOK).stdout)


def test_default_mode_is_pane_and_prints_no_banner():
    out = _hook_with_display(None)          # default is now pane
    assert "systemMessage" not in out, "panel default must not double-render the banner"
    assert "gating probe item" in out["hookSpecificOutput"]["additionalContext"]


def test_pane_mode_prints_no_banner_but_keeps_model_context():
    out = _hook_with_display("pane")
    assert "systemMessage" not in out
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert "gating probe item" in ctx and "NEVER hand-edit" in ctx


def test_banner_mode_prints_banner():
    out = _hook_with_display("banner")
    assert "gating probe item" in out["systemMessage"]


def test_both_mode_prints_banner_and_model_context():
    out = _hook_with_display("both")
    assert "gating probe item" in out["systemMessage"]
    assert "gating probe item" in out["hookSpecificOutput"]["additionalContext"]

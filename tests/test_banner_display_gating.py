"""0.19.0: the printed SessionStart banner is back ON by default (display=banner), OFF only for
display=pane. The model always gets additionalContext. The banner carries one hint line saying
how to switch (pane on / banner off)."""
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


def test_default_mode_is_banner_and_prints_banner():
    out = _hook_with_display(None)          # default is banner now
    assert "gating probe item" in out["systemMessage"]
    # the switch hint line is present in the DEFAULT mode too, not only on explicit banner
    assert "pane: /waypoints-pane" in out["systemMessage"]
    assert "banner off: ask Claude to set display=pane" in out["systemMessage"]
    assert "gating probe item" in out["hookSpecificOutput"]["additionalContext"]


def test_pane_mode_prints_no_banner_but_keeps_model_context():
    out = _hook_with_display("pane")
    assert "systemMessage" not in out
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert "gating probe item" in ctx and "NEVER hand-edit" in ctx


def test_banner_mode_prints_banner():
    out = _hook_with_display("banner")
    assert "gating probe item" in out["systemMessage"]


def test_banner_carries_the_switch_hint_line():
    out = _hook_with_display("banner")
    msg = out["systemMessage"]
    assert "pane: /waypoints-pane" in msg
    assert "banner off: ask Claude to set display=pane" in msg
    # the user-visible banner never carries a console command ANYWHERE (standing UX rule) —
    # check the whole message, not just the hint line (QC-4 finding: [-1] let earlier lines pass)
    assert "waypoints.py" not in msg


def test_both_mode_prints_banner_and_model_context():
    out = _hook_with_display("both")
    assert "gating probe item" in out["systemMessage"]
    assert "pane: /waypoints-pane" in out["systemMessage"]   # hint shows in both too
    assert "gating probe item" in out["hookSpecificOutput"]["additionalContext"]

import os, sys
# make the plugin-root modules (waypoints_core) importable from tests
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    """Point the store family AND the claude dir at tmp_path for EVERY test.

    THE LIVE STORE IS SACRED (~/.claude/waypoints.json holds the user's real open items; one
    unprotected test writes to it for real). Running every test against a temp store used to
    be a PER-TEST duty, and $WAYPOINTS_FILE fails OPEN -- unset means the REAL path -- so a
    test that forgot its env silently wrote the live store. This fixture makes the temp store
    the DEFAULT, so forgetting is safe: a test that sets nothing is isolated anyway.

    A test that sets its own $WAYPOINTS_FILE still wins -- env assignment in the test body
    happens after this fixture, and the subprocess helpers build on dict(os.environ, ...),
    which inherits the fixture's values and then applies the test's overrides on top.
    Subprocess children inherit os.environ, so the isolation covers the hook and the CLI too
    (proven by test_unprotected_test_cannot_reach_the_real_store).

    $WAYPOINTS_CLAUDE_DIR follows for the same reason: plugin_available() probes under it,
    and a probe must not read the real machine's registry from a test.
    """
    monkeypatch.setenv("WAYPOINTS_FILE", str(tmp_path / "waypoints.json"))
    monkeypatch.setenv("WAYPOINTS_CLAUDE_DIR", str(tmp_path / "claude"))

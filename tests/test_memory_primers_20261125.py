"""waypoints: run-5 §C memory primer (plan 2026-11-25-memory-plugin-primer, Task 4).

The SessionStart hook's additionalContext must carry the resume-find-swallowed-prompts
trigger vocabulary on BOTH lanes (localhost proxy + gateway base URL). RED until the
primer lines land in hooks/waypoints.py. A sandbox store (WAYPOINTS_FILE + temp HOME)
is seeded first because the hook emits nothing when the store is empty.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "hooks" / "waypoints.py"
CLI = ROOT / "bin" / "waypoints.py"

TOKENS = {
    "resume-history-jsonl": "history.jsonl",
    "resume-queue-operation": "queue-operation",
}
LANES = ["http://127.0.0.1:4147", "https://api.anthropic.com"]


def run_hook(tmp_path, base_url):
    store = tmp_path / "wp.json"
    env = dict(os.environ, HOME=str(tmp_path), WAYPOINTS_FILE=str(store),
               CLAUDE_PLUGIN_ROOT=str(ROOT), ANTHROPIC_BASE_URL=base_url)
    seed = subprocess.run([sys.executable, str(CLI), "add", "primer probe item"],
                          capture_output=True, text=True, env=env, timeout=30)
    assert seed.returncode == 0, seed.stderr
    p = subprocess.run([sys.executable, str(HOOK)], capture_output=True, text=True, env=env, timeout=30)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]


@pytest.mark.parametrize("slug,token", list(TOKENS.items()), ids=list(TOKENS))
def test_memory_primer_token_present(slug, token, tmp_path):
    ctx = run_hook(tmp_path, LANES[0])
    assert token in ctx, f"{slug}: {token!r} missing from hook additionalContext"


@pytest.mark.parametrize("base_url", LANES)
def test_memory_primer_tokens_on_lane(base_url, tmp_path):
    ctx = run_hook(tmp_path, base_url)
    missing = [t for t in TOKENS.values() if t not in ctx]
    assert not missing, f"lane {base_url}: missing {missing}"

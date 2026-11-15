"""Wave C waypoints writer safety: single-writer lock + corrupt-archive refusal.

The store is per-machine but multi-PROCESS (concurrent sessions share it), so a
read-modify-write without a lock can lose an update. The lock must be:
  - cross-process (fcntl.flock on a sidecar .lock file),
  - re-entrant within one process (the menu re-enters main per action),
  - loud when busy beyond a timeout (never a silent stall),
and read-only commands must NOT need it.
A corrupt ARCHIVE file must be REFUSED (quarantined, named), never read as silently empty —
the live store already behaves that way; the archive now must too.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import waypoints_core as c

CLI = ROOT / "bin" / "waypoints.py"


@pytest.fixture()
def store_env(tmp_path, monkeypatch):
    monkeypatch.setenv("WAYPOINTS_FILE", str(tmp_path / "waypoints.json"))
    monkeypatch.setenv("WAYPOINTS_TODAY", "2026-11-15")
    return tmp_path


def _cli(args, env, timeout=15):
    e = dict(os.environ)
    e.update(env)
    return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True,
                          env=e, timeout=timeout)


def test_store_lock_serializes_across_processes(store_env):
    lock = c.store_lock()
    with lock:  # held by THIS process
        probe = ("import sys; sys.path.insert(0, %r); import waypoints_core as c\n"
                 "import sys as s\n"
                 "try:\n"
                 "    with c.store_lock(timeout=0.5):\n"
                 "        print('ACQUIRED')\n"
                 "except Exception as e:\n"
                 "    print('BUSY'); s.exit(3)\n" % str(ROOT))
        r = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True,
                           env={**os.environ, "WAYPOINTS_FILE": os.environ["WAYPOINTS_FILE"]},
                           timeout=15)
        assert r.returncode == 3 and "BUSY" in r.stdout, (r.returncode, r.stdout, r.stderr)
    # released: the probe now acquires
    r = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True,
                       env={**os.environ, "WAYPOINTS_FILE": os.environ["WAYPOINTS_FILE"]},
                       timeout=15)
    assert r.returncode == 0 and "ACQUIRED" in r.stdout, (r.stdout, r.stderr)


def test_store_lock_is_reentrant_within_one_process(store_env):
    with c.store_lock():
        with c.store_lock():  # the menu re-enters main per action — must not deadlock
            pass


def test_mutating_command_waits_for_lock_readonly_does_not(store_env):
    env = dict(os.environ)
    with c.store_lock():
        # a read-only command must run while the lock is held
        r = _cli(["list"], env, timeout=10)
        assert r.returncode == 0, r.stderr
        # a mutating command must NOT complete while the lock is held
        try:
            _cli(["add", "locked probe"], env, timeout=1)
            raise AssertionError("mutating command completed while the lock was held")
        except subprocess.TimeoutExpired:
            pass
    r = _cli(["add", "after release"], env, timeout=15)
    assert r.returncode == 0, r.stderr
    store = c.load_store()
    assert any(i["title"] == "after release" for i in store["items"])


def test_corrupt_archive_is_refused_not_empty(store_env, tmp_path):
    arch = Path(c.archive_path())
    arch.parent.mkdir(parents=True, exist_ok=True)
    arch.write_text("{not json", encoding="utf-8")
    with pytest.raises(c.StoreCorrupt):
        c.load_archive()                      # strict by default now
    assert c.load_archive(strict=False) == {"version": c.VERSION, "items": []}
    env = dict(os.environ)
    r = _cli(["archive", "list"], env, timeout=15)
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert "corrupt" in (r.stderr + r.stdout).lower()

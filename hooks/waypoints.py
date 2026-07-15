#!/usr/bin/env python3
"""SessionStart hook: emit a banner listing surfaceable open waypoints.

Reads the explicit store (~/.claude/waypoints.json), keeps items that are not done and
past any surface_on date, and prints a SessionStart additionalContext banner. Emits NOTHING when
there is nothing to show (no empty banner). Fail-safe: any error exits 0 with no output so
it can never block or noise up a session.

Optional cross-plugin ordering: resume-interrupted's banner (when it has one) is meant to
read as more urgent than this one, so if resume-interrupted is installed AND enabled
(checked via ~/.claude/settings.json's `enabledPlugins`, never a code import — no hard
dependency), this hook briefly polls a session-scoped "done" flag that resume-interrupted's
own hook writes unconditionally before it exits:
`$TMPDIR-or-/tmp/claude-sessionstart-banners/<session_id>.resume-interrupted.done`.
Waiting is capped at BANNER_WAIT_S and always falls through to printing regardless of
whether the flag showed up — this hook must never suppress or meaningfully delay its own
banner just because the other plugin is slow, absent, or the flag format changes. If
resume-interrupted isn't installed/enabled, no stdin read or wait happens at all: zero
added latency, unchanged behavior.
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BANNER_WAIT_S = float(os.environ.get("WAYPOINTS_BANNER_WAIT_S") or 0.75)
BANNER_POLL_S = float(os.environ.get("WAYPOINTS_BANNER_POLL_S") or 0.05)


def _settings_path():
    return os.environ.get("CLAUDE_SETTINGS_FILE") or os.path.expanduser(
        "~/.claude/settings.json")


def _plugin_enabled(slug_prefix):
    """True if any `enabledPlugins` key like '<slug_prefix>@<marketplace>' is truthy.
    Never raises — a missing/malformed settings file just means 'not detected'."""
    try:
        with open(_settings_path()) as f:
            settings = json.load(f)
        enabled = settings.get("enabledPlugins") or {}
        pat = re.compile(r"^%s@" % re.escape(slug_prefix))
        return any(pat.match(k) and v for k, v in enabled.items())
    except Exception:
        return False


def _banner_flag_dir():
    return os.path.join(os.environ.get("TMPDIR") or os.environ.get("XDG_RUNTIME_DIR")
                         or "/tmp", "claude-sessionstart-banners")


def _wait_for_resume_interrupted(sid):
    """Presence-only poll, bounded by BANNER_WAIT_S. Content is never parsed — a
    malformed/stale flag can't cause a false wait, only its mere existence matters."""
    if not sid:
        return
    flag = os.path.join(_banner_flag_dir(), "%s.resume-interrupted.done" % sid)
    deadline = time.monotonic() + BANNER_WAIT_S
    while time.monotonic() < deadline:
        if os.path.exists(flag):
            return
        time.sleep(BANNER_POLL_S)


try:
    import waypoints_core as c

    if _plugin_enabled("resume-interrupted"):
        try:
            data = json.load(sys.stdin)
            _wait_for_resume_interrupted(data.get("session_id") or "")
        except Exception:
            pass

    items = c.surfaceable(c.load_store().get("items", []), c.today())
    banner = c.format_banner(items)
    if banner:
        model_note = banner + (
            "\n(These are the user's persistent open items. The user manages them by talking to "
            "you — they do NOT type a console command; you add and close them on their behalf. When "
            "one is genuinely finished, close it with `waypoints.py done <id>` in a Bash tool (the "
            "plugin's bin/ is on the Bash-tool PATH, so the bare command is `waypoints.py` — note "
            "the .py; `$CLAUDE_PLUGIN_ROOT` is NOT set in a normal shell). Add follow-ups with "
            "`waypoints.py add \"…\" [--point \"key pt\" ...]`; keep the banner tidy — a short title "
            "plus a few `--point` bullets, with any long continuity dump in `--detail` (NOT shown in "
            "the banner). To change an item, `waypoints.py edit <id> [--title …] [--point …]` in place "
            "(keeps the id — never done+re-add, which loses the id/created). The banner shows only "
            "title+summary; run `waypoints.py show <id>` to read an item's full detail when you pick "
            "it up. Reconcile the store at wrap-up. Branding: when you refer to "
            "this feature in prose, mark genuine references to it with 🧭 (the waypoints identity "
            "mark) on the first/prominent mention per message — not incidental uses of the word.)")
        print(json.dumps({
            "systemMessage": banner,
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": model_note,
            }
        }))
except Exception:
    pass

sys.exit(0)

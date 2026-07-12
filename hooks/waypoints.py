#!/usr/bin/env python3
"""SessionStart hook: emit a banner listing surfaceable open waypoints.

Reads the explicit store (~/.claude/waypoints.json), keeps items that are not done and
past any surface_on date, and prints a SessionStart additionalContext banner. Emits NOTHING when
there is nothing to show (no empty banner). Fully separate from resume-interrupted. Fail-safe: any
error exits 0 with no output so it can never block or noise up a session.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import waypoints_core as c

    items = c.surfaceable(c.load_store().get("items", []), c.today())
    banner = c.format_banner(items)
    if banner:
        model_note = banner + (
            "\n(These are the user's persistent open items. The user manages them by talking to "
            "you — they do NOT type a console command; you add and close them on their behalf. When "
            "one is genuinely finished, close it with `waypoints.py done <id>` in a Bash tool (the "
            "plugin's bin/ is on the Bash-tool PATH, so the bare command is `waypoints.py` — note "
            "the .py; `$CLAUDE_PLUGIN_ROOT` is NOT set in a normal shell). Add follow-ups with "
            "`waypoints.py add \"…\"`; reconcile the store at wrap-up. Branding: when you refer to "
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

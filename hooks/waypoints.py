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
            "\n(These are the user's persistent open items; help progress them and mark each "
            "done via `waypoints done <id>` when finished — reconcile the store at wrap-up.)")
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

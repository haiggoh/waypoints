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

# Wait cap for resume-interrupted's flag so its banner lands first. Trimmed 0.75->0.5 (v0.1.11):
# resume-interrupted writes its flag ALWAYS (even on clean sessions) and early-exit below breaks
# as soon as it appears, so the full cap only bites on a slow/racy startup — 0.5s keeps ordering
# headroom while shaving the worst case. Only resume-interrupted ordering matters (no-hidden-changes
# is rare). Both tunable via env. Poll tightened 0.05->0.03 so the flag is noticed sooner.
BANNER_WAIT_S = float(os.environ.get("WAYPOINTS_BANNER_WAIT_S") or 0.5)
BANNER_POLL_S = float(os.environ.get("WAYPOINTS_BANNER_POLL_S") or 0.03)


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

    try:
        all_items = c.load_store().get("items", [])
    except c.StoreCorrupt as e:
        # A corrupt store used to read as empty here, so the banner just VANISHED — the most
        # alarming possible state produced the least alarming output. Say it loudly instead,
        # to the user AND to the model, and exit 0 (never block a session).
        alarm = ("🧭 waypoints: THE STORE IS UNREADABLE — the open-items banner is missing "
                 "because the file could not be parsed, NOT because there is nothing open.\n"
                 + e.report())
        print(json.dumps({
            "systemMessage": alarm,
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": (
                    alarm + "\n(Tell the user their waypoints store is damaged and offer to run "
                    "`waypoints.py recover` in a Bash tool — it puts the newest backup that "
                    "parses back in place and journals the event. Do NOT hand-edit or "
                    "hand-repair the JSON, and do NOT add/close items until it is recovered: "
                    "the first write would make the loss canonical.)"),
            }
        }))
        sys.exit(0)
    items = c.surfaceable(all_items, c.today())
    # all_items (plus the archive) is the universe for resolving a waiting target -- see
    # format_banner. `items` alone would make every landed target look like a missing one.
    try:
        archived = c.load_archive().get("items", [])
    except Exception:
        archived = []
    banner = c.format_banner(items, all_items=all_items, archived=archived)
    if banner:
        model_note = banner + (
            # RULE ZERO, first because a model that decides the JSON is easier never reads as
            # far as the CLI usage below. 2026-09-03: one hand-edit made every item unreadable.
            "\nNEVER hand-edit ~/.claude/waypoints.json (or waypoints-archive.json). Every "
            "change goes through `waypoints.py`. One bad escape makes the WHOLE file unparseable, "
            "so all items are lost at once, not one. If the file already looks broken, do not fix "
            "it by hand — run `waypoints.py recover`."
            "\n(These are the user's persistent open items. The user manages them by talking to "
            "you — they do NOT type a console command; you add and close them on their behalf. When "
            "one is genuinely finished, close it with `waypoints.py done <id>` in a Bash tool (the "
            "plugin's bin/ is on the Bash-tool PATH, so the bare command is `waypoints.py` — note "
            "the .py; `$CLAUDE_PLUGIN_ROOT` is NOT set in a normal shell). Add follow-ups with "
            "`waypoints.py add \"…\" [--point \"key pt\" ...]`; keep the banner tidy — a short title "
            "plus a few `--point` bullets, with any long continuity dump in `--detail` (NOT shown in "
            "the banner). To ADD information to an existing item use `waypoints.py edit <id> --add-point \"…\"` (APPENDS, keeps what is there) — plain `--point` on an edit REPLACES every "
            "existing bullet and is refused unless you also pass `--replace-points`. "
            "To retitle, `waypoints.py edit <id> --title …` in place "
            "(keeps the id — never done+re-add, which loses the id/created). The banner shows only "
            "title+summary; run `waypoints.py show <id>` to read an item's full detail when you pick "
            "it up. The banner LISTS ONLY the highest-priority items and counts the rest — run "
            "`waypoints.py list` when you need the whole queue, and don't infer from the banner "
            "alone that an item is absent. To clear a stray or mistaken item use `waypoints.py rm "
            "<id>` (it ARCHIVES, never deletes, and works on an open item) rather than editing "
            "the store file by hand; `waypoints.py reopen <id>` brings back anything archived, in "
            "one step. `waypoints.py archive list` is the closed-item paper trail, and "
            "`waypoints.py journal [--id <id>]` is the append-only history of which command "
            "changed what — reach for it when something looks wrong rather than guessing. Permanent "
            "deletion exists but is deliberately obscure (`rm <id> --delete --confirm`, "
            "archive-only) — it destroys the record of how something resolved, so it is the user's "
            "call to make, never yours to volunteer. Reconcile the store at wrap-up. Branding: when you refer to "
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

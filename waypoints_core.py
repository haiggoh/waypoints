"""Pure, unit-testable core for the waypoints reminder.

No Claude/session dependency. I/O helpers (load/save/store_path/today) are thin and
env-overridable so the hook, the CLI, and the tests all share one implementation.

Store schema (`~/.claude/waypoints.json`, overridable via $WAYPOINTS_FILE):
    {"version": 1, "items": [
        {"id","title","detail","surface_on"(YYYY-MM-DD|null),"created"(YYYY-MM-DD),"done"(bool)}
    ]}

`surface_on` is the EARLIEST date an item should appear — NOT an expiry. An item surfaces on
and after that date and persists every session until explicitly marked done.
"""
import json
import os
import re
import tempfile
import textwrap
from datetime import date

VERSION = 1

# Sentinel for edit_item: distinguishes "caller didn't pass this field" (leave as-is) from
# "caller explicitly set it to None/empty" (e.g. clearing surface_on). Plain None can't do both.
_UNSET = object()


def store_path():
    return os.environ.get("WAYPOINTS_FILE") or os.path.expanduser(
        "~/.claude/waypoints.json")


def today():
    """Today as YYYY-MM-DD; overridable via $WAYPOINTS_TODAY (tests / manual)."""
    return os.environ.get("WAYPOINTS_TODAY") or date.today().isoformat()


def load_store(path=None):
    path = path or store_path()
    try:
        with open(path) as f:
            d = json.load(f)
        if not isinstance(d, dict) or not isinstance(d.get("items"), list):
            raise ValueError("bad shape")
        return d
    except FileNotFoundError:
        return {"version": VERSION, "items": []}
    except Exception:
        # Fail safe: a corrupt store must never break a session or lose data silently to a
        # crash. Return empty for reads; callers that write re-serialize valid data.
        return {"version": VERSION, "items": []}


def save_store(store, path=None):
    path = path or store_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # atomic write within the same dir
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(store, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def slugify(title, maxlen=30):
    """Kebab id from a title, capped at maxlen. Capping matters because a bloated title (the
    thing an `edit` command now prevents) would otherwise yield a monstrous, unusable id."""
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    if len(s) > maxlen:
        cut = s[:maxlen]
        if "-" in cut:
            cut = cut.rsplit("-", 1)[0]  # drop the partial trailing word for a clean boundary
        s = cut.strip("-")
    return s or "item"


def _unique_id(items, base):
    existing = {i.get("id") for i in items}
    if base not in existing:
        return base
    n = 2
    while f"{base}-{n}" in existing:
        n += 1
    return f"{base}-{n}"


def add_item(items, title, detail="", surface_on=None, created=None, id=None, summary=None):
    item = {
        "id": id or _unique_id(items, slugify(title)),
        "title": title,
        "summary": list(summary) if summary else [],  # short banner bullets (on-screen tier)
        "detail": detail or "",                        # full continuity dump (on-demand tier)
        "surface_on": surface_on,
        "created": created or today(),
        "done": False,
        "priority": 0,                                  # higher sorts earlier in the banner
    }
    items.append(item)
    return item


def get_item(items, item_id):
    """Return the item dict with this id, or None."""
    for i in items:
        if i.get("id") == item_id:
            return i
    return None


def edit_item(items, item_id, title=_UNSET, summary=_UNSET, detail=_UNSET, surface_on=_UNSET):
    """Update an existing item in place; only fields explicitly passed change. `id` and `created`
    are intentionally immutable — a stable id is the whole reason this exists (the old
    done+re-add workaround regenerated the id and lost the created date). Returns the item, or
    None if no such id. Pass surface_on=None to CLEAR a date (vs the _UNSET default = leave it)."""
    it = get_item(items, item_id)
    if it is None:
        return None
    if title is not _UNSET:
        it["title"] = title
    if summary is not _UNSET:
        it["summary"] = list(summary) if summary else []
    if detail is not _UNSET:
        it["detail"] = detail
    if surface_on is not _UNSET:
        it["surface_on"] = surface_on
    return it


def mark_done(items, item_id):
    for i in items:
        if i.get("id") == item_id:
            i["done"] = True
            return True
    return False


def reopen_item(items, item_id):
    """Undo `done` on an item (the inverse of mark_done). Returns True if found."""
    for i in items:
        if i.get("id") == item_id:
            i["done"] = False
            return True
    return False


def toggle_done(items, item_id):
    """Flip an item's done state. Returns the new state, or None if no such id."""
    for i in items:
        if i.get("id") == item_id:
            i["done"] = not i.get("done", False)
            return i["done"]
    return None


def set_priority(items, item_id, priority):
    """Set an item's priority (int; higher sorts earlier in the banner). Returns the item, or
    None if no such id."""
    it = get_item(items, item_id)
    if it is None:
        return None
    it["priority"] = priority
    return it


def reorder_item(items, item_id, position):
    """Move an item to a specific 0-based position within `items` (clamped to bounds). This
    changes list order directly rather than `priority` — for the rare case of wanting explicit
    manual ordering instead of a priority tier. Returns True if found."""
    for idx, i in enumerate(items):
        if i.get("id") == item_id:
            it = items.pop(idx)
            position = max(0, min(position, len(items)))
            items.insert(position, it)
            return True
    return False


def prune(items):
    """Return items with done ones removed."""
    return [i for i in items if not i.get("done")]


def surfaceable(items, today_str):
    """Items to show now: not done, and (undated OR surface_on <= today). ISO dates sort
    lexically, so a string <= comparison is correct. Sorted by priority descending (stable, so
    equal-priority items keep their list/insertion order)."""
    out = []
    for i in items:
        if i.get("done"):
            continue
        so = i.get("surface_on")
        if so and so > today_str:
            continue
        out.append(i)
    out.sort(key=lambda i: -i.get("priority", 0))
    return out


COMPACT_THRESHOLD = 3

# Wrap width for banner lines. Overridable ($WAYPOINTS_BANNER_WIDTH) for tests.
#
# Why 72 (not the terminal's real width, and not the old 100): the hook's output is NOT printed
# straight to the invoking tty. It's emitted as a JSON `systemMessage`/`additionalContext` string
# that Claude Code relays through its OWN message renderer, which reflows text at the user's LIVE
# pane width. So we wrap TWICE: once here (adding the hanging indent), then again by Claude Code's
# renderer if any line we emit is wider than the pane. That second wrap knows nothing about our
# indent spaces — it just breaks the raw stream at the pane edge, landing mid-indent/mid-word.
# That double-wrap is what made continuation lines ragged "only at some window widths."
#
# The real render width is UNKNOWABLE at hook-run time (shutil.get_terminal_size()/$COLUMNS
# reflect the hook subprocess's own stdio, not the chat pane), so we can't measure it. Instead we
# pick a width comfortably under the common 80-column terminal minimum: at 72 our pre-wrapped
# lines fit inside an 80-col pane with ~8 cols of slack, so the renderer never re-wraps them and
# the double-wrap simply stops happening in practice. The slack also absorbs the one wide glyph
# in the banner (🧭 is East-Asian-Wide = 2 display cols but textwrap counts it as 1); it sits only
# in the header, never inside a wrapped/indented continuation segment, so a 1-col miscount there
# is harmless within the slack.
BANNER_WIDTH = int(os.environ.get("WAYPOINTS_BANNER_WIDTH") or 72)


def _wrap(text, indent):
    """Wrap `text` at BANNER_WIDTH with continuation lines hanging-indented to align under the
    first line's text (not its bullet marker). We wrap ourselves — Claude Code's message renderer
    (which shows this banner) has no knowledge of our indent, and keeping every emitted line under
    a conservative width stops that renderer from re-wrapping (and thus mangling) our lines."""
    return textwrap.fill(text, width=BANNER_WIDTH, initial_indent=indent,
                          subsequent_indent=" " * len(indent))


def format_banner(items):
    """Banner text for the given (already-surfaceable) items, or '' if none.

    ids are intentionally NOT printed here — they read as a redundant restatement of the title
    right next to them; use `waypoints.py list`/`show <id>` to get an item's id when needed.
    Past COMPACT_THRESHOLD open items, sub-bullets are dropped (title only) to keep the banner
    skimmable; full detail stays one `waypoints.py show <id>` away."""
    if not items:
        return ""
    compact = len(items) > COMPACT_THRESHOLD
    header = (f"🧭 waypoints: {len(items)} open waypoint(s) still ahead — they persist until "
               f"done. Just ask me to add or complete one; disable via /plugin if unwanted:")
    lines = [_wrap(header, "")]
    if compact:
        lines.append(_wrap("(compact mode — run `waypoints.py show <id>` for an item's "
                            "sub-bullets)", "  "))
    bullet_indent = "  • "
    date_indent = " " * len(bullet_indent)
    for i in items:
        lines.append(_wrap(i["title"], bullet_indent))
        # The date always gets its own line, hanging-indented under the title, so its
        # placement/indentation is fixed regardless of title length or pane width --
        # unlike appending it to the title line, this needs no wrap heuristics.
        if i.get("created"):
            lines.append(_wrap(f"(since {i['created']})", date_indent))
        if not compact:
            for point in i.get("summary") or []:
                lines.append(_wrap(point, "      - "))
    return "\n".join(lines)

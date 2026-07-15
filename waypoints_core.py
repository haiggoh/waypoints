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


def slugify(title, maxlen=50):
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


def format_banner(items):
    """Banner text for the given (already-surfaceable) items, or '' if none.

    Past COMPACT_THRESHOLD open items, sub-bullets are dropped (title+id only) to keep the
    banner skimmable; full detail stays one `waypoints.py show <id>` away."""
    if not items:
        return ""
    compact = len(items) > COMPACT_THRESHOLD
    lines = [
        f"🧭 waypoints: {len(items)} open waypoint(s) still ahead — they persist until done. "
        f"Just ask me to add or complete one; disable via /plugin if unwanted:"
    ]
    if compact:
        lines.append("  (compact mode — run `waypoints.py show <id>` for an item's sub-bullets)")
    for i in items:
        since = f"  (since {i['created']})" if i.get("created") else ""
        lines.append(f"  • {i['title']}{since}  [{i['id']}]")
        if not compact:
            for point in i.get("summary") or []:
                lines.append(f"      - {point}")
    return "\n".join(lines)

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


def slugify(title):
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s or "item"


def _unique_id(items, base):
    existing = {i.get("id") for i in items}
    if base not in existing:
        return base
    n = 2
    while f"{base}-{n}" in existing:
        n += 1
    return f"{base}-{n}"


def add_item(items, title, detail="", surface_on=None, created=None, id=None):
    item = {
        "id": id or _unique_id(items, slugify(title)),
        "title": title,
        "detail": detail or "",
        "surface_on": surface_on,
        "created": created or today(),
        "done": False,
    }
    items.append(item)
    return item


def mark_done(items, item_id):
    for i in items:
        if i.get("id") == item_id:
            i["done"] = True
            return True
    return False


def prune(items):
    """Return items with done ones removed."""
    return [i for i in items if not i.get("done")]


def surfaceable(items, today_str):
    """Items to show now: not done, and (undated OR surface_on <= today). ISO dates sort
    lexically, so a string <= comparison is correct."""
    out = []
    for i in items:
        if i.get("done"):
            continue
        so = i.get("surface_on")
        if so and so > today_str:
            continue
        out.append(i)
    return out


def format_banner(items):
    """Banner text for the given (already-surfaceable) items, or '' if none."""
    if not items:
        return ""
    lines = [
        f"🧭 waypoints: {len(items)} open waypoint(s) still ahead — they persist until done. "
        f"Just ask me to add or complete one; disable via /plugin if unwanted:"
    ]
    for i in items:
        since = f"  (since {i['created']})" if i.get("created") else ""
        lines.append(f"  • {i['title']}{since}  [{i['id']}]")
    return "\n".join(lines)

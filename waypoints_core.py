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


# --- Optional triage verdict ----------------------------------------------------------------
# A verdict says how an item can be picked up: `do-now` (bounded and self-contained), `heavy`
# (doable alone but liable to sprawl), `gated` (needs something this store cannot supply).
#
# Both keys are ABSENT by default, not defaulted: an item nobody has assessed carries neither,
# so every store written before this existed stays valid with no migration. "Untriaged" is a
# real third state and NOT a synonym for actionable — an item nobody has looked at is not
# thereby known to be unblocked. Views keep the three separate for exactly that reason.
TIERS = ("do-now", "heavy", "gated")
GATED = "gated"
ACTIONABLE_TIERS = ("do-now", "heavy")


class VerdictError(ValueError):
    """An invalid tier, or a gate reason on an item that isn't gated."""


def validate_verdict(tier, gate_reason=None):
    """Raise VerdictError on a contradictory verdict; return (tier, gate_reason) unchanged.

    A gate reason on a non-gated item is refused rather than quietly stored: it would be a
    record that disagrees with itself, and the reason is what a reader acts on.
    """
    if tier is not None and tier not in TIERS:
        raise VerdictError("tier must be one of %s (got %r)" % (", ".join(TIERS), tier))
    if gate_reason and tier is not None and tier != GATED:
        raise VerdictError("a gate reason only applies to a %r item (tier is %r)" % (GATED, tier))
    return tier, gate_reason


def tier_of(item):
    """The item's tier, or None when it has never been triaged."""
    return item.get("tier")


def is_gated(item):
    return item.get("tier") == GATED


def is_actionable(item):
    return item.get("tier") in ACTIONABLE_TIERS


def is_untriaged(item):
    return item.get("tier") is None


def partition(items):
    """Split into the three verdict groups. Every item lands in exactly one, so the counts
    always add up to the input length — a reader can verify nothing was dropped."""
    return {"gated": [i for i in items if is_gated(i)],
            "actionable": [i for i in items if is_actionable(i)],
            "untriaged": [i for i in items if is_untriaged(i)]}


def set_verdict(items, item_id, tier=_UNSET, gate_reason=_UNSET):
    """Set or clear an item's verdict in place. Pass tier=None to clear the verdict entirely
    (which also drops any gate reason, since it would be orphaned). Returns the item, or None
    if no such id. Raises VerdictError on a contradictory combination."""
    it = get_item(items, item_id)
    if it is None:
        return None
    new_tier = it.get("tier") if tier is _UNSET else tier
    if gate_reason is _UNSET:
        # An inherited reason is only meaningful while the item stays gated. Retiering to
        # do-now/heavy drops it rather than erroring: the reason is orphaned by definition, so
        # demanding a second call to clear it would buy nothing. An EXPLICIT reason passed
        # alongside a non-gated tier is a different thing — a contradiction of intent — and
        # validate_verdict still refuses that.
        new_reason = it.get("gate_reason") if new_tier == GATED else None
    else:
        new_reason = gate_reason
    if new_tier is None:
        new_reason = None
    validate_verdict(new_tier, new_reason)
    # Absent, not null: a cleared verdict removes the keys so the item is byte-identical to
    # one that was never triaged. Anything else would leak a tombstone into the store.
    for key, val in (("tier", new_tier), ("gate_reason", new_reason)):
        if val:
            it[key] = val
        else:
            it.pop(key, None)
    return it


def add_item(items, title, detail="", surface_on=None, created=None, id=None, summary=None,
             tier=None, gate_reason=None):
    validate_verdict(tier, gate_reason)
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
    if tier:
        item["tier"] = tier
    if gate_reason:
        item["gate_reason"] = gate_reason
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


# Leading words that make a title read as an unanswered inquiry/decision rather than a task. A ✓
# on "Confirm X" / "Decide Y" hides the ANSWER (did it work? what was decided?), which is the
# prose-vs-status contradiction this guard exists to catch. Plain task imperatives (fix, add,
# build, publish, finish, run…) are intentionally NOT here — "Fix login bug ✓" reads fine as done.
_INQUIRY_LEADERS = frozenset({
    "confirm", "verify", "check", "test", "decide", "research", "investigate",
    "evaluate", "determine", "assess", "explore", "compare", "figure", "whether",
    "should", "head-to-head",
})


def looks_unresolved(title):
    """True if `title` reads as an open question/decision that a bare ✓ would leave contradictory.
    Pure and side-effect-free so the CLI guard and tests share one definition. Matches a trailing
    '?' or a leading inquiry/decision verb (see _INQUIRY_LEADERS)."""
    t = (title or "").strip()
    if not t:
        return False
    if t.rstrip().endswith("?"):
        return True
    first = re.split(r"[\s:]+", t.lower(), maxsplit=1)[0].strip(".,")
    return first in _INQUIRY_LEADERS


def mark_done(items, item_id, resolved_title=None):
    """Mark an item done. If `resolved_title` is given, rewrite the title to that resolution phrasing
    first (the one-call replacement for edit+done) — `id`/`created` stay immutable, same as `edit`.
    Returns True if the item existed."""
    for i in items:
        if i.get("id") == item_id:
            if resolved_title is not None:
                i["title"] = resolved_title
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


# --- Machine-readable list contract ---------------------------------------------------------
# LIST_CONTRACT is versioned INDEPENDENTLY of the store's own `version`. That separation is the
# whole point: a reader pins the output contract and the on-disk format stays free to change
# underneath it. Documenting the raw store file instead would couple every reader to internals.
LIST_CONTRACT = 1


def list_payload(items, today_str=None):
    """The `list --json` payload: a documented, stable view of the queue.

    Shape (contract 1):
      contract  int    — this contract's version, NOT the store's
      generated str    — the date the view was computed (surfaceability depends on it)
      counts    object — total, open, done, surfaceable, gated, actionable, untriaged
      items     array  — every item, in store order, each with:
                           id, title, summary[], detail, created, surface_on, done, priority,
                           surfaceable (bool, computed), tier (str|null), gate_reason (str|null)

    `tier`/`gate_reason` are always PRESENT here and null when unset — a consumer reading a
    view should not have to distinguish a missing key from a null one. In the STORE they stay
    absent; that asymmetry is deliberate and belongs to the boundary between the two.

    gated + actionable + untriaged == open, so a consumer can verify no item was dropped.
    """
    today_str = today_str or today()
    surf = {i["id"] for i in surfaceable(items, today_str)}
    open_items = [i for i in items if not i.get("done")]
    groups = partition(open_items)
    out = []
    for i in items:
        out.append({
            "id": i.get("id"),
            "title": i.get("title", ""),
            "summary": list(i.get("summary") or []),
            "detail": i.get("detail", ""),
            "created": i.get("created"),
            "surface_on": i.get("surface_on"),
            "done": bool(i.get("done")),
            "priority": i.get("priority", 0),
            "surfaceable": i.get("id") in surf,
            "tier": i.get("tier"),
            "gate_reason": i.get("gate_reason"),
        })
    return {
        "contract": LIST_CONTRACT,
        "generated": today_str,
        "counts": {
            "total": len(items),
            "open": len(open_items),
            "done": sum(1 for i in items if i.get("done")),
            "surfaceable": len(surf),
            "gated": len(groups["gated"]),
            "actionable": len(groups["actionable"]),
            "untriaged": len(groups["untriaged"]),
        },
        "items": out,
    }


COMPACT_THRESHOLD = 3

# Mirrors COMPACT_THRESHOLD: past this many GATED items the group collapses to one counted line
# rather than listing each. Set from COMPACT_THRESHOLD so the two stay consistent by default.
#
# What this deliberately does NOT do: reorder anything. Gated items keep their priority position
# among the rest and are marked in place — sorting them last would encode an assumption that
# something else consumes the other pile, i.e. a preference baked into the store's own output.
# Collapse triggers on GROUP LENGTH alone. The count stays visible either way, so a collapsed
# group is disclosed rather than hidden.
#
# The one apparent exception is not one: when the group DOES collapse, its items are not rendered
# at all, so there is no position left to preserve — the summary line lands at the end because
# that is where a summary belongs, not because gated work was demoted. Ordering is observable
# only in the un-collapsed case, and there it is untouched (see the no-reorder test).
GATED_COLLAPSE_THRESHOLD = int(os.environ.get("WAYPOINTS_GATED_COLLAPSE_THRESHOLD")
                                or COMPACT_THRESHOLD)

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
    # break_on_hyphens=False / break_long_words=False: this banner is full of hyphenated tokens
    # that MUST survive intact -- kebab-case item ids, `/slash-commands`, `--long-flags`. Default
    # textwrap happily splits `/waypoints-gated` into `/waypoints-` + `gated`, which the user then
    # cannot copy or run, and turns an id into two unrecognizable halves. Preferring a slightly
    # over-long line to a broken token is the right trade for output whose job is to be actioned.
    return textwrap.fill(text, width=BANNER_WIDTH, initial_indent=indent,
                          subsequent_indent=" " * len(indent),
                          break_on_hyphens=False, break_long_words=False)


def format_banner(items):
    """Banner text for the given (already-surfaceable) items, or '' if none.

    ids are intentionally NOT printed here — they read as a redundant restatement of the title
    right next to them; use `waypoints.py list`/`show <id>` to get an item's id when needed.
    Past COMPACT_THRESHOLD open items, sub-bullets are dropped (title only) to keep the banner
    skimmable; full detail stays one `waypoints.py show <id>` away.

    Gated items are marked ⛔ in place. Past GATED_COLLAPSE_THRESHOLD of them they collapse to a
    single counted line instead — the count is always stated, so nothing is silently dropped."""
    if not items:
        return ""
    gated = [i for i in items if is_gated(i)]
    collapse_gated = len(gated) > GATED_COLLAPSE_THRESHOLD
    shown = [i for i in items if not (collapse_gated and is_gated(i))] if collapse_gated else items
    compact = len(shown) > COMPACT_THRESHOLD
    header = (f"🧭 waypoints: {len(items)} open waypoint(s) still ahead — they persist until "
               f"done. Just ask me to add or complete one; disable via /plugin if unwanted:")
    lines = [_wrap(header, "")]
    if compact:
        lines.append(_wrap("(compact mode — run `waypoints.py show <id>` for an item's "
                            "sub-bullets)", "  "))
    bullet_indent = "  • "
    gated_indent = "  ⛔ "
    date_indent = " " * len(bullet_indent)
    for i in shown:
        lines.append(_wrap(i["title"], gated_indent if is_gated(i) else bullet_indent))
        # The date always gets its own line, hanging-indented under the title, so its
        # placement/indentation is fixed regardless of title length or pane width --
        # unlike appending it to the title line, this needs no wrap heuristics.
        if i.get("created"):
            lines.append(_wrap(f"(since {i['created']})", date_indent))
        if not compact:
            for point in i.get("summary") or []:
                lines.append(_wrap(point, "      - "))
            if is_gated(i) and i.get("gate_reason"):
                lines.append(_wrap(f"gated: {i['gate_reason']}", "      - "))
    if collapse_gated:
        lines.append(_wrap(f"⛔ {len(gated)} gated — each needs something before it can move. "
                            f"Run `/waypoints-gated` (or `waypoints.py list --gated`) to see them "
                            f"and why.", "  "))
    return "\n".join(lines)

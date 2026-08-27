"""Pure, unit-testable core for the waypoints reminder.

No Claude/session dependency. I/O helpers (load/save/archive_path/today) are thin and
env-overridable so the hook, the CLI, and the tests all share one implementation.

Store schema (`~/.claude/waypoints.json`, overridable via $WAYPOINTS_FILE):
    {"version": 1, "items": [
        {"id","title","detail","surface_on"(YYYY-MM-DD|null),"created"(YYYY-MM-DD),"done"(bool)}
    ]}

`surface_on` is the EARLIEST date an item should appear — NOT an expiry. An item surfaces on
and after that date and persists every session until explicitly marked done.

Items pass through four tiers of record-keeping:

    open      -> shown in the SessionStart banner
    done      -> in the live store, hidden from the banner, still reopenable
    archived  -> moved OUT of the live store into the archive file, still readable, restorable
    deleted   -> gone; reachable only from `archived`, only via the deliberate two-step

The closed list (done, then archived) is a deliberate PAPER TRAIL — used to reconstruct after
the fact where an error slipped in. So nothing that runs routinely destroys it, and permanent
deletion is an obscure command that cannot fire by accident.
"""
import datetime
import glob
import json
import os
import re
import shutil
import tempfile
import textwrap

VERSION = 1

# Sentinel for edit_item: distinguishes "caller didn't pass this field" (leave as-is) from
# "caller explicitly set it to None/empty" (e.g. clearing surface_on). Plain None can't do both.
_UNSET = object()


def store_path():
    return os.environ.get("WAYPOINTS_FILE") or os.path.expanduser(
        "~/.claude/waypoints.json")


def archive_path(store=None):
    """Where archived (closed-and-pruned) items live. Derived from the store path by suffix,
    so $WAYPOINTS_FILE overrides both — tests point the pair at tmp_path in one env var."""
    store = store or store_path()
    return os.path.splitext(store)[0] + "-archive.json"


# How many recent snapshots the ring keeps, beyond the per-day baselines. A wrap-up burst can
# write a dozen times in a minute, so this has to be comfortably larger than one burst or the
# burst evicts the pre-session state — the one snapshot most worth having.
BACKUP_KEEP_RECENT = 20

# How many day-baselines (the first snapshot of each calendar day) survive the ring. These are
# what make a burst non-destructive: promoting them out of the recent window means no amount of
# same-day churn can evict the state a day began in.
BACKUP_KEEP_DAILY = 30

# Only files matching this exact shape are ours, and ONLY ours are ever pruned. The store has
# hand-made neighbours (e.g. waypoints.json.bak-reconcile-20260731-025549 from a past session);
# a retention sweep that globbed loosely would delete those, destroying the very ad-hoc history
# this layer exists to replace. Strict naming is the guard.
#
# Shape: <source-stem>.<YYYYmmdd>-<HHMMSS>-<micros>[-n].json — the STEM matters. The store and the
# archive share one backup dir (one place to look, one policy), so without it their snapshots
# would be indistinguishable after the fact and the dedupe check could compare a store against an
# archive snapshot. Scoping by stem keeps the two histories separate inside the shared dir.
_BACKUP_RE = re.compile(r"^(?P<stem>.+)\.(?P<day>\d{8})-\d{6}-\d{6}(?:-\d{3})?\.json$")


def backup_dir(store=None):
    """The tool-owned snapshot directory. A DEDICATED dir (not siblings of the store) so that
    retention can never reach a file it did not create — see _BACKUP_RE."""
    store = store or store_path()
    return os.path.splitext(store)[0] + "-backups"


def today():
    """Today as YYYY-MM-DD; overridable via $WAYPOINTS_TODAY (tests / manual)."""
    return os.environ.get("WAYPOINTS_TODAY") or datetime.date.today().isoformat()


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


def _atomic_write(path, text):
    """Replace `path` atomically within its own directory."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


BACKUP_STAMP_FMT = "%Y%m%d-%H%M%S-%f"  # sub-second: see _backup_stamp


def _backup_stamp(when=None):
    """The snapshot name's time field, at MICROSECOND precision.

    O_EXCL already guarantees uniqueness, so this is not what prevents a clobber — it is what
    keeps names naturally ordered and collision-suffix-free. At second granularity a burst of
    twenty writes lands twenty items in one stamp and every one after the first needs a `-NNN`
    suffix, which is both unreadable and one more thing to sort correctly.
    """
    return (when or datetime.datetime.now()).strftime(BACKUP_STAMP_FMT)


def _backup_stem(path):
    """The source-file marker embedded in a snapshot's name (e.g. `waypoints`, `waypoints-archive`)."""
    return os.path.basename(os.path.splitext(path)[0])


def _existing_backups(directory, stem):
    """Our snapshots of ONE source file, oldest first. Anything not matching _BACKUP_RE, or
    belonging to another source, is invisible here — which is what makes retention safe."""
    out = []
    for p in glob.glob(os.path.join(directory, "*.json")):
        m = _BACKUP_RE.match(os.path.basename(p))
        if m and m.group("stem") == stem:
            out.append((os.path.basename(p), m.group("day"), p))
    out.sort()  # lexicographic == chronological, given the fixed-width stamp
    return out


def _unique_backup_path(directory, stem, stamp):
    """Mint a backup path that is GUARANTEED unused, and return it with an open fd.

    Second-granularity names collide: several writes inside one second produced one file and
    silently overwrote the earlier snapshots. Microseconds make a clash unlikely; O_EXCL makes
    it impossible by letting the filesystem arbitrate instead of a look-then-write race.
    """
    for n in range(1000):
        # ALWAYS suffixed, and zero-padded. Both matter for ordering, because _existing_backups
        # depends on lexicographic order meaning chronological order:
        #   - unpadded, "-10" sorts before "-2";
        #   - omitted on the first file, "<stamp>.json" sorts AFTER "<stamp>-001.json", since
        #     "-" (0x2D) < "." (0x2E) — so the earliest snapshot would look like the newest.
        tail = "%s-%03d" % (stamp, n)
        path = os.path.join(directory, "%s.%s.json" % (stem, tail))
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            continue
        return path, fd
    raise OSError("could not mint a unique backup name in %s" % directory)


def _prune_backups(directory, stem):
    """Bound the snapshot ring without losing the day-baselines.

    Keeps the newest BACKUP_KEEP_RECENT snapshots, PLUS the first snapshot of each of the most
    recent BACKUP_KEEP_DAILY days. The daily tier is what survives a burst: a wrap-up that
    closes fifteen items would otherwise push the pre-wrap-up state out of the window entirely.

    Scoped to ONE source stem, so the store's ring and the archive's ring are bounded
    independently. Only files matching _BACKUP_RE are considered, so a hand-made backup sitting
    nearby is invisible to this and cannot be deleted by it.
    """
    ours = _existing_backups(directory, stem)
    keep = {p for _, _, p in ours[-BACKUP_KEEP_RECENT:]}
    first_of_day = {}
    for name, day, path in ours:
        first_of_day.setdefault(day, path)
    for day in sorted(first_of_day)[-BACKUP_KEEP_DAILY:]:
        keep.add(first_of_day[day])
    removed = []
    for _, _, path in ours:
        if path not in keep:
            try:
                os.remove(path)
                removed.append(path)
            except OSError:
                pass
    return removed


def _backup_before_write(path, store_for_dir=None):
    """Snapshot the current file into the tool's backup dir before overwriting it.

    COPIES (shutil.copy2) rather than moves. A move would unlink the store for the instant
    between backup and rewrite: die in that window and the canonical path is simply absent,
    load_store reads empty, and the banner goes silently blank — strictly worse than the 0.3.0
    behaviour, where the original survived until the atomic replace. Copying keeps both the
    crash-safety floor and the recovery layer.

    Skips when the content is byte-identical to the newest snapshot: a no-op `edit` should not
    consume a ring slot, because slots are what protect the older states.

    Never raises. The backup is insurance, and a failed backup (permissions, full disk) must not
    wedge the write that asked for it.
    """
    if not os.path.exists(path):
        return None
    try:
        directory = backup_dir(store_for_dir or path)
        os.makedirs(directory, exist_ok=True)
        stem = _backup_stem(path)
        existing = _existing_backups(directory, stem)
        if existing:
            with open(path, "rb") as a, open(existing[-1][2], "rb") as b:
                if a.read() == b.read():
                    return None  # unchanged since the last snapshot — nothing new to protect
        stamp = _backup_stamp()
        dst, fd = _unique_backup_path(directory, stem, stamp)
        os.close(fd)
        shutil.copy2(path, dst)
        os.chmod(dst, 0o600)  # copy2 carries the source mode; pin it so a wide store cannot widen its backups
        _prune_backups(directory, stem)
        return dst
    except OSError:
        return None


def save_store(store, path=None):
    """Persist the live store. BACKS UP the current file first — see _backup_before_write.
    A plain atomic write is recoverable from a crash but not from a mistaken-but-valid
    command, and the closed items we prune away are the paper trail, not noise."""
    path = path or store_path()
    _backup_before_write(path)
    _atomic_write(path, json.dumps(store, indent=2, ensure_ascii=False) + "\n")
    return path


def load_archive(path=None):
    """The archive store — same shape as the live store. Corrupt/missing reads as empty,
    mirroring load_store's fail-safe: the archive is a reference copy, and a bad read of
    it must never wedge a session that only came to move items into it."""
    path = path or archive_path()
    try:
        with open(path) as f:
            d = json.load(f)
        if not isinstance(d, dict) or not isinstance(d.get("items"), list):
            raise ValueError("bad shape")
        return d
    except Exception:
        return {"version": VERSION, "items": []}


def save_archive(arch, path=None):
    """Persist the archive, backing up first exactly like save_store — the archive IS the
    paper trail, so it gets the same recoverable-write guarantee (append-only in spirit;
    the backup is how a bad entry stays correctable)."""
    path = path or archive_path()
    # store_path() so the archive's snapshots share the store's backup dir: one place to look
    # when reconstructing, and one retention policy governing the pair.
    _backup_before_write(path, store_path())
    _atomic_write(path, json.dumps(arch, indent=2, ensure_ascii=False) + "\n")
    return path


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
    """Partition `items` into (kept, archived): every done item is REMOVED from the live
    store and returned as the archive batch (stamped with `archived_at` so the trail
    carries WHEN, not just WHAT). Never drops: the caller appends the batch to the
    archive, so a prune is a move, and `restore`/`reopen` can put anything back.

    The 0.3.0 contract returned a pruned list and destroyed the done items on save.
    That made a single keystroke destroy the closure trail, so `reopen` — the safety
    net that catches a premature close — was silently disarmed for everything pruned.
    """
    kept, archived = [], []
    for i in items:
        if i.get("done"):
            i["archived_at"] = today()
            archived.append(i)
        else:
            kept.append(i)
    return kept, archived


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


ARCHIVE_CONTRACT = 1


def archive_payload(items, today_str=None):
    """The `archive list --json` payload: the closed-item paper trail, machine-readable.

    Shape (contract 1):
      contract  int    — this contract's version, independent of the store's and the list view's
      generated str    — the date the view was computed
      counts    object — total, restored (items that came back at least once)
      items     array  — every archived item, in archive order (append order == closure order),
                         each with: id, title, summary[], detail, created, done, priority,
                         tier, gate_reason, archived_at, restored_at

    Deliberately NOT list_payload: `surfaceable` is meaningless for an item that is not in the
    live store, and reusing that shape would invite a consumer to treat the two as one queue.
    `archived_at`/`restored_at` are always present and null when unset, matching list_payload's
    rule that a view never makes a consumer distinguish a missing key from a null one.
    """
    out = []
    for i in items:
        out.append({
            "id": i.get("id"),
            "title": i.get("title", ""),
            "summary": list(i.get("summary") or []),
            "detail": i.get("detail", ""),
            "created": i.get("created"),
            "done": bool(i.get("done")),
            "priority": i.get("priority", 0),
            "tier": i.get("tier"),
            "gate_reason": i.get("gate_reason"),
            "archived_at": i.get("archived_at"),
            "restored_at": i.get("restored_at"),
        })
    return {
        "contract": ARCHIVE_CONTRACT,
        "generated": today_str or today(),
        "counts": {
            "total": len(items),
            "restored": sum(1 for i in items if i.get("restored_at")),
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

# How many open items the banner LISTS before summarising the rest as a count.
#
# The banner is injected into EVERY session's context, so its cost is paid on every single
# session — unlike a `list` the user chose to run. Past a couple of dozen open items the banner
# stops being a reminder and becomes a wall of text that crowds out the actual conversation.
# Ranking is by priority (surfaceable() sorts descending), so the head of the list is the part
# worth spending context on; the tail is disclosed as a count, never silently dropped, and one
# `waypoints.py list` shows it in full.
BANNER_MAX_ITEMS = int(os.environ.get("WAYPOINTS_BANNER_MAX_ITEMS") or 10)

# Titles longer than this are trimmed to one line in the banner. Titles accreted continuity notes
# ("★ NEXT UP: … — prefix-cache goal already met by …"), which wrap to three lines each and turn
# ten items into thirty. The full title stays one `show <id>` away, and the trim is word-boundary
# with an ellipsis so it always reads as truncated rather than as a shorter title.
BANNER_TITLE_MAX = int(os.environ.get("WAYPOINTS_BANNER_TITLE_MAX") or 96)

# The command that walks the user through unblocking gated items. It ships in a SEPARATE plugin
# (run-to-completion), so the banner must not promise it unconditionally — see plugin_available.
UNGATE_COMMAND = "/ungate-queue"
UNGATE_PLUGIN = "run-to-completion"


def claude_dir():
    """Claude Code's config root. Overridable via $WAYPOINTS_CLAUDE_DIR so tests can point the
    plugin probe at a fixture instead of the real machine."""
    return os.environ.get("WAYPOINTS_CLAUDE_DIR") or os.path.expanduser("~/.claude")


def plugin_available(name, root=None):
    """True when a SIBLING plugin is both installed and not explicitly disabled.

    A soft dependency. `waypoints` must stand alone: pointing at another plugin's command when it
    isn't there is a dangling reference for anyone who installed only this one. So the hint is
    earned by a positive check, never assumed.

    Two surfaces, because installed and enabled are different states: the registry
    (`plugins/installed_plugins.json`, keyed `name@marketplace`) says it is on disk;
    `enabledPlugins` in settings says whether it is switched on, and a user can disable a plugin
    without uninstalling it. settings.local.json wins over settings.json, matching Claude Code's
    own precedence.

    Fails CLOSED — any unreadable/missing/malformed file means "don't advertise it". A missing
    hint is a cosmetic loss; a hint for a command that does not exist is a broken instruction.
    """
    root = root or claude_dir()
    try:
        with open(os.path.join(root, "plugins", "installed_plugins.json")) as f:
            registry = json.load(f)
        keys = [k for k in (registry.get("plugins") or {})
                if k == name or k.startswith(name + "@")]
        if not keys:
            return False
    except Exception:
        return False
    # Explicit disable wins, and local settings win over global.
    for settings_file in ("settings.json", "settings.local.json"):
        try:
            with open(os.path.join(root, settings_file)) as f:
                enabled = (json.load(f).get("enabledPlugins") or {})
        except Exception:
            continue
        for k in keys:
            if k in enabled:
                if not enabled[k]:
                    return False
                break
    return True


def _short_title(title, maxlen=None):
    """Trim a title to one banner line on a word boundary. Returns it unchanged when it fits."""
    maxlen = BANNER_TITLE_MAX if maxlen is None else maxlen
    t = " ".join((title or "").split())
    if len(t) <= maxlen:
        return t
    cut = t[:maxlen].rsplit(" ", 1)[0].rstrip(" ,;:—-")
    return (cut or t[:maxlen].rstrip()) + "…"

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


def format_banner(items, ungate_hint=None):
    """Banner text for the given (already-surfaceable) items, or '' if none.

    ids are intentionally NOT printed here — they read as a redundant restatement of the title
    right next to them; use `waypoints.py list`/`show <id>` to get an item's id when needed.
    Past COMPACT_THRESHOLD open items, sub-bullets are dropped (title only) and long titles are
    trimmed to one line, to keep the banner skimmable; full detail stays one
    `waypoints.py show <id>` away.

    At most BANNER_MAX_ITEMS items are LISTED — the highest-priority head, since surfaceable()
    has already sorted by priority. The remainder is disclosed as a count rather than listed,
    because this text is injected into every session's context and an unbounded banner crowds
    out the conversation it is meant to serve. Nothing is silently dropped: the header counts all
    open items, the tail is counted explicitly, and `list` shows everything.

    Gated items are marked ⛔ in place. Past GATED_COLLAPSE_THRESHOLD of them they collapse to a
    single counted line instead — the count is always stated, so nothing is silently dropped.
    That line offers UNGATE_COMMAND only when its plugin is actually installed and enabled
    (`ungate_hint=None` probes; pass a bool to decide it yourself) — a soft dependency, so this
    plugin never advertises a command a given machine does not have."""
    if not items:
        return ""
    # None = probe the machine; a bool = caller decided (tests, and any future caller that
    # already knows). Probing only when gated items will actually collapse keeps the common
    # path free of file reads.
    gated = [i for i in items if is_gated(i)]
    collapse_gated = len(gated) > GATED_COLLAPSE_THRESHOLD
    listable = [i for i in items if not (collapse_gated and is_gated(i))] if collapse_gated else items
    # Cap the list at the highest-priority head; the tail becomes a count, not a silence.
    shown = listable[:BANNER_MAX_ITEMS]
    unlisted = len(listable) - len(shown)
    compact = len(shown) > COMPACT_THRESHOLD
    header = (f"🧭 waypoints: {len(items)} open waypoint(s) still ahead — they persist until "
               f"done. Just ask me to add or complete one; disable via /plugin if unwanted:")
    lines = [_wrap(header, "")]
    if compact:
        note = "(compact mode — run `waypoints.py show <id>` for an item's sub-bullets"
        note += "; titles are trimmed)" if any(
            len(" ".join(i["title"].split())) > BANNER_TITLE_MAX for i in shown) else ")"
        lines.append(_wrap(note, "  "))
    bullet_indent = "  • "
    gated_indent = "  ⛔ "
    date_indent = " " * len(bullet_indent)
    for i in shown:
        title = _short_title(i["title"]) if compact else i["title"]
        lines.append(_wrap(title, gated_indent if is_gated(i) else bullet_indent))
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
    if unlisted:
        lines.append(_wrap(f"… and {unlisted} more open, not listed here (lower priority). "
                            f"`waypoints.py list` shows every one.", "  "))
    if collapse_gated:
        if ungate_hint is None:
            ungate_hint = plugin_available(UNGATE_PLUGIN)
        gated_line = (f"⛔ {len(gated)} gated — each needs something before it can move. "
                      f"Run `/waypoints-gated` to see them and why")
        gated_line += (f", or `{UNGATE_COMMAND}` to work through what is blocking them."
                       if ungate_hint else ".")
        lines.append(_wrap(gated_line, "  "))
    return "\n".join(lines)

#!/usr/bin/env python3
"""CLI to manage the waypoints store.

    waypoints                            # a concise dashboard (counts, top items, what to type)
    waypoints list                       # every item, ONE LINE each, grouped by verdict
    waypoints list --verbose             # ...plus bullets, gate reasons, dates, priorities
    waypoints list --json                # documented machine-readable contract (see list_payload)
    waypoints list --gated|--waiting|--actionable|--untriaged   # symmetric views; --open drops done
    waypoints list [--limit N] [--page N] [--max-chars N] [--all]   # paging, see below
    waypoints resolve                    # release waiting items whose target has landed
    waypoints triage <id> --tier do-now|heavy|gated|waiting
                        [--gate-reason "…"] [--waiting-on "<item-id> @ <milestone>"] [--clear]
    waypoints add "Title" [--point "…" ...] [--detail ...] [--surface-on YYYY-MM-DD]
    waypoints edit <id> [--title …] [--add-point "…" ...] [--clear-summary] [--detail …]
                                         # --add-point APPENDS; --point REPLACES (guarded)
                        [--surface-on YYYY-MM-DD] [--clear-surface-on]
    waypoints show <id>                  # print title + summary + full detail (the "pick it up" view)
    waypoints done <id> [--as "resolution"]  # mark done; --as rewrites the title to the outcome
                                             # (use it when the title reads as an open question)
    waypoints reopen <id>                # undo done (inverse of `done`); AUTO-RESTORES an
                                         # archived item first — no separate `restore` needed
    waypoints restore <id>               # bring an archived item back to the live store (still done)
    waypoints rm <id>                    # remove an item from the LIVE store, archiving it (recoverable)
                                         # --delete --confirm = the obscure two-step, archive-only
    waypoints archive list               # the closed-item paper trail
    waypoints archive show <id>          # full record of an archived item
    waypoints journal [--id <id>] [--since YYYY-MM-DD]
                                         # the mutation history: which command changed what,
                                         # when. Append-only and never pruned
    waypoints toggle <id>                # flip an item's done state
    waypoints priority <id> <level>      # set banner priority (int; higher shows earlier)
    waypoints reorder <id> <position>    # move an item to a 0-based position in the list
    waypoints prune                      # MOVE all done items to the archive (nothing is destroyed)

Item lifecycle: open -> done (live store, hidden from the banner) -> archived (a separate file,
still readable/restorable) -> deleted (gone; only via rm --delete --confirm, from the archive,
by exact id). The closed trail is a deliberate record of how things resolved, so nothing that
runs routinely destroys it.

Tiers: `title` (banner headline) + `summary` (short bullets, shown in banner via --point) +
`detail` (full continuity dump, NOT in the banner — read on demand with `show`).

Output size is a first-class concern, not a nicety. Claude Code shows roughly 30,000 characters
of a command's output inline and saves the rest to a file, and the pre-0.6.0 verbose render of a
real ~150-item store was ~32.5 KB — so the tail silently stopped being readable in place. Hence:
`list` is title-only by default (~19.6 KB for the same store), everything it moved is still there
behind `--verbose` and `show`, and pages are bounded by output size as well as item count. The
size of a candidate page is MEASURED by rendering it, never estimated, and counted in UTF-8 bytes
because bytes >= characters and the ceiling's unit cannot be verified from here. Two guarantees
hold at every budget: no item is ever unreachable by paginating (a page always carries at least
one whole item), and a page that cannot honour its budget SAYS so instead of overshooting quietly.

The `waiting` tier is blocked-on-another-item-in-this-store. It is a real tier rather than a
prefix inside `gated` for one reason: the target is an id this store holds, so the store can
re-check it for free and release the item itself. `--waiting-on` therefore REQUIRES a milestone
("<item-id> @ <milestone>"), because "when that item is done" is frequently not the trigger.
Closing a target auto-releases its dependents to UNTRIAGED — never to a guessed weight, since
their own weight was never assessed while they waited.

Three records, three jobs — do not reach for the wrong one:
  `journal`      every mutation, permanent. Answers "where did this go wrong".
  `archive list` closed items, human-readable. Answers "how did this resolve".
  the backup dir a bounded ring of whole-file snapshots. Answers "put it back".

Store path: ~/.claude/waypoints.json (override with $WAYPOINTS_FILE); the archive, the journal
and the backup dir are all derived from it, so one env var redirects the whole family.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import waypoints_core as c


JOURNAL_ARGV_TOKEN_MAX = 60


def _journal_argv_token(arg):
    """One argv token, shortened FOR DISPLAY only — the raw token stays in the file.

    A `--detail` value is routinely a multi-paragraph dump, and printing it verbatim turns the
    one-line-per-entry layout (the thing that makes the history scannable) into pages of prose
    with the timestamps buried. Newlines are collapsed first, because a single embedded newline
    is enough to break the format regardless of length.
    """
    s = " ".join(str(arg).split())
    if len(s) > JOURNAL_ARGV_TOKEN_MAX:
        s = s[:JOURNAL_ARGV_TOKEN_MAX - 1].rstrip() + "…"
    return s


def _journal_change_line(ch):
    """One change, as a line. Shows WHICH FIELDS moved rather than dumping both item dicts —
    the raw before/after stay in the file for a reader that wants them, but an unsummarised
    dump per change makes the common case (scan for the command that broke something)
    unreadable, which would defeat the point of having the record."""
    item_id = ch.get("id")
    was, now = ch.get("before"), ch.get("after")
    if was is None and now is not None:
        return f"+ {item_id}: added"
    if now is None and was is not None:
        return f"- {item_id}: removed"
    if ch.get("moved"):
        a, b = ch["moved"]
        return f"~ {item_id}: moved {a} -> {b}"
    fields = sorted(set(was or {}) | set(now or {}))
    changed = [f for f in fields if (was or {}).get(f) != (now or {}).get(f)]
    return f"~ {item_id}: {', '.join(changed) or 'no field change'}"


# ---------------------------------------------------------------------------------------
# Compact rendering (0.6.0). The default `list` is TITLE-ONLY, one line per item wherever
# possible, because the verbose form crossed Claude Code's inline-output ceiling: at ~112
# open items the full render was ~33 KB against a fixed ~30 KB boundary, so the tail became
# a saved file rather than something you could read in place. Bullets, gate reasons, dates
# and priorities all still exist -- behind --verbose and `show` -- so nothing is hidden,
# only moved off the default path.
# ---------------------------------------------------------------------------------------

# Claude Code returns roughly 30,000 characters of a successful command's output inline
# before switching to a preview plus a saved file path. Sit just under it by default.
MAX_CHARS_DEFAULT = 26000

# A page is bounded by BOTH a character budget and an item count, whichever binds first. The
# character budget is the one that matters: title lengths vary a lot, so a fixed item count
# either wastes most of the window or overshoots it.
#
# The trailing chrome is not a guessed constant -- see _footer_reserve, which BUILDS the real
# footer strings and measures them. A guessed reserve was wrong twice: too small by the section
# headers, then too small by a long `Next:` command echoing every option in force.
FOOTER_RESERVE_FALLBACK = 420

TITLE_MAX = 96

_SECTION_TITLES = {
    "actionable": "  ACTIONABLE",
    "waiting": "  WAITING (releases itself when its target lands)",
    "gated": "  GATED (needs you)",
    "untriaged": "  UNTRIAGED (no verdict yet — not the same as unblocked)",
    "done": "  DONE",
}

_SECTION_ORDER = ("actionable", "waiting", "gated", "untriaged", "done")


def _trim(text, cap=TITLE_MAX):
    s = " ".join(str(text or "").split())
    return s if len(s) <= cap else s[:cap - 1].rstrip() + "…"


def _sections(sel, c):
    """(section, members) in reading order, store order preserved inside each section."""
    done = [i for i in sel if i.get("done")]
    openish = [i for i in sel if not i.get("done")]
    g = c.partition(openish)
    groups = {"actionable": g["actionable"], "waiting": g["waiting"], "gated": g["gated"],
              "untriaged": g["untriaged"], "done": done}
    return [(name, groups[name]) for name in _SECTION_ORDER if groups[name]]


def _item_lines(i, surf, verbose, items, arch, c):
    """One item's lines. Compact is a single line; --verbose restores everything."""
    if i.get("done"):
        flag = "✓"
    elif c.is_waiting(i):
        flag = "⏳"
    elif c.is_gated(i):
        flag = "⛔"
    else:
        flag = "▶" if i["id"] in surf else "·"
    title = i.get("title", "") if verbose else _trim(i.get("title", ""))
    head = f"  {flag} [{i['id']}] {title}"
    if c.is_waiting(i):
        status, target, milestone = c.waiting_status(i, items, arch)
        arrow = f"{target or '(unparseable)'} @ {milestone or '?'}"
        if status == c.WAITING_STALE:
            head += f"   ← ⚠️ {_trim(arrow, 60)} (no such target)"
        else:
            head += f"   ← {_trim(arrow, 70)}"
    if not verbose:
        return [head]
    lines = [head]
    extra = []
    if i.get("tier"):
        extra.append(f"[{i['tier']}]")
    if i.get("surface_on"):
        extra.append(f"surface_on={i['surface_on']}")
    if i.get("priority"):
        extra.append(f"priority={i['priority']}")
    if extra:
        lines[0] = f"  {flag} [{i['id']}] {title} " + " ".join(extra)
    for b in (i.get("summary") or []):
        lines.append(f"      - {_trim(b, 200)}")
    if i.get("gate_reason"):
        lines.append(f"      gated: {i['gate_reason']}")
    return lines


def _page_size(blocks):
    """A page's real size, in UTF-8 BYTES, obtained by rendering it.

    MEASURED, never predicted. An estimate of this got it wrong twice in one sitting: first by
    omitting the section-header and footer cost, then by a one-character drift -- and an estimate
    that is 1 over is still a page that breaches the ceiling it exists to respect. Rendering the
    candidate page is O(items squared) in principle and free in practice at this scale.

    Bytes rather than characters because the ceiling's unit is not something this code can
    verify, and bytes >= characters always: a byte-safe page is therefore safe under either
    reading, whereas a character-safe page is NOT (these titles are full of multi-byte —, ←, ⏳,
    which ran ~1.3% over a 26000 budget when counted as bytes). The cost of the conservative
    choice is a slightly under-filled page; the cost of the other is a silent breach.

    Every header is rendered as `(continued)` here so the measurement is the worst case for the
    page regardless of where it lands in the sequence."""
    return len(_render_page(blocks, set(_SECTION_TITLES)).encode("utf-8"))


def _footer_reserve(args, with_counts):
    """Exactly how much room the trailing chrome needs, in UTF-8 bytes.

    Built from the real strings rather than estimated. The `Next:` line echoes every option in
    force, so its length varies with the invocation -- which is precisely how a fixed reserve
    ends up too small on the long invocations and only there, making the breach look random."""
    parts = ["\n  Showing 000000-000000 of 000000.",
             "  Next: " + _next_page_cmd(args, 999999)]
    if with_counts:
        parts.append("\n  open: 000000 — 000000 actionable · 000000 waiting · 000000 gated · "
                     "000000 untriaged")
        parts.append("  (views: --actionable / --waiting / --gated / --untriaged"
                     " · --verbose for bullets, reasons and dates)")
        parts.append("  ⚠️  000000 waiting item(s) point at a target that does not exist — "
                     "run `waypoints resolve` to see which.")
    return len("\n".join(parts).encode("utf-8"))


def _paginate_sections(blocks, limit, max_chars, page, reserve=FOOTER_RESERVE_FALLBACK):
    """Slice (section, lines) blocks into pages by item count AND output budget.

    A block always lands whole, so one item is never split across a page boundary; and a
    single oversized block is still emitted alone, so no item can become unreachable by
    paginating. Returns (page_blocks, start_index, has_more, total)."""
    budget = max(1, max_chars - reserve) if max_chars else 0
    pages, cur = [], []
    for b in blocks:
        if limit and len(cur) >= limit:
            pages.append(cur)
            cur = []
        elif budget and cur and _page_size(cur + [b]) > budget:
            pages.append(cur)
            cur = []
        cur.append(b)
    if cur or not pages:
        pages.append(cur)
    idx = page - 1
    total = sum(len(p) for p in pages)
    if idx < 0 or idx >= len(pages):
        return [], total, False, total
    start = sum(len(p) for p in pages[:idx])
    return pages[idx], start, idx + 1 < len(pages), total


def _render_page(shown, seen_before):
    """Section headers, emitted when the section changes. A section already partly shown on an
    earlier page is marked `(continued)` so a page is never mistaken for the whole group."""
    out, current = [], None
    for section, lines in shown:
        if section != current:
            title = _SECTION_TITLES[section]
            if section in seen_before:
                title += "  (continued)"
            out.append(title if not out else "\n" + title)
            current = section
        out.extend(lines)
    return "\n".join(out)


def _next_page_cmd(args, page):
    """The exact command for the next page, echoing the options in force."""
    parts = ["waypoints", "list"]
    for flag in ("gated", "waiting", "actionable", "untriaged", "open", "verbose"):
        if getattr(args, flag, False):
            parts.append("--" + flag)
    if args.limit:
        parts.append(f"--limit {args.limit}")
    if args.max_chars != MAX_CHARS_DEFAULT:
        parts.append(f"--max-chars {args.max_chars}")
    parts.append(f"--page {page}")
    return " ".join(parts)


DASHBOARD_TOP = 5


def _dashboard(store, items):
    """`waypoints` with no arguments: a concise orientation, not the whole inventory.

    The bare command used to be an error (the subparser was required), which meant the most
    natural thing to type taught you nothing. It must stay SMALL -- if it grew into the full
    list it would hit the same inline ceiling that made the compact list necessary."""
    openish = [i for i in items if not i.get("done")]
    if not items:
        print("(no waypoints yet)   add one:  waypoints add \"Title\" --point \"key point\"")
        return 0
    g = c.partition(openish)
    today = c.today()
    surf = {i["id"] for i in c.surfaceable(items, today)}
    print(f"{len(openish)} open — {len(g['actionable'])} actionable · {len(g['waiting'])} waiting"
          f" · {len(g['gated'])} gated · {len(g['untriaged'])} untriaged")

    ranked = sorted((i for i in openish if not c.is_gated(i)),
                    key=lambda i: -i.get("priority", 0))[:DASHBOARD_TOP]
    if ranked:
        print("\nHighest priority:")
        arch = c.load_archive()["items"]
        for i in ranked:
            mark = "⏳" if c.is_waiting(i) else ("⛔" if c.is_gated(i)
                                                else ("▶" if i["id"] in surf else "·"))
            line = f"  {mark} [{i['id']}] {_trim(i.get('title', ''), 72)}"
            if c.is_waiting(i):
                _s, target, milestone = c.waiting_status(i, items, arch)
                line += f"   ← {_trim(f'{target} @ {milestone}', 48)}"
            print(line)
    if g["gated"]:
        print(f"\n{len(g['gated'])} gated item(s) need something from you: waypoints list --gated")
    print("\nCommands:")
    print("  waypoints list                 every item, one line each")
    print("  waypoints list --waiting       what is blocked on another item")
    print("  waypoints show ID              the full detail of one item")
    print("  waypoints resolve              release waiting items whose target landed")
    print("  waypoints --help               everything else")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="waypoints", description="Manage waypoints reminders.")
    # NOT required: a bare `waypoints` is the dashboard. The most natural thing to type used
    # to be an argparse error, which taught the reader nothing.
    sub = p.add_subparsers(dest="cmd", required=False)
    sub.add_parser("dashboard", help="the concise orientation shown by a bare `waypoints`")
    sub.add_parser("resolve", help="release waiting items whose target has landed; "
                                   "report waiting targets that do not exist")
    pl = sub.add_parser("list", help="list all items")
    pl.add_argument("--json", action="store_true",
                    help="emit the documented machine-readable contract instead of text")
    # Symmetric views, equal citizens: none is the default and none implies the others are
    # someone else's problem. Untriaged is its own view because an unassessed item is not
    # thereby actionable, and it must be findable rather than falling between the two.
    view = pl.add_mutually_exclusive_group()
    view.add_argument("--gated", action="store_true", help="only items whose verdict is gated")
    view.add_argument("--actionable", action="store_true",
                      help="only items whose verdict is do-now or heavy")
    view.add_argument("--waiting", action="store_true",
                      help="only items blocked on ANOTHER ITEM in this store reaching a milestone")
    view.add_argument("--untriaged", action="store_true", help="only items with no verdict yet")
    pl.add_argument("--open", action="store_true", help="exclude items already done")
    pl.add_argument("--verbose", action="store_true",
                    help="restore summary bullets, gate reasons, dates and priorities "
                         "(the default is title-only, one line per item)")
    pl.add_argument("--limit", type=int, default=0, metavar="N",
                    help="at most N items per page (0 = no item limit)")
    pl.add_argument("--page", type=int, default=1, metavar="N", help="which page to show (1-based)")
    pl.add_argument("--max-chars", type=int, default=MAX_CHARS_DEFAULT, metavar="N",
                    help=f"end a page before its output exceeds N (default {MAX_CHARS_DEFAULT}; "
                         f"0 disables), bounding it to what Claude Code shows inline. Counted in "
                         f"UTF-8 BYTES, the conservative reading — these titles carry multi-byte "
                         f"characters, so a byte-safe page is safe either way")
    pl.add_argument("--all", action="store_true",
                    help="no item and no character limit — for an ordinary terminal or a "
                         "redirection, not the inline view")
    pa = sub.add_parser("add", help="add an open item")
    pa.add_argument("title")
    pa.add_argument("--point", action="append", default=None,
                    help="a short summary bullet shown in the banner (repeatable)")
    pa.add_argument("--add-point", action="append", default=None, metavar="POINT",
                    help="alias of --point (a new item has no bullets to lose); accepted so the "
                         "safe verb works the same on add and edit")
    pa.add_argument("--detail", default="")
    pa.add_argument("--surface-on", default=None,
                    help="earliest date to surface (YYYY-MM-DD); NOT an expiry — persists until done")

    pe = sub.add_parser("edit", help="update an existing item in place (id + created stay fixed)")
    pe.add_argument("id")
    pe.add_argument("--title", default=None, help="new title (does NOT change the id)")
    pe.add_argument("--point", action="append", default=None,
                    help="REPLACE every summary bullet (destructive). Refuses when the item already "
                         "has bullets unless --replace-points is also given. To keep the existing "
                         "bullets and add one, use --add-point instead")
    pe.add_argument("--add-point", action="append", default=None, metavar="POINT",
                    help="append a summary bullet, KEEPING the existing ones (safe; repeatable). "
                         "This is almost always what you want when recording new information")
    pe.add_argument("--replace-points", action="store_true",
                    help="confirm that --point may discard the item's existing bullets")
    pe.add_argument("--clear-summary", action="store_true", help="remove all summary bullets")
    pe.add_argument("--detail", default=None, help="new detail; pass \"\" to clear it")
    pe.add_argument("--surface-on", default=None, help="set the earliest-surface date (YYYY-MM-DD)")
    pe.add_argument("--clear-surface-on", action="store_true", help="remove the surface-on date")

    ps = sub.add_parser("show", help="print an item's full detail (the pick-it-up view)")
    ps.add_argument("id")

    pd = sub.add_parser("done", help="mark an item done by id")
    pd.add_argument("id")
    pd.add_argument("--as", dest="resolved", default=None, metavar="RESOLUTION",
                    help="rewrite the title to this resolution phrasing while closing (one call "
                         "instead of edit+done); use it when the title reads as an open question")

    pr = sub.add_parser("reopen", help="undo done on an item by id (inverse of `done`)")
    pr.add_argument("id")

    pres = sub.add_parser("restore", help="bring an archived item back to the live store (stays done)")
    pres.add_argument("id")

    prm = sub.add_parser("rm", help="remove an item from the live store, archiving it (recoverable)")
    prm.add_argument("id")
    prm.add_argument("--delete", action="store_true",
                     help="permanent deletion — only valid for an item that is ALREADY archived "
                          "(never removes from the live store)")
    prm.add_argument("--confirm", action="store_true",
                     help="required together with --delete to actually delete (fail-closed without it)")

    parc = sub.add_parser("archive", help="read the archived (closed) item trail")
    parc_sub = parc.add_subparsers(dest="archive_cmd", required=True)
    parl = parc_sub.add_parser("list", help="list archived items")
    parl.add_argument("--json", action="store_true",
                      help="emit the documented machine-readable contract instead of text")
    parsh = parc_sub.add_parser("show", help="print an archived item's full record")
    parsh.add_argument("id")

    pt = sub.add_parser("toggle", help="flip an item's done state")
    pt.add_argument("id")

    pp = sub.add_parser("priority", help="set an item's banner priority (higher sorts earlier)")
    pp.add_argument("id")
    pp.add_argument("level", type=int, help="integer priority; higher = shown earlier. 0 is default")

    pro = sub.add_parser("reorder", help="move an item to a specific 0-based position in the list")
    pro.add_argument("id")
    pro.add_argument("position", type=int)

    pv = sub.add_parser("triage", help="record how an item can be picked up (tier + gate reason)")
    pv.add_argument("id")
    pv.add_argument("--tier", choices=c.TIERS, default=None,
                    help="do-now (bounded) | heavy (may sprawl) | gated (needs something first)")
    pv.add_argument("--waiting-on", default=None, metavar="'<item-id> @ <milestone>'",
                    help="required for --tier waiting: the item this one waits on AND the "
                         "milestone that releases it. The milestone is not optional — "
                         "\"when that item is done\" is often not the actual trigger")
    pv.add_argument("--gate-reason", default=None,
                    help="what this item is waiting on (only valid with --tier gated)")
    pv.add_argument("--clear", action="store_true",
                    help="remove the verdict entirely, back to untriaged")

    pj = sub.add_parser("journal", help="the append-only mutation history (which command changed what)")
    pj.add_argument("--id", default=None, help="only entries that touched this item id")
    pj.add_argument("--since", default=None,
                    help="only entries at or after this YYYY-MM-DD (or a full ISO stamp)")

    sub.add_parser("prune", help="move all done items to the archive (nothing is destroyed)")
    args = p.parse_args(argv)

    store = c.load_store()
    items = store["items"]

    if args.cmd is None or args.cmd == "dashboard":
        return _dashboard(store, items)

    if args.cmd == "resolve":
        arch = c.load_archive()["items"]
        promoted = c.promote_landed_waiting(items, arch)
        stale = c.stale_waiting(items, arch)
        if promoted:
            c.save_store(store)
            print(f"released {len(promoted)} waiting item(s) — each is now UNTRIAGED on purpose, "
                  f"because its own weight was never assessed while it waited:")
            for it, target, milestone in promoted:
                print(f"  ⏵ [{it['id']}] {it['title']}")
                print(f"      landed: {target} @ {milestone}")
        else:
            print("nothing released: no waiting item's target has landed.")
        if stale:
            print(f"\n  ⚠️  {len(stale)} waiting item(s) point at a target that does not exist. "
                  f"Not repaired — the store cannot know whether the target was renamed or the "
                  f"dependency was mistyped:")
            for it, target in stale:
                print(f"      [{it['id']}] -> {target or '(unparseable)'}")
        return 0

    if args.cmd == "list":
        view = ("gated" if args.gated else "actionable" if args.actionable
                else "waiting" if args.waiting
                else "untriaged" if args.untriaged else None)
        sel = items
        if args.open or view:
            sel = [i for i in sel if not i.get("done")]
        if view == "gated":
            sel = [i for i in sel if c.is_gated(i)]
        elif view == "actionable":
            sel = [i for i in sel if c.is_actionable(i)]
        elif view == "waiting":
            sel = [i for i in sel if c.is_waiting(i)]
        elif view == "untriaged":
            sel = [i for i in sel if c.is_untriaged(i)]

        if args.json:
            # Counts describe the WHOLE store (unfiltered) so a filtered view still tells the
            # reader what it is a subset of -- a count that silently narrows with the filter is
            # how a partial view gets mistaken for the total. The same reasoning is why --limit
            # and --max-chars are IGNORED here: silently paginated JSON is not a contract.
            payload = c.list_payload(items)
            if view or args.open:
                keep = {i["id"] for i in sel}
                payload["items"] = [it for it in payload["items"] if it["id"] in keep]
                payload["view"] = view or "open"
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return 0

        if not items:
            print("(no open waypoints)")
            return 0
        if not sel:
            print(f"(no {view} waypoints)" if view else "(nothing to show)")
            return 0
        today = c.today()
        surf = {i["id"] for i in c.surfaceable(items, today)}
        arch = c.load_archive()["items"]

        # Grouped, in the order a reader acts on them. `waiting` gets its OWN section rather
        # than being folded into either neighbour: it cannot be started now, but it needs no
        # human and releases itself, so filing it with the human-gated pile would hide the
        # dependency cascade. Within a section, store order is preserved, so `reorder` and
        # `priority` still mean what they meant.
        blocks = []
        for section, members in _sections(sel, c):
            for i in members:
                blocks.append((section, _item_lines(i, surf, args.verbose, items, arch, c)))

        limit = 0 if args.all else args.limit
        max_chars = 0 if args.all else args.max_chars
        shown, start, has_more, total = _paginate_sections(
            blocks, limit, max_chars, args.page,
            reserve=_footer_reserve(args, with_counts=view is None))
        if not shown:
            print(f"page {args.page} is past the end ({total} item(s) total).")
            return 0

        # The budget bounds the WHOLE output, so body and chrome are assembled together and
        # checked ONCE. Checking the body alone was a real bug: a page whose items fit but whose
        # footer tipped it over reported no breach, so the breach was invisible exactly when it
        # mattered.
        seen_before = {sec for sec, _ in blocks[:start]}
        out = [_render_page(shown, seen_before)]

        if start or has_more:
            out.append(f"\n  Showing {start + 1}-{start + len(shown)} of {total}.")
            if has_more:
                out.append(f"  Next: {_next_page_cmd(args, args.page + 1)}")
        if view is None:
            g = c.partition([i for i in items if not i.get("done")])
            openn = sum(len(v) for v in g.values())
            out.append(f"\n  open: {openn} — {len(g['actionable'])} actionable · "
                       f"{len(g['waiting'])} waiting · {len(g['gated'])} gated · "
                       f"{len(g['untriaged'])} untriaged")
            out.append("  (views: --actionable / --waiting / --gated / --untriaged"
                       " · --verbose for bullets, reasons and dates)")
        # The universe for resolving a target is ALWAYS the whole store, never the current view:
        # a target outside the filter still exists, and narrowing the universe would report it as
        # missing. Only the REPORTING is scoped to what is on screen.
        in_view = {i["id"] for i in sel}
        stale = [(it, t) for it, t in c.stale_waiting(items, arch) if it["id"] in in_view]
        if stale:
            out.append(f"  ⚠️  {len(stale)} waiting item(s) point at a target that does not "
                       f"exist — run `waypoints resolve` to see which.")

        text = "\n".join(out)
        if args.max_chars and len(text.encode("utf-8")) > args.max_chars:
            # A page always carries at least one WHOLE item, so a budget too small to hold one
            # item plus the chrome cannot be honoured. Ship it and SAY so: a silent overshoot
            # hides the breach, and dropping the item would make it unreachable by paginating,
            # which is worse. Stated unconditionally — if this ever fires with more than one item
            # on the page, that is a paginator bug and the message is how it becomes visible.
            text += (f"\n  (--max-chars {args.max_chars} could not be honoured for "
                     f"{'this single item' if len(shown) == 1 else f'these {len(shown)} items'}"
                     f" — shown anyway rather than dropped.)")
        print(text)
        return 0

    if args.cmd == "add":
        it = c.add_item(items, args.title, detail=args.detail, surface_on=args.surface_on,
                        summary=(args.point or []) + (args.add_point or []) or None)
        c.save_store(store)
        print(f"added [{it['id']}] {it['title']}")
        return 0

    if args.cmd == "edit":
        existing = c.get_item(items, args.id)
        if existing is None:
            print(f"no such id: {args.id}")
            return 1
        old_points = list(existing.get("summary") or [])

        def _echo_discarded(verb):
            # Print them so they land in the session transcript and stay recoverable.
            print(f"{verb} {len(old_points)} existing summary bullet(s):")
            for point in old_points:
                print(f"    - {point}")

        kwargs = {}
        if args.title is not None:
            kwargs["title"] = args.title
        if args.clear_summary:
            if args.point or args.add_point:
                print("--clear-summary cannot be combined with --point/--add-point")
                return 2
            if old_points:
                _echo_discarded("clearing")
            kwargs["summary"] = []
        elif args.add_point:
            if args.point:
                print("pass either --point (replace) or --add-point (append), not both")
                return 2
            kwargs["summary"] = old_points + list(args.add_point)
        elif args.point is not None:
            if old_points and not args.replace_points:
                print(f"refusing to discard {len(old_points)} summary bullet(s) on [{args.id}].")
                print("  --point REPLACES the whole bullet list; it does not append.")
                _echo_discarded("  would discard")
                print("  To add to them:      --add-point \"…\"")
                print("  To really replace:   --replace-points --point \"…\"")
                return 2
            if old_points:
                _echo_discarded("replacing")
            kwargs["summary"] = list(args.point)
        if args.detail is not None:
            kwargs["detail"] = args.detail
        if args.clear_surface_on:
            kwargs["surface_on"] = None
        elif args.surface_on is not None:
            kwargs["surface_on"] = args.surface_on
        it = c.edit_item(items, args.id, **kwargs)
        if it is None:
            print(f"no such id: {args.id}")
            return 1
        c.save_store(store)
        print(f"edited [{it['id']}] {it['title']}")
        return 0

    if args.cmd == "show":
        it = c.get_item(items, args.id)
        if it is None:
            print(f"no such id: {args.id}")
            return 1
        print(f"[{it['id']}] {it['title']}")
        for point in it.get("summary") or []:
            print(f"  - {point}")
        if it.get("tier"):
            line = f"verdict: {it['tier']}"
            if it.get("gate_reason"):
                line += f" — waiting on: {it['gate_reason']}"
            print(f"  {line}")
        meta = f"created: {it.get('created')}   done: {it.get('done')}"
        if it.get("surface_on"):
            meta += f"   surface_on: {it['surface_on']}"
        print(meta)
        if it.get("detail"):
            print(f"\n{it['detail']}")
        return 0

    if args.cmd == "done":
        it = c.get_item(items, args.id)
        ok = c.mark_done(items, args.id, resolved_title=args.resolved)
        c.save_store(store)
        if not ok:
            print(f"no such id: {args.id}")
            return 1
        print(f"marked done: {args.id}")
        # Closing an item is the EVENT that releases anything waiting on it, so promotion
        # happens here rather than on read. A store that mutated every time it was listed would
        # make `list` unsafe to run, and the release would then be attributed to whoever
        # happened to look next instead of to the close that actually caused it.
        released = c.promote_landed_waiting(items, c.load_archive()["items"])
        if released:
            c.save_store(store)
            print(f"released {len(released)} item(s) that were waiting on this:")
            for rel, target, milestone in released:
                print(f"  ⏵ [{rel['id']}] {rel['title']}")
            print("    Each is now UNTRIAGED on purpose — its own weight was never assessed "
                  "while it waited, so it needs a verdict rather than an assumed one.")
        # Point-of-action guard: if the title still reads as an open question/decision and no
        # resolution was recorded, nudge (non-blocking — the close already happened) so a bare ✓
        # doesn't leave the answer implicit. Re-running `done --as` on a done item is safe.
        if args.resolved is None and it is not None and c.looks_unresolved(it.get("title", "")):
            print(
                f"⚠️  This title reads as an open question — its ✓ won't say how it resolved.\n"
                f"    Record the outcome:  waypoints.py done {args.id} --as \"<what actually happened>\"",
                file=sys.stderr)
        return 0

    if args.cmd == "reopen":
        # Multi-store: the live store wins (an id that exists in both is a live item, even a
        # done one — prefer it and name the archived namesake rather than silently picking).
        live = c.get_item(items, args.id)
        arch = c.load_archive()
        archived = c.get_item(arch["items"], args.id)
        if live is not None:
            if live.get("done"):
                c.reopen_item(items, args.id)
                c.save_store(store)
            if archived is not None:
                print(
                    f"note: an archived item with the same id exists "
                    f"(archived {archived.get('archived_at') or 'unknown'}) — "
                    f"the live copy was the one reopened",
                    file=sys.stderr)
            print(f"reopened: {args.id}")
            return 0
        if archived is not None:
            # Auto-restore + reopen in one step: it would otherwise be stranded, still done,
            # out of the banner — exactly the trap that 0.3.0's destroy-on-prune created.
            if args.id in [i["id"] for i in items]:
                items.append(archived)
            else:
                items.insert(0, archived)  # fresh id -> top of the queue
            archived["done"] = False
            archived["restored_at"] = c.today()
            # archived_at is KEPT: it is the trail's record of when this closed, and a restore
            # should add a fact, not erase one. `restored_at` alone says where it is now.
            arch["items"] = [i for i in arch["items"] if i["id"] != args.id]
            c.save_store(store)
            c.save_archive(arch)
            print(f"restored from archive and reopened: {args.id}")
            return 0
        print("no such id: not in the live store or the archive")
        return 1

    if args.cmd == "restore":
        arch = c.load_archive()
        aitem = c.get_item(arch["items"], args.id)
        if aitem is None:
            print(f"no such id in the archive: {args.id}")
            return 1
        if args.id in [i["id"] for i in items]:
            print(f"refusing: {args.id} is already in the live store — use `edit`/`reopen` on it")
            return 2
        # Back as DONE — restore is a move, not a re-open; `reopen` is the one-step form.
        # archived_at is KEPT for the same reason as in `reopen`: it records when the item closed.
        aitem["restored_at"] = c.today()
        arch["items"] = [i for i in arch["items"] if i["id"] != args.id]
        items.insert(0, aitem)
        c.save_store(store)
        c.save_archive(arch)
        print(f"restored to the live store (still done): {args.id} — `reopen {args.id}` to re-open")
        return 0

    if args.cmd == "toggle":
        new_state = c.toggle_done(items, args.id)
        if new_state is None:
            print(f"no such id: {args.id}")
            return 1
        c.save_store(store)
        print(f"{args.id} is now {'done' if new_state else 'open'}")
        return 0

    if args.cmd == "priority":
        it = c.set_priority(items, args.id, args.level)
        if it is None:
            print(f"no such id: {args.id}")
            return 1
        c.save_store(store)
        print(f"priority [{it['id']}] = {it['priority']}")
        return 0

    if args.cmd == "reorder":
        ok = c.reorder_item(items, args.id, args.position)
        c.save_store(store)
        print(f"reordered: {args.id}" if ok else f"no such id: {args.id}")
        return 0 if ok else 1

    if args.cmd == "triage":
        if args.clear and (args.tier or args.gate_reason or args.waiting_on):
            print("--clear cannot be combined with --tier/--gate-reason/--waiting-on")
            return 2
        try:
            if args.clear:
                it = c.set_verdict(items, args.id, tier=None)
            else:
                kw = {}
                if args.tier is not None:
                    kw["tier"] = args.tier
                if args.gate_reason is not None:
                    kw["gate_reason"] = args.gate_reason
                if args.waiting_on is not None:
                    kw["waiting_on"] = args.waiting_on
                if not kw:
                    print("nothing to set: pass --tier, --gate-reason, --waiting-on, or --clear")
                    return 2
                # Tier and target move in ONE call on purpose. Retiering away from gated drops
                # gate_reason, so migrating a WAIT item in two steps would lose the prose in
                # between -- and that prose is usually the only record of what it waited for.
                it = c.set_verdict(items, args.id, **kw)
        except c.VerdictError as e:
            print(f"refused: {e}")
            return 2
        if it is None:
            print(f"no such id: {args.id}")
            return 1
        c.save_store(store)
        verdict = it.get("tier") or "untriaged"
        extra = f" — {it['gate_reason']}" if it.get("gate_reason") else ""
        if it.get("waiting_on"):
            extra = f" — waiting on {it['waiting_on']}"
            status, target, _m = c.waiting_status(it, items, c.load_archive()["items"])
            if status == c.WAITING_STALE:
                extra += "   ⚠️ no item with that id — check the target before relying on it"
            elif status == c.WAITING_LANDED:
                extra += "   ⚠️ that target is already done — run `waypoints resolve`"
        print(f"triaged [{it['id']}] {verdict}{extra}")
        return 0

    if args.cmd == "prune":
        kept, archived_batch = c.prune(items)
        if not archived_batch:
            print("no done items to archive")
            return 0
        arch = c.load_archive()
        existing = {i["id"] for i in arch["items"]}
        for i in archived_batch:
            if i["id"] not in existing:  # re-prune of the same done item: idempotent no-op
                arch["items"].append(i)
        store["items"] = kept
        c.save_store(store)
        c.save_archive(arch)
        print(
            f"archived {len(archived_batch)} done item(s) to {c.archive_path()} "
            f"(nothing was destroyed: `reopen <id>` restores; `archive list` shows the trail; "
            f"`rm <id> --delete --confirm` is the only path to permanent deletion)")
        return 0

    if args.cmd == "rm":
        live = c.get_item(items, args.id)
        if args.delete:
            # The deliberate two-step. Without BOTH flags this refuses — 0.3.0's
            # --point/--replace-points idiom: no destructive default, exit 2, name the flag.
            if not args.confirm:
                print("refusing: permanent deletion requires BOTH --delete AND --confirm.")
                print(f"  The archive is the paper trail of how things resolved; deleting it is "
                      f"your call, made deliberately.")
                print(f"  To really delete:  waypoints.py rm {args.id} --delete --confirm")
                return 2
            if live is not None:
                print(
                    f"refusing: {args.id} is still in the LIVE store — the two-step deletes "
                    f"from the ARCHIVE only (its purpose is destroying the paper trail, which a "
                    f"live item doesn't have yet).")
                print(f"  Step 1 (archive it):  waypoints.py rm {args.id}"
                      + ("   [it is OPEN — that step will close it]"
                         if not live.get("done") else ""))
                print(f"  Step 2 (destroy it):   waypoints.py rm {args.id} --delete --confirm")
                return 2
            arch = c.load_archive()
            aitem = c.get_item(arch["items"], args.id)
            if aitem is None:
                print(f"no such id in the archive: {args.id} — nothing to delete")
                return 1
            arch["items"] = [i for i in arch["items"] if i["id"] != args.id]
            c.save_archive(arch)
            print(f"permanently deleted from the archive: [{aitem['id']}] {aitem['title']}")
            return 0
        # Bare rm = remove from the LIVE store, into the archive (a move, never a destruction).
        if live is None:
            arch = c.load_archive()
            if c.get_item(arch["items"], args.id) is not None:
                print(
                    f"{args.id} is not in the live store — it is ARCHIVED "
                    f"(the paper trail is recoverable: `restore {args.id}` brings it back, "
                    f"`archive show {args.id}` reads it, `rm {args.id} --delete --confirm` "
                    f"is the only way to destroy it)")
            else:
                print(f"no such id: {args.id} (not in the live store or the archive)")
            return 2
        arch = c.load_archive()
        existing = {i["id"] for i in arch["items"]}
        if args.id in existing:
            print(
                f"refusing: the archive already holds {args.id} — refusing to silently "
                f"overwrite its closed record (restore the archived copy or delete it with "
                f"`rm {args.id} --delete --confirm`, then re-rm)")
            return 2
        was_open = not live.get("done")
        live["done"] = True
        live["archived_at"] = c.today()
        items.remove(live)
        arch["items"].append(live)
        c.save_store(store)
        c.save_archive(arch)
        print(f"archived (removed from live, recoverable): [{live['id']}] {live['title']}")
        if was_open:
            # rm exists precisely to clear a stray OPEN item (a test probe, a mistake) without a
            # hand-edit of the store. Say plainly that an open item was closed on the way out, so
            # the state change is visible rather than inferred.
            print(f"  note: it was OPEN — archiving marked it done. "
                  f"`reopen {args.id}` puts it back in the queue in one step.")
        return 0

    if args.cmd == "journal":
        entries = c.read_journal(item_id=args.id, since=args.since)
        if not entries:
            where = c.journal_path()
            if not os.path.exists(where):
                print(f"(no journal yet at {where} — it starts at the next change)")
            else:
                print("(no journal entries match)")
            return 0
        for e in entries:
            argv = " ".join(_journal_argv_token(a) for a in e.get("argv") or []) or "(no argv recorded)"
            src_tag = "" if e.get("source") == "store" else f" [{e.get('source')}]"
            print(f"  {e.get('at')}{src_tag}  waypoints {argv}")
            for ch in e.get("changes") or []:
                print(f"      {_journal_change_line(ch)}")
        plural = "entry" if len(entries) == 1 else "entries"
        print(f"\n  {len(entries)} {plural} in {c.journal_path()}")
        return 0

    if args.cmd == "archive":
        arch = c.load_archive()
        aitems = arch["items"]
        if args.archive_cmd == "list":
            if args.json:
                print(json.dumps(c.archive_payload(aitems), indent=2, ensure_ascii=False))
                return 0
            if not aitems:
                print("(no archived waypoints)")
                return 0
            for i in aitems:
                at = f" (archived {i['archived_at']})" if i.get("archived_at") else ""
                print(f"  • [{i['id']}] {i['title']}{at}")
            print(f"\n  {len(aitems)} archived item(s) in {c.archive_path()}")
            return 0
        if args.archive_cmd == "show":
            aitem = c.get_item(aitems, args.id)
            if aitem is None:
                print(f"no such id in the archive: {args.id}")
                return 1
            print(f"[{aitem['id']}] {aitem['title']}")
            for point in aitem.get("summary") or []:
                print(f"  - {point}")
            if aitem.get("tier"):
                line = f"verdict: {aitem['tier']}"
                if aitem.get("gate_reason"):
                    line += f" — waiting on: {aitem['gate_reason']}"
                print(f"  {line}")
            meta = f"created: {aitem.get('created')}"
            if aitem.get("archived_at"):
                meta += f"   archived: {aitem['archived_at']}"
            if aitem.get("restored_at"):
                meta += f"   restored: {aitem['restored_at']}"
            print(meta)
            if aitem.get("detail"):
                print(f"\n{aitem['detail']}")
            return 0
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

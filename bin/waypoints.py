#!/usr/bin/env python3
"""CLI to manage the waypoints store.

    waypoints list                       # show all items (surfaceable ones marked ▶)
    waypoints list --json                # documented machine-readable contract (see list_payload)
    waypoints list --gated|--actionable|--untriaged   # symmetric views; --open drops done items
    waypoints triage <id> --tier do-now|heavy|gated [--gate-reason "…"] [--clear]
    waypoints add "Title" [--point "…" ...] [--detail ...] [--surface-on YYYY-MM-DD]
    waypoints edit <id> [--title …] [--point "…" ...] [--clear-summary] [--detail …]
                        [--surface-on YYYY-MM-DD] [--clear-surface-on]
    waypoints show <id>                  # print title + summary + full detail (the "pick it up" view)
    waypoints done <id> [--as "resolution"]  # mark done; --as rewrites the title to the outcome
                                             # (use it when the title reads as an open question)
    waypoints reopen <id>                # undo done (inverse of `done`)
    waypoints toggle <id>                # flip an item's done state
    waypoints priority <id> <level>      # set banner priority (int; higher shows earlier)
    waypoints reorder <id> <position>    # move an item to a 0-based position in the list
    waypoints prune                      # drop all done items

Tiers: `title` (banner headline) + `summary` (short bullets, shown in banner via --point) +
`detail` (full continuity dump, NOT in the banner — read on demand with `show`).

Store path: ~/.claude/waypoints.json (override with $WAYPOINTS_FILE).
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import waypoints_core as c


def main(argv=None):
    p = argparse.ArgumentParser(prog="waypoints", description="Manage waypoints reminders.")
    sub = p.add_subparsers(dest="cmd", required=True)
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
    view.add_argument("--untriaged", action="store_true", help="only items with no verdict yet")
    pl.add_argument("--open", action="store_true", help="exclude items already done")
    pa = sub.add_parser("add", help="add an open item")
    pa.add_argument("title")
    pa.add_argument("--point", action="append", default=None,
                    help="a short summary bullet shown in the banner (repeatable)")
    pa.add_argument("--detail", default="")
    pa.add_argument("--surface-on", default=None,
                    help="earliest date to surface (YYYY-MM-DD); NOT an expiry — persists until done")

    pe = sub.add_parser("edit", help="update an existing item in place (id + created stay fixed)")
    pe.add_argument("id")
    pe.add_argument("--title", default=None, help="new title (does NOT change the id)")
    pe.add_argument("--point", action="append", default=None,
                    help="replace the summary bullets (repeatable); pass none + --clear-summary to empty")
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
    pv.add_argument("--gate-reason", default=None,
                    help="what this item is waiting on (only valid with --tier gated)")
    pv.add_argument("--clear", action="store_true",
                    help="remove the verdict entirely, back to untriaged")

    sub.add_parser("prune", help="remove done items")
    args = p.parse_args(argv)

    store = c.load_store()
    items = store["items"]

    if args.cmd == "list":
        view = ("gated" if args.gated else "actionable" if args.actionable
                else "untriaged" if args.untriaged else None)
        sel = items
        if args.open or view:
            sel = [i for i in sel if not i.get("done")]
        if view == "gated":
            sel = [i for i in sel if c.is_gated(i)]
        elif view == "actionable":
            sel = [i for i in sel if c.is_actionable(i)]
        elif view == "untriaged":
            sel = [i for i in sel if c.is_untriaged(i)]

        if args.json:
            # Counts describe the WHOLE store (unfiltered) so a filtered view still tells the
            # reader what it is a subset of -- a count that silently narrows with the filter is
            # how a partial view gets mistaken for the total.
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
        for i in sel:
            flag = "✓" if i.get("done") else ("▶" if i["id"] in surf else "·")
            so = f" surface_on={i['surface_on']}" if i.get("surface_on") else ""
            pr = f" priority={i['priority']}" if i.get("priority") else ""
            tier = f" [{i['tier']}]" if i.get("tier") else ""
            print(f"  {flag} [{i['id']}] {i['title']}{tier}{so}{pr}")
            if i.get("gate_reason"):
                print(f"      gated: {i['gate_reason']}")
        if view is None:
            g = c.partition([i for i in items if not i.get("done")])
            print(f"\n  open: {len(g['actionable'])} actionable · {len(g['gated'])} gated · "
                  f"{len(g['untriaged'])} untriaged"
                  f"   (views: --actionable / --gated / --untriaged)")
        return 0

    if args.cmd == "add":
        it = c.add_item(items, args.title, detail=args.detail, surface_on=args.surface_on,
                        summary=args.point)
        c.save_store(store)
        print(f"added [{it['id']}] {it['title']}")
        return 0

    if args.cmd == "edit":
        kwargs = {}
        if args.title is not None:
            kwargs["title"] = args.title
        if args.clear_summary:
            kwargs["summary"] = []
        elif args.point is not None:
            kwargs["summary"] = args.point
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
        ok = c.reopen_item(items, args.id)
        c.save_store(store)
        print(f"reopened: {args.id}" if ok else f"no such id: {args.id}")
        return 0 if ok else 1

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
        if args.clear and (args.tier or args.gate_reason):
            print("--clear cannot be combined with --tier/--gate-reason")
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
                if not kw:
                    print("nothing to set: pass --tier, --gate-reason, or --clear")
                    return 2
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
        print(f"triaged [{it['id']}] {verdict}{extra}")
        return 0

    if args.cmd == "prune":
        before = len(items)
        store["items"] = c.prune(items)
        c.save_store(store)
        print(f"pruned {before - len(store['items'])} done item(s)")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

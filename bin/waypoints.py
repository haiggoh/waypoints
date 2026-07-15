#!/usr/bin/env python3
"""CLI to manage the waypoints store.

    waypoints list                       # show all items (surfaceable ones marked ▶)
    waypoints add "Title" [--point "…" ...] [--detail ...] [--surface-on YYYY-MM-DD]
    waypoints edit <id> [--title …] [--point "…" ...] [--clear-summary] [--detail …]
                        [--surface-on YYYY-MM-DD] [--clear-surface-on]
    waypoints show <id>                  # print title + summary + full detail (the "pick it up" view)
    waypoints done <id>                  # mark an item done (removes it from the banner)
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
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import waypoints_core as c


def main(argv=None):
    p = argparse.ArgumentParser(prog="waypoints", description="Manage waypoints reminders.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="list all items")
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

    sub.add_parser("prune", help="remove done items")
    args = p.parse_args(argv)

    store = c.load_store()
    items = store["items"]

    if args.cmd == "list":
        if not items:
            print("(no open waypoints)")
            return 0
        today = c.today()
        surf = {i["id"] for i in c.surfaceable(items, today)}
        for i in items:
            flag = "✓" if i.get("done") else ("▶" if i["id"] in surf else "·")
            so = f" surface_on={i['surface_on']}" if i.get("surface_on") else ""
            pr = f" priority={i['priority']}" if i.get("priority") else ""
            print(f"  {flag} [{i['id']}] {i['title']}{so}{pr}")
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
        meta = f"created: {it.get('created')}   done: {it.get('done')}"
        if it.get("surface_on"):
            meta += f"   surface_on: {it['surface_on']}"
        print(meta)
        if it.get("detail"):
            print(f"\n{it['detail']}")
        return 0

    if args.cmd == "done":
        ok = c.mark_done(items, args.id)
        c.save_store(store)
        print(f"marked done: {args.id}" if ok else f"no such id: {args.id}")
        return 0 if ok else 1

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

    if args.cmd == "prune":
        before = len(items)
        store["items"] = c.prune(items)
        c.save_store(store)
        print(f"pruned {before - len(store['items'])} done item(s)")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

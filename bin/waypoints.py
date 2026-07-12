#!/usr/bin/env python3
"""CLI to manage the waypoints store.

    waypoints list                       # show all items (surfaceable ones marked ▶)
    waypoints add "Title" [--detail ...] [--surface-on YYYY-MM-DD]
    waypoints done <id>                  # mark an item done (removes it from the banner)
    waypoints prune                      # drop all done items

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
    pa.add_argument("--detail", default="")
    pa.add_argument("--surface-on", default=None,
                    help="earliest date to surface (YYYY-MM-DD); NOT an expiry — persists until done")
    pd = sub.add_parser("done", help="mark an item done by id")
    pd.add_argument("id")
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
            print(f"  {flag} [{i['id']}] {i['title']}{so}")
        return 0

    if args.cmd == "add":
        it = c.add_item(items, args.title, detail=args.detail, surface_on=args.surface_on)
        c.save_store(store)
        print(f"added [{it['id']}] {it['title']}")
        return 0

    if args.cmd == "done":
        ok = c.mark_done(items, args.id)
        c.save_store(store)
        print(f"marked done: {args.id}" if ok else f"no such id: {args.id}")
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

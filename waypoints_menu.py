#!/usr/bin/env python3
"""Interactive command selector for the waypoints CLI.

Why this exists: the store is meant to be maintained through the CLI and never by hand, but the
CLI has ~22 subcommands and the ones you need for routine upkeep are not the ones you remember.
Adding a bullet is `edit <id> --add-point "…"`, which nobody recalls under pressure. The selector
closes that gap so basic maintenance stays possible from a bare terminal with no Claude Code
session available at all — which is precisely when hand-editing the JSON is most tempting and most
destructive.

THE CENTRAL DESIGN RULE: this module never touches the store. Every action ends by composing an
argv and handing it to the ordinary CLI dispatch. So the guards, the journal entries, the
confirmations and the backup ring all behave exactly as if the command had been typed — there is
no second code path that can drift from the first, and the journal records the real command rather
than "menu". A selector that reimplemented even one mutation would be a worse bug than the one it
was written to prevent.

Because the argv is the unit of work, the selector can also SHOW it before running it. That is
deliberate: it turns each use into a lesson in the actual CLI, so a reader graduates off the menu
instead of depending on it. Confirmation is not the point of the echo; teaching is.

Pure stdlib, no curses, no third-party TUI. The tool has to work when nothing else does.
"""

import os
import sys

import waypoints_core as c

# --- how many items a picker shows before it stops scrolling the terminal ---
# The picker is an aid for choosing, not a second `list`. Past a screenful it stops helping and
# starts burying the prompt, so it truncates and points at the real list command instead.
PICK_LIMIT = 20


class Cancelled(Exception):
    """Raised by any prompt when the user backs out. Unwinds to the menu loop, never to a
    half-built argv — an action is either fully specified or not attempted."""


def _in(prompt):
    """One line of input. EOF (^D) and interrupt (^C) both mean 'back out of this action',
    never 'crash' and never 'proceed with a default' — a mis-typed ^D must not mutate the store."""
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise Cancelled()


def available(stream_in=None, stream_out=None, env=None):
    """Whether the selector may run at all.

    Gated on BOTH streams being a terminal, because a bare `waypoints` is also what a script, a
    pipe (`waypoints | head`) and a hook run — and any of those blocking forever on a prompt for
    input that will never arrive is a far worse regression than the missing convenience. The
    dashboard stays the non-interactive answer, unchanged.

    WAYPOINTS_NO_MENU is the explicit opt-out for an interactive terminal that still wants the
    old plain behaviour; `waypoints dashboard` is the other, already-existing one.
    """
    env = os.environ if env is None else env
    stream_in = sys.stdin if stream_in is None else stream_in
    stream_out = sys.stdout if stream_out is None else stream_out
    if env.get("WAYPOINTS_NO_MENU", "").strip() not in ("", "0", "false", "no"):
        return False
    try:
        return bool(stream_in.isatty() and stream_out.isatty())
    except (AttributeError, ValueError):
        return False


# --------------------------------------------------------------------------- prompts


def ask(label, default=None, required=False):
    """Free text. An empty answer takes the default, or re-asks when the field is required —
    it never silently submits an empty string, which for a title or a reason would write a
    record that says nothing."""
    suffix = f" [{default}]" if default else ""
    while True:
        v = _in(f"  {label}{suffix}: ")
        if v:
            return v
        if default is not None:
            return default
        if not required:
            return ""
        print("     (required — or ^D to cancel)")


def ask_many(label):
    """Repeated text until a blank line: the flags that legitimately take several values
    (--point, --add-point) would otherwise need one menu round-trip per bullet."""
    out = []
    print(f"  {label} — one per line, blank line to finish:")
    while True:
        v = _in(f"    {len(out) + 1}> ")
        if not v:
            return out
        out.append(v)


def confirm(question, default_no=True):
    """A yes/no whose DEFAULT is no wherever the action is not reversible. Typing return in a
    hurry is the common case, so return must never be the destructive answer."""
    hint = "[y/N]" if default_no else "[Y/n]"
    v = _in(f"  {question} {hint} ").lower()
    if not v:
        return not default_no
    return v in ("y", "yes")


def ask_choice(label, options):
    """Pick one of a fixed set. Shown numbered AND named, so the answer can be either — the
    number is faster and the name is what the real command takes."""
    print(f"  {label}")
    for n, (val, desc) in enumerate(options, 1):
        print(f"    {n}) {val}{'  — ' + desc if desc else ''}")
    while True:
        v = _in("  choice: ")
        if not v:
            raise Cancelled()
        if v.isdigit() and 1 <= int(v) <= len(options):
            return options[int(v) - 1][0]
        for val, _d in options:
            if v == val:
                return val
        print("     (not one of the choices)")


def _label_for(item):
    mark = "·"
    if item.get("done"):
        mark = "✓"
    elif c.is_waiting(item):
        mark = "⏳"
    elif c.is_gated(item):
        mark = "⛔"
    title = (item.get("title") or "").replace("\n", " ")
    if len(title) > 64:
        title = title[:63] + "…"
    return f"{mark} [{item['id']}] {title}"


def ask_item(items, label="item", allow_id=True):
    """Pick an item by NUMBER from a list, or by typing its id.

    Numbering matters more than it looks: ids are slugs long enough that re-typing one is where a
    wrong-item mutation comes from, and the whole reason this selector exists is that the terminal
    is the fallback surface with no autocomplete. Typing an id stays allowed because it is what
    the echoed command shows, and because a store larger than the pick limit needs it.
    """
    if not items:
        print(f"  (no {label}s to choose from)")
        raise Cancelled()
    shown = items[:PICK_LIMIT]
    print()
    for n, it in enumerate(shown, 1):
        print(f"    {n:>3}) {_label_for(it)}")
    if len(items) > len(shown):
        print(f"    … {len(items) - len(shown)} more not shown — "
              f"type an id, or quit and run `waypoints list`")
    while True:
        v = _in(f"  {label} (number or id): ")
        if not v:
            raise Cancelled()
        if v.isdigit() and 1 <= int(v) <= len(shown):
            return shown[int(v) - 1]["id"]
        if allow_id:
            hit = c.get_item(items, v)
            if hit:
                return hit["id"]
        print("     (no such number or id)")


# --------------------------------------------------------------------------- actions
#
# Each builder returns the argv to run, or raises Cancelled. Builders may return a LIST of argvs
# when one intention is genuinely two commands (editing an item's title and its bullets), so the
# echo still shows exactly what will run rather than hiding a second mutation.


def _view_flag():
    v = ask_choice("which view?", [
        ("all", "every item, grouped by verdict"),
        ("--actionable", "what you could start now"),
        ("--waiting", "blocked on another item (releases itself)"),
        ("--gated", "blocked on you"),
        ("--untriaged", "no verdict recorded yet"),
        ("--open", "everything not done"),
    ])
    return [] if v == "all" else [v]


def a_list(items, arch):
    argv = ["list"] + _view_flag()
    if confirm("include bullets, dates and priorities (--verbose)?"):
        argv.append("--verbose")
    return argv


def a_show(items, arch):
    return ["show", ask_item([i for i in items], "item")]


def a_search(items, arch):
    """Keyword search. Reachable from the selector because a search you can only run by typing
    the flag is useless in the case the menu exists for — a bare terminal, no docs to hand."""
    q = ask("keyword (searches title, bullets and detail)", required=True)
    argv = ["search", q]
    if confirm("include closed/archived items (--all)?"):
        argv.append("--all")
    return argv


def a_add(items, arch):
    title = ask("title", required=True)
    argv = ["add", title]
    for p in ask_many("bullets (--point)"):
        argv += ["--point", p]
    detail = ask("detail — the long continuity dump, not shown in the banner", default="")
    if detail:
        argv += ["--detail", detail]
    on = ask("surface on (YYYY-MM-DD, blank for now)", default="")
    if on:
        argv += ["--surface-on", on]
    return argv


def a_add_point(items, arch):
    """The action the user reaches for by the name `add-point`, which is not a subcommand at all
    but a flag on `edit`. Offering it under the name people actually use is most of the value of
    having a selector: the flag is discoverable here and echoed in full, so the next time it can
    be typed directly."""
    iid = ask_item([i for i in items if not i.get("done")], "item")
    pts = ask_many("bullets to APPEND (existing ones are kept)")
    if not pts:
        raise Cancelled()
    argv = ["edit", iid]
    for p in pts:
        argv += ["--add-point", p]
    return argv


def a_edit(items, arch):
    iid = ask_item(items, "item")
    field = ask_choice("what do you want to change?", [
        ("title", "rewrite the title in place (id and created date are kept)"),
        ("add-point", "APPEND bullets, keeping the existing ones"),
        ("replace-points", "REPLACE every bullet — destructive, needs --replace-points"),
        ("clear-points", "remove all bullets"),
        ("detail", "the long continuity dump"),
        ("surface-on", "the date it starts surfacing"),
        ("clear-surface-on", "surface it again from now on"),
    ])
    if field == "title":
        return ["edit", iid, "--title", ask("new title", required=True)]
    if field == "add-point":
        argv = ["edit", iid]
        pts = ask_many("bullets to append")
        if not pts:
            raise Cancelled()
        for p in pts:
            argv += ["--add-point", p]
        return argv
    if field == "replace-points":
        print("  ⚠️  this DISCARDS every existing bullet on the item.")
        pts = ask_many("the complete new set of bullets")
        if not pts or not confirm("replace all bullets?"):
            raise Cancelled()
        argv = ["edit", iid, "--replace-points"]
        for p in pts:
            argv += ["--point", p]
        return argv
    if field == "clear-points":
        if not confirm("remove every bullet from this item?"):
            raise Cancelled()
        return ["edit", iid, "--clear-summary"]
    if field == "detail":
        return ["edit", iid, "--detail", ask("new detail", required=True)]
    if field == "surface-on":
        return ["edit", iid, "--surface-on", ask("date (YYYY-MM-DD)", required=True)]
    return ["edit", iid, "--clear-surface-on"]


def a_done(items, arch):
    """`--as` is offered rather than buried, because closing an item whose title reads as an open
    question leaves a record that still asks it. Rewriting the title to the outcome is the whole
    difference between an archive that answers questions and one that only proves work happened."""
    iid = ask_item([i for i in items if not i.get("done")], "item to close")
    argv = ["done", iid]
    # EVIDENCE IS REQUIRED by the CLI, so the menu must collect it -- otherwise the
    # interactive path would build a command the CLI refuses, and the gate would read as the
    # menu being broken. A blank answer is not an error: it routes to --no-evidence, because
    # some items genuinely close as duplicates or mistakes and that must be SAYABLE.
    ev = ask("evidence — what was achieved, pointing at a commit/file/version/test count",
             default="")
    if ev:
        argv += ["--evidence", ev]
    else:
        why = ask("no evidence of work — why does it close? (duplicate, superseded, obsolete)",
                  default="closed from the menu without recorded evidence")
        argv += ["--no-evidence", why or "closed from the menu without recorded evidence"]
    res = ask("resolution — rewrites the title to the outcome (--as), blank to keep it",
              default="")
    if res:
        argv += ["--as", res]
    return argv


def a_reopen(items, arch):
    """Offered over both stores at once: `reopen` auto-restores an archived item first, so
    splitting the picker into live-versus-archived would ask the user to know something the
    command deliberately handles for them."""
    pool = [i for i in items if i.get("done")] + list(arch)
    return ["reopen", ask_item(pool, "done or archived item")]


def a_toggle(items, arch):
    return ["toggle", ask_item(items, "item")]


def a_priority(items, arch):
    iid = ask_item([i for i in items if not i.get("done")], "item")
    return ["priority", iid, ask("priority (integer; higher sorts earlier)", required=True)]


def a_reorder(items, arch):
    iid = ask_item(items, "item")
    return ["reorder", iid, ask("new 0-based position", required=True)]


def a_pin(items, arch):
    iid = ask_item([i for i in items if not i.get("done")], "item")
    return ["pin", iid, "--because",
            ask("why this outranks the tier order (required)", required=True)]


def a_unpin(items, arch):
    return ["unpin", ask_item([i for i in items if not i.get("done")], "pinned item")]


def a_triage(items, arch):
    iid = ask_item([i for i in items if not i.get("done")], "item")
    tier = ask_choice("tier", [
        ("do-now", "safe and bounded enough to start unattended"),
        ("heavy", "autonomous but expensive"),
        ("gated", "blocked on a person — needs a reason"),
        ("waiting", "blocked on another ITEM — needs a target and a milestone"),
        ("clear", "remove the verdict entirely"),
    ])
    if tier == "clear":
        return ["triage", iid, "--clear"]
    argv = ["triage", iid, "--tier", tier]
    if tier == "gated":
        argv += ["--gate-reason", ask("what a person must supply", required=True)]
    elif tier == "waiting":
        print("  the item this one waits on:")
        target = ask_item([i for i in items if not i.get("done") and i["id"] != iid], "target")
        ms = ask("milestone — the POINT in that item that releases this one (required)",
                 required=True)
        argv += ["--waiting-on", f"{target} @ {ms}"]
    return argv


def a_resolve(items, arch):
    return ["resolve"]


def a_journal(items, arch):
    argv = ["journal"]
    if confirm("narrow to one item?"):
        argv += ["--id", ask_item(items + list(arch), "item")]
    since = ask("since (YYYY-MM-DD, blank for all)", default="")
    if since:
        argv += ["--since", since]
    return argv


def a_archive_list(items, arch):
    return ["archive", "list"]


def a_archive_show(items, arch):
    return ["archive", "show", ask_item(list(arch), "archived item")]


def a_restore(items, arch):
    return ["restore", ask_item(list(arch), "archived item")]


def a_prune(items, arch):
    """Shown with the count it would move, because `prune` on a store you have not just looked at
    is the one routine command whose effect is invisible until afterwards."""
    n = len([i for i in items if i.get("done")])
    if not n:
        print("  (nothing to prune — no done items in the live store)")
        raise Cancelled()
    print(f"  {n} done item(s) would move to the archive. Nothing is destroyed; "
          f"`restore` and `reopen` bring one back.")
    if not confirm("prune now?", default_no=False):
        raise Cancelled()
    return ["prune"]


def a_rm(items, arch):
    iid = ask_item([i for i in items if not i.get("done")], "item to remove")
    print("  this ARCHIVES the item — it stays readable and `reopen` brings it back in one step.")
    if not confirm("remove it?"):
        raise Cancelled()
    return ["rm", iid]


def a_recover(items, arch):
    """Exposed listing-first. `recover` replaces the whole store file, so the selector routes to
    the read-only `--list` and makes the caller come back for the repair rather than offering a
    file-level overwrite one keystroke deep."""
    print("  file-level repair, for a store that no longer parses at all.")
    print("  showing the available backups first — nothing is replaced by this.")
    return ["recover", "--list"]


ACTIONS = [
    ("look", [
        ("list",       "list items, by view",                 a_list),
        ("show",       "one item's full detail",              a_show),
        ("search",     "find items by keyword (title, bullets, detail)", a_search),
        ("journal",    "what changed, when, by which command", a_journal),
        ("archive",    "the closed-item trail",               a_archive_list),
        ("archived",   "one archived item's full record",     a_archive_show),
    ]),
    ("capture", [
        ("add",        "a new open item",                     a_add),
        ("add-point",  "append a bullet to an item  (edit --add-point)", a_add_point),
        ("edit",       "change a title, bullets, detail or date", a_edit),
    ]),
    ("close", [
        ("done",       "mark an item done (offers --as to retitle it to the outcome)", a_done),
        ("reopen",     "undo done; auto-restores an archived item first", a_reopen),
        ("toggle",     "flip an item's done state",           a_toggle),
        ("restore",    "bring an archived item back, still done", a_restore),
    ]),
    ("triage", [
        ("triage",     "record a tier, gate reason or waiting target", a_triage),
        ("resolve",    "release waiting items whose target landed", a_resolve),
        ("pin",        "do this now whatever its tier (reason required)", a_pin),
        ("unpin",      "drop the pin",                        a_unpin),
        ("priority",   "set banner priority",                 a_priority),
        ("reorder",    "move an item to a position",          a_reorder),
    ]),
    ("maintain", [
        ("prune",      "move all done items to the archive",  a_prune),
        ("rm",         "archive one open item out of the live store", a_rm),
        ("recover",    "list backups for a store that will not parse", a_recover),
    ]),
]


def _flat():
    out = []
    for _group, rows in ACTIONS:
        out.extend(rows)
    return out


def _print_menu():
    print("\nWhat would you like to do?  (number, or the name; q to quit)")
    n = 0
    for group, rows in ACTIONS:
        print(f"\n  {group}")
        for name, desc, _fn in rows:
            n += 1
            print(f"   {n:>2}) {name:<11} {desc}")
    print()


def _live_items():
    """Re-read the live store for each action.

    Wrapped rather than inlined because the store can stop parsing WHILE the loop is open -- an
    external editor, a full disk, a crash mid-write. The CLI refuses a corrupt store before the
    selector ever opens, so this is the narrow case of it breaking underneath us; the honest
    answer is to say so and offer an empty picker rather than to crash out of a session the user
    may be part-way through, or to present stale items as if they were current.
    """
    try:
        return c.load_store()["items"]
    except c.StoreCorrupt as e:
        print(e.report(), file=sys.stderr)
        print("  (the store stopped parsing — `recover` is the repair; "
              "pickers are empty until then)", file=sys.stderr)
        return []


def run(dispatch, load_items=None, load_archive=None, echo=True):
    """The selector loop.

    `dispatch` is the ordinary CLI entry point, taking an argv list. Injected rather than imported
    so the loop is testable without a store and without a terminal, and so this module keeps no
    import back-edge into the CLI that owns it.

    Stays in the loop after each command: the reason to open this at all is a maintenance pass —
    close a few items, then prune — and one action per invocation would make the common case the
    slow one. The store is re-read before every action, so each command sees the effect of the
    last rather than a snapshot from the top of the session.
    """
    load_items = load_items or _live_items
    load_archive = load_archive or (lambda: c.load_archive()["items"])
    rows = _flat()
    by_name = {name: fn for name, _d, fn in rows}
    _print_menu()

    while True:
        try:
            pick = _in("waypoints> ")
        except Cancelled:
            return 0
        if not pick:
            _print_menu()
            continue
        if pick.lower() in ("q", "quit", "exit"):
            return 0
        if pick.lower() in ("?", "h", "help", "m", "menu"):
            _print_menu()
            continue

        fn = None
        if pick.isdigit() and 1 <= int(pick) <= len(rows):
            fn = rows[int(pick) - 1][2]
        elif pick in by_name:
            fn = by_name[pick]
        if fn is None:
            print(f"  (no action '{pick}' — press return for the menu, q to quit)")
            continue

        try:
            built = fn(load_items(), load_archive())
        except Cancelled:
            print("  (cancelled — nothing was changed)")
            continue

        batch = built if built and isinstance(built[0], list) else [built]
        for argv in batch:
            if echo:
                print(f"\n  $ waypoints {' '.join(_quote(a) for a in argv)}\n")
            try:
                dispatch(argv)
            except SystemExit as e:
                # The CLI exits rather than returns on a rejected argument or a refused store.
                # That must end the ACTION, not the session -- being dropped back to the shell
                # over one bad date is exactly the friction this selector exists to remove.
                if e.code:
                    print(f"  (command exited {e.code} — nothing further in this action ran)")
                    break
        print("  — press return for the menu, or type the next action.")


def _quote(a):
    """Shell-quote for the ECHO only. The argv handed to dispatch is untouched, so this can never
    affect what runs — it exists so the printed line is one a reader can paste and re-run."""
    if a and all(ch.isalnum() or ch in "-_./:=@" for ch in a):
        return a
    return "'" + a.replace("'", "'\\''") + "'"

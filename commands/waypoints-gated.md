---
description: Show the gated waypoints — the open items blocked on something, and what each is waiting on
argument-hint: "[--json]"
---

The startup banner collapses the gated group to a counted line once there are more than a few of
them. This expands it.

Run the bundled CLI and present the result:

```sh
waypoints.py list --gated $ARGUMENTS
```

If `waypoints.py` isn't on PATH, fall back to
`python3 "$CLAUDE_PLUGIN_ROOT/bin/waypoints.py" list --gated $ARGUMENTS`.

Then, for the user:

1. **Group by what each item is waiting on**, not by item order — several usually share one
   blocker, and one answer can clear a whole group. Items with no recorded `gate_reason` are their
   own group: the reason was never captured, which is itself worth fixing.
2. **State the count** you were given, and say plainly if any item lacks a reason.
3. **Offer the unblocking question per group** — for most gated items there is exactly one thing
   only the user can supply (a decision, a credential, being present, an external system being up).
   Ask those, one group at a time.
4. When an answer arrives that unblocks an item, **record the new state** rather than only acting
   on it: `waypoints.py triage <id> --tier do-now` (or `heavy`), which drops the stale gate reason.

A gate reason is a question the user owes themselves. Reading it back to them is the point of this
command — do not silently skip an item because its blocker looks tedious.

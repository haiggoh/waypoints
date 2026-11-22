---
description: Open/close the waypoints panel pane (the engine decides where it sits)
---

This command is intercepted by the plugin's pane mod where mods run (Claude Code
terminal, and the Claude desktop app's Code tab on mod-capable builds): it toggles
the pane directly, no inference. On hosts that do not run mods, this document is
the fallback — say plainly that the pane needs a mod-capable build.

Lead any reply with `🧭 waypoints:` — the mark says which plugin produced it.

Toggle: open the panel if closed, close it if open. Any argument is refused
(positions were removed in 0.18.0 — the engine picks the seat: docked beside the
transcript in the fullscreen layout, above the prompt otherwise, a desktop widget
when minimized).

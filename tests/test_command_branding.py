#!/usr/bin/env python3
"""commands/waypoints-gated.md must instruct the reply to lead with `🧭 waypoints:`
(emoji branding rollout, Task 15 — waypoints is the reference implementation).

Usage: python3 tests/test_command_branding.py [-v]
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class CommandBrandingTests(unittest.TestCase):
    def test_gated_command_instructs_leading_with_the_mark(self):
        text = (ROOT / "commands" / "waypoints-gated.md").read_text(encoding="utf-8")
        self.assertIn("🧭 waypoints:", text)


if __name__ == "__main__":
    unittest.main()

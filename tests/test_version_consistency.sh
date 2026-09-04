#!/usr/bin/env bash
# The version lives in more than one place, and it has drifted before (three times in one day in a
# sibling plugin). This asserts the manifest, the CHANGELOG's top released entry and the README's
# documented contract number agree -- and that a bump without a changelog entry fails.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fails=0
check() { if [ "$1" -eq 0 ]; then echo "  ok: $2"; else echo "  FAIL: $2"; fails=$((fails+1)); fi; }

MANIFEST_V="$(sed -n 's/.*"version": "\([^"]*\)".*/\1/p' "$ROOT/.claude-plugin/plugin.json" | head -1)"
[ -n "$MANIFEST_V" ]; check $? "manifest carries a version ($MANIFEST_V)"

# The newest RELEASED heading, skipping an [Unreleased] placeholder.
CHANGELOG_V="$(grep -o '^## \[[0-9][^]]*\]' "$ROOT/CHANGELOG.md" | head -1 | tr -d '#[] ')"
[ "$CHANGELOG_V" = "$MANIFEST_V" ]
check $? "CHANGELOG's newest release ($CHANGELOG_V) == manifest ($MANIFEST_V)"

# A bump with no entry of its own is the specific failure mode: the heading must exist AND carry
# at least one bullet before the next heading.
BODY="$(awk -v v="## [$MANIFEST_V]" 'index($0,v)==1{f=1;next} f&&/^## /{exit} f' "$ROOT/CHANGELOG.md" | grep -c '^- ')"
[ "$BODY" -gt 0 ]
check $? "the $MANIFEST_V entry has content ($BODY bullets)"

# The README documents the list contract by number; a bump there must not be forgotten.
CONTRACT="$(sed -n 's/^LIST_CONTRACT = \([0-9]*\).*/\1/p' "$ROOT/waypoints_core.py")"
grep -q "contract $CONTRACT" "$ROOT/README.md"
check $? "README mentions the current list contract ($CONTRACT)"

if [ "$fails" -eq 0 ]; then echo "ALL PASS"; else echo "$fails FAILURE(S)"; exit 1; fi

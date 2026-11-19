#!/bin/bash
# Lay the Claude Code mod API types into .claude-plugin/types/ so tsc and the TypeScript
# language server resolve 'claude-code' (and 'claude-code/testing') for hooks/register.tsx.
set -euo pipefail
usage() {
  cat <<'USAGE'
usage: scripts/lay-mod-types.sh [--from FILE] [--help]

Copies this build's mod API declarations to .claude-plugin/types/claude-code/index.d.ts
(gitignored) so `tsc -p .` and editors type-check the hooks module.

  --from FILE   use this claude-code.d.ts instead of searching for one
  --help        show this help

Without --from it takes the newest claude-code.d.ts the plugin-authoring skill wrote under
$TMPDIR-style bundled-skills folders (/private/tmp/claude-*/bundled-skills/*/*/plugin-authoring/
types/). Load the plugin-authoring skill once in any session if none is found.

Environment: WAYPOINTS_MOD_TYPES  same as --from (an invalid path aborts).
USAGE
}
src="${WAYPOINTS_MOD_TYPES:-}"
while [ $# -gt 0 ]; do
  case "$1" in
    --help|-h) usage; exit 0 ;;
    --from) [ $# -ge 2 ] || { echo "error: --from needs a file" >&2; exit 2; }; src="$2"; shift 2 ;;
    *) echo "error: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done
if [ -n "$src" ]; then
  [ -f "$src" ] || { echo "error: types file not found: $src" >&2; exit 1; }
else
  src=$(ls -t /private/tmp/claude-*/bundled-skills/*/*/plugin-authoring/types/claude-code.d.ts 2>/dev/null | head -1 || true)
  [ -n "$src" ] || { echo "error: no bundled claude-code.d.ts found; load the plugin-authoring skill once, or pass --from" >&2; exit 1; }
fi
root="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$root/.claude-plugin/types/claude-code"
cp "$src" "$root/.claude-plugin/types/claude-code/index.d.ts"
echo "laid $(head -1 "$src" | sed 's|^// ||') -> .claude-plugin/types/claude-code/index.d.ts"

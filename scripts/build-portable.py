#!/usr/bin/env python3
"""Build the portable package for waypoints (COORDINATION C1/C2, Option B).

The host package (repo root) is unchanged: it keeps its bin/, hooks and settings, and
existing Code contracts stay intact. This script generates the committed ``portable/``
directory from the host tree — never hand-edit portable/, edit the host and re-run this
script; ``--check`` (and the test suite) fails when the two drift.

Portable layout rules (COORDINATION C1, from the loading/platform docs):
  - ``.claude-plugin/plugin.json`` keeps the SAME name as the host manifest, so a synced
    copy never double-runs next to the installed marketplace plugin (loading.md
    name-conflict order).
  - no top-level ``bin/`` (top-level bin blocks Chat/Cowork installs, platform-support.md).
  - hook-invoked scripts stay under ``hooks/`` referenced via ``${CLAUDE_PLUGIN_ROOT}``;
    skill-invoked scripts would go to ``skills/<skill>/scripts/`` via
    ``${CLAUDE_SKILL_DIR}`` (none in this repo).
  - the Python import closure is copied, never symlinked outside the root (loading.md).

Determinism: ``portable/`` is byte-stable for a given (host tree, source_commit,
source_repo); the zip additionally pins ZipInfo date_time/external_attr, so it is
byte-stable on one machine/zlib — not a cross-platform guarantee. ``--check`` is commit-stable by construction: it rebuilds with the
COMMITTED source_commit (read back from portable/PORTABLE-BUILD.json), so the gate is
green at the shipping commit and at every later HEAD as long as the host files did not
drift — and red the moment they did.

Usage:
  build-portable.py               build portable/ in place (temp build + atomic swap)
  build-portable.py --check       rebuild in a temp dir (stamped with the COMMITTED
                                  source_commit) and diff against portable/; exit 1 on drift
  build-portable.py --zip [--out DIR]   emit the upload zip from a temp build (does NOT
                                  touch portable/); default out: dist/ (gitignored)
  build-portable.py --commit SHA  record this source_commit (default: HEAD)

Env: none. Stdlib only. Requires git only when --commit is not given.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

SCHEMA = "haiggoh-portable-build/1"
TRANSFORM_VERSION = "1"
BUILDER = "scripts/build-portable.py"
BUILDER_VERSION = "1.0.0"
FALLBACK_SOURCE_REPO = "haiggoh/waypoints"   # pinned: never derive from the clone's dir name
ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)                 # fixed zip timestamps: byte-stable zips

# host-relative -> portable-relative copy map. Root-level modules stay at the portable
# ROOT because bin/waypoints.py puts the repo root on sys.path to import them; the CLI
# itself moves bin/ -> scripts/ (top-level bin/ blocks Chat/Cowork installs). Text files
# in TRANSFORMS get the listed rewrites (the bin/ -> scripts/ reference updates).
COPY_FILES = [
    ".claude-plugin/plugin.json",
    "__init__.py",
    "waypoints_core.py",
    "waypoints_menu.py",
    "hooks/hooks.json",
    "hooks/waypoints.py",
    "hooks/register.tsx",
    "types/index.d.ts",
    "scripts/waypoints.py",
    "skills/waypoints/SKILL.md",
    "commands/waypoints-gated.md",
    "commands/waypoints-pane.md",
]
HOST_TO_PORTABLE = {"scripts/waypoints.py": "bin/waypoints.py"}
TRANSFORMS = {
    # the CLI path move and every reference to it. Replacements are quote-free so they
    # are safe inside f-strings in the CLI source as well as markdown.
    "skills/waypoints/SKILL.md": [
        ("$CLAUDE_PLUGIN_ROOT/bin/waypoints.py", "$CLAUDE_PLUGIN_ROOT/scripts/waypoints.py"),
        ("`waypoints.py`", "`python3 $CLAUDE_PLUGIN_ROOT/scripts/waypoints.py`"),
        ("`waypoints.py ", "`python3 $CLAUDE_PLUGIN_ROOT/scripts/waypoints.py "),
            ("re:" + r"(?<!/)waypoints\.py(?=[\s).])", "python3 $CLAUDE_PLUGIN_ROOT/scripts/waypoints.py"),
    ],
    "commands/waypoints-gated.md": [
        ("$CLAUDE_PLUGIN_ROOT/bin/waypoints.py", "$CLAUDE_PLUGIN_ROOT/scripts/waypoints.py"),
        ("waypoints.py list --gated $ARGUMENTS",
         "python3 $CLAUDE_PLUGIN_ROOT/scripts/waypoints.py list --gated $ARGUMENTS"),
        ("`waypoints.py`", "`python3 $CLAUDE_PLUGIN_ROOT/scripts/waypoints.py`"),
        ("`waypoints.py ", "`python3 $CLAUDE_PLUGIN_ROOT/scripts/waypoints.py "),
            ("re:" + r"(?<!/)waypoints\.py(?=[\s).])", "python3 $CLAUDE_PLUGIN_ROOT/scripts/waypoints.py"),
    ],
    "hooks/waypoints.py": [
        # host-only PATH guidance is FALSE in the portable package (no bin/, scripts/ not on PATH)
        ("bin/ is on the Bash-tool PATH", "ships no bin/ on the PATH"),
        ("`waypoints.py`", "`python3 $CLAUDE_PLUGIN_ROOT/scripts/waypoints.py`"),
        ("`waypoints.py ", "`python3 $CLAUDE_PLUGIN_ROOT/scripts/waypoints.py "),
    ],
    "scripts/waypoints.py": [
        ('parts = ["waypoints", "list"]',
         'parts = ["python3", "$CLAUDE_PLUGIN_ROOT/scripts/waypoints.py", "list"]'),
        ("`waypoints.py ", "`python3 $CLAUDE_PLUGIN_ROOT/scripts/waypoints.py "),
        ("waypoints.py done", "python3 $CLAUDE_PLUGIN_ROOT/scripts/waypoints.py done"),
        ("waypoints.py config", "python3 $CLAUDE_PLUGIN_ROOT/scripts/waypoints.py config"),
        # catch-all for remaining un-backticked verb examples; the / lookbehind keeps the
        # scripts/ path itself (produced by the rules above) intact
        ("re:" + r"(?<!/)waypoints\.py(?=[\s).])", "python3 $CLAUDE_PLUGIN_ROOT/scripts/waypoints.py"),
    ],
    "waypoints_core.py": [
        ("`waypoints.py`", "`python3 $CLAUDE_PLUGIN_ROOT/scripts/waypoints.py`"),
        ("`waypoints.py ", "`python3 $CLAUDE_PLUGIN_ROOT/scripts/waypoints.py "),
        # un-backticked occurrences inside print() literals (quote-free replacement is safe there)
        ("waypoints.py ", "python3 $CLAUDE_PLUGIN_ROOT/scripts/waypoints.py "),
        ("re:" + r"(?<!/)waypoints\.py(?=[\s).])", "python3 $CLAUDE_PLUGIN_ROOT/scripts/waypoints.py"),
    ],
}

# component metadata per C2/C3 vocabulary (adaptation class / evidence level / surfaces)
COMPONENTS = [
    {"path": ".claude-plugin/plugin.json", "kind": "manifest",
     "adaptation_class": "mechanical", "evidence_level": "source-inspected",
     "surfaces": {"chat": True, "cowork": True, "code": True},
     "notes": "same name+version as the host manifest; an installed marketplace plugin wins "
              "over a synced copy in Code, so no double-run"},
    {"path": "skills/waypoints/SKILL.md", "kind": "skill",
     "adaptation_class": "mechanical", "evidence_level": "source-inspected",
     "surfaces": {"chat": True, "cowork": True, "code": True},
     "notes": "CLI references rewritten bin/ -> scripts/; strict-YAML frontmatter pinned by tests"},
    {"path": "commands/waypoints-gated.md", "kind": "command",
     "adaptation_class": "mechanical", "evidence_level": "source-inspected",
     "surfaces": {"chat": True, "cowork": True, "code": True},
     "notes": "slash command; CLI reference rewritten bin/ -> scripts/"},
    {"path": "commands/waypoints-pane.md", "kind": "command",
     "adaptation_class": "native-unchanged", "evidence_level": "source-inspected",
     "surfaces": {"chat": True, "cowork": True, "code": True},
     "notes": "slash command doc so the desktop autocomplete lists it; the pane mod intercepts command.run where mods run"},
    {"path": "hooks/hooks.json", "kind": "hooks",
     "adaptation_class": "mechanical", "evidence_level": "source-inspected",
     "surfaces": {"chat": False, "cowork": True, "code": True},
     "notes": "Chat ignores plugin hooks, Cowork loads them; SessionStart banner hook"},
    {"path": "hooks/waypoints.py", "kind": "hook-script",
     "adaptation_class": "native-unchanged", "evidence_level": "source-inspected",
     "surfaces": {"chat": False, "cowork": True, "code": True},
     "notes": "stdlib-only, reads the store JSON directly; host-only PATH guidance in the banner note is rewritten to the scripts/ invocation by TRANSFORMS"},
    {"path": "scripts/waypoints.py", "kind": "cli",
     "adaptation_class": "mechanical", "evidence_level": "source-inspected",
     "surfaces": {"chat": False, "cowork": True, "code": True},
     "notes": "moved bin/ -> scripts/ per C1; adds the portable root to sys.path and imports "
              "the core modules copied alongside at the root"},
    {"path": "waypoints_core.py", "kind": "library",
     "adaptation_class": "native-unchanged", "evidence_level": "source-inspected",
     "surfaces": {"chat": False, "cowork": True, "code": True},
     "notes": "store logic at the portable root — bin/waypoints.py puts the root on sys.path"},
    {"path": "waypoints_menu.py", "kind": "library",
     "adaptation_class": "native-unchanged", "evidence_level": "source-inspected",
     "surfaces": {"chat": False, "cowork": True, "code": True},
     "notes": "interactive selector; imports waypoints_core from the same root"},
    {"path": "__init__.py", "kind": "library",
     "adaptation_class": "native-unchanged", "evidence_level": "source-inspected",
     "surfaces": {"chat": False, "cowork": True, "code": True},
     "notes": "package marker copied with the root modules"},
    {"path": "hooks/register.tsx", "kind": "mod",
     "adaptation_class": "native-unchanged", "evidence_level": "source-inspected",
     "surfaces": {"chat": False, "cowork": False, "code": True},
     "notes": "Claude Code mod: pane + band drawn only when display is pane or both; finds the CLI under bin/ or scripts/; builds without mod support ignore it"},
    {"path": "types/index.d.ts", "kind": "mod-types",
     "adaptation_class": "native-unchanged", "evidence_level": "source-inspected",
     "surfaces": {"chat": False, "cowork": False, "code": True},
     "notes": "type contract for the mod's session state"},
]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def git(args, cwd):
    try:
        return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True,
                              check=True).stdout.strip()
    except FileNotFoundError:
        sys.exit("build-portable.py: git binary not found — pass --commit <sha> explicitly")
    except subprocess.CalledProcessError as e:
        sys.exit(f"build-portable.py: git {' '.join(args)} failed: {e.stderr.strip()}")


def source_identity(root, commit_override):
    commit = commit_override or git(["rev-parse", "HEAD"], root)
    remote = ""
    try:
        remote = git(["remote", "get-url", "origin"], root)
    except SystemExit:
        remote = ""
    # owner/repo from the remote URL (git@host:owner/repo[.git] or https://host/owner/repo[.git])
    m = re.match(r"(?:git@[^:]+:|https://[^/]+/)([^/]+/[^/]+?)(?:\.git)?$", remote or "")
    source_repo = m.group(1) if m else FALLBACK_SOURCE_REPO
    return source_repo, commit


def build_tree(root, dest):
    """Write the portable package into dest/ (a fresh dir), applying TRANSFORMS."""
    with open(os.path.join(root, ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    for rel in COPY_FILES:
        host_rel = HOST_TO_PORTABLE.get(rel, rel)
        src = os.path.join(root, host_rel)
        dst = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if rel in TRANSFORMS:
            with open(src, encoding="utf-8") as i:
                text = i.read()
            for old, new in TRANSFORMS[rel]:
                if old.startswith("re:"):
                    # catch-all regex rules may legitimately match nothing (earlier rules
                    # already rewrote the file); literal rules must always match
                    text, _n = re.subn(old[3:], new, text)
                else:
                    assert old in text, f"transform anchor missing in {rel}: {old[:60]!r}"
                    text = text.replace(old, new)
            with open(dst, "w", encoding="utf-8") as o:
                o.write(text)
        else:
            with open(src, "rb") as i, open(dst, "wb") as o:
                shutil.copyfileobj(i, o)
        os.chmod(dst, 0o755 if rel.endswith((".sh", ".py")) else 0o644)
    return manifest


def write_build_json(dest, root, commit_override, repo_override=None):
    source_repo, commit = source_identity(root, commit_override)
    if repo_override:
        source_repo = repo_override
    files = {}
    for dirpath, _dn, filenames in os.walk(dest):
        for fn in sorted(filenames):
            p = os.path.join(dirpath, fn)
            files[os.path.relpath(p, dest).replace(os.sep, "/")] = sha256_file(p)
    doc = {
        "schema": SCHEMA,
        "source_repo": source_repo,
        "source_commit": commit,
        "builder": BUILDER,
        "builder_version": BUILDER_VERSION,
        "transform_version": TRANSFORM_VERSION,
        "files": files,
        "components": COMPONENTS,
    }
    with open(os.path.join(dest, "PORTABLE-BUILD.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps(doc, indent=2, sort_keys=True) + "\n")


IGNORE_DIRS = {"__pycache__", ".pytest_cache", ".git"}
IGNORE_SUFFIXES = (".pyc", ".pyo")


def walk_files(root):
    """Package files only — runtime litter (__pycache__ bytecode written when the
    portable CLI runs from its own root) is never part of the package or the diff."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for fn in sorted(filenames):
            if fn.endswith(IGNORE_SUFFIXES):
                continue
            p = os.path.join(dirpath, fn)
            out[os.path.relpath(p, root).replace(os.sep, "/")] = p
    return out


def diff_trees(a, b):
    """Relative paths that differ between two dirs: content hash, existence, OR file mode."""
    fa, fb = walk_files(a), walk_files(b)
    out = []
    for rel in sorted(set(fa) | set(fb)):
        pa, pb = fa.get(rel), fb.get(rel)
        if pa is None or pb is None:
            out.append(rel)
            continue
        if sha256_file(pa) != sha256_file(pb):
            out.append(rel)
            continue
        if (os.lstat(pa).st_mode & 0o777) != (os.lstat(pb).st_mode & 0o777):
            out.append(rel + " (mode)")
    return out


def swap_in(fresh, portable):
    """Replace portable/ with the fresh build (temp-built first, so an interrupt never
    leaves a half-written committed dir)."""
    if os.path.isdir(portable):
        shutil.rmtree(portable)
    os.rename(fresh, portable)


def write_zip(build_dir, out_dir, name):
    os.makedirs(out_dir, exist_ok=True)
    zpath = os.path.join(out_dir, f"{name}-portable.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in sorted(walk_files(build_dir)):
            p = os.path.join(build_dir, rel)
            zi = zipfile.ZipInfo(rel, date_time=ZIP_EPOCH)          # fixed timestamp
            mode = 0o755 if rel.endswith((".sh", ".py")) else 0o644
            zi.external_attr = (mode & 0xFFFF) << 16                 # fixed mode
            zi.compress_type = zipfile.ZIP_DEFLATED
            with open(p, "rb") as f:
                z.writestr(zi, f.read())
    return zpath


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="build-portable.py",
        description="Generate the committed portable/ package (COORDINATION C1/C2) from the "
                    "host tree. Never hand-edit portable/.")
    ap.add_argument("--check", action="store_true",
                    help="rebuild in a temp dir stamped with the COMMITTED source_commit and "
                         "diff against portable/; exit 1 listing drift")
    ap.add_argument("--zip", action="store_true",
                    help="also emit the upload zip from a temp build (portable/ is NOT touched)")
    ap.add_argument("--out", metavar="DIR", default=None, help="zip output dir (default dist/)")
    ap.add_argument("--commit", metavar="SHA", default=None, help="record this source_commit")
    args = ap.parse_args(argv)

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    portable = os.path.join(root, "portable")

    # --check is commit-stable: stamp the fresh build with the COMMITTED source_commit,
    # so the gate is green at the shipping commit (a SHA cannot contain itself).
    check_commit = args.commit
    check_repo = None
    if args.check and check_commit is None and os.path.isfile(
            os.path.join(portable, "PORTABLE-BUILD.json")):
        with open(os.path.join(portable, "PORTABLE-BUILD.json"), encoding="utf-8") as f:
            committed = json.load(f)
        check_commit = committed.get("source_commit")
        check_repo = committed.get("source_repo")

    with tempfile.TemporaryDirectory() as tmp:
        fresh = os.path.join(tmp, "portable")
        os.makedirs(fresh)
        build_tree(root, fresh)
        write_build_json(fresh, root, check_commit or args.commit, check_repo)

        if args.check:
            if not os.path.isdir(portable):
                print("✗ portable/ does not exist — run scripts/build-portable.py first")
                return 1
            drift = diff_trees(fresh, portable)
            if drift:
                print("✗ portable/ drifted from a fresh build:")
                for rel in drift:
                    print("  ", rel)
                print("  fix: run scripts/build-portable.py and commit the result")
                return 1
            print("✓ portable/ matches a fresh build")
            return 0

        if args.zip:
            with open(os.path.join(root, ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
                name = json.load(f)["name"]
            zpath = write_zip(fresh, args.out or os.path.join(root, "dist"), name)
            print(f"✓ wrote {zpath} (from a temp build; portable/ untouched)")
            return 0  # --zip must never mutate the committed portable/ (test side-effect pin)

        swap_in(fresh, portable)
    n = len(walk_files(portable))
    print(f"✓ built portable/ ({n} files) + PORTABLE-BUILD.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())

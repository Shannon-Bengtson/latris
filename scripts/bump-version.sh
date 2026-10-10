#!/usr/bin/env bash
set -euo pipefail

# scripts/bump-version.sh — Bump the package version, commit, and tag.
#
# Usage:
#   bash scripts/bump-version.sh 0.3.1
#   bash scripts/bump-version.sh 0.3.1 --no-tag   # bump + commit only, skip tag
#
# Updates:
#   - src/latris/__init__.py  (__version__ — read by hatchling)
#
# Then commits the bump and creates a git tag (v0.3.1). The v* tag is what
# triggers .github/workflows/publish.yml to publish to PyPI — so remember
# to push the tag.

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# ── Parse arguments ───────────────────────────────────────────────────
CREATE_TAG=true
VERSION=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-tag) CREATE_TAG=false; shift ;;
        -*)       echo "Unknown flag: $1" >&2; exit 1 ;;
        *)        VERSION="$1"; shift ;;
    esac
done

if [[ -z "$VERSION" ]]; then
    echo "Usage: bash scripts/bump-version.sh <version> [--no-tag]" >&2
    echo "" >&2
    echo "Examples:" >&2
    echo "  bash scripts/bump-version.sh 0.3.1" >&2
    echo "  bash scripts/bump-version.sh 0.3.1 --no-tag" >&2
    exit 1
fi

# ── Validate version format (semver-ish: X.Y.Z with optional pre-release) ─
if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?$ ]]; then
    echo "Error: version must be semver (e.g. 0.3.1 or 1.0.0-beta.1)" >&2
    exit 1
fi

# ── Check for clean working tree ──────────────────────────────────────
if ! git -C "$REPO_ROOT" diff --quiet || ! git -C "$REPO_ROOT" diff --cached --quiet; then
    echo "Error: working tree has uncommitted changes. Commit or stash first." >&2
    exit 1
fi

# ── Read current version ──────────────────────────────────────────────
INIT_PY="$REPO_ROOT/src/latris/__init__.py"

CURRENT=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$INIT_PY")
echo "Current version: $CURRENT"
echo "New version:     $VERSION"

if [[ "$CURRENT" == "$VERSION" ]]; then
    echo "Error: version is already $VERSION" >&2
    exit 1
fi

# ── Update Python version ─────────────────────────────────────────────
sed -i "s/__version__ = \".*\"/__version__ = \"$VERSION\"/" "$INIT_PY"
echo "Updated $INIT_PY"

# ── Commit ─────────────────────────────────────────────────────────────
git -C "$REPO_ROOT" add "$INIT_PY"
git -C "$REPO_ROOT" commit -m "Bump version to $VERSION"
echo "Committed version bump"

# ── Tag ────────────────────────────────────────────────────────────────
if [[ "$CREATE_TAG" == true ]]; then
    TAG="v$VERSION"
    git -C "$REPO_ROOT" tag "$TAG"
    echo "Created tag $TAG"
    echo ""
    echo "Done. Push with:"
    echo "  git push && git push --tags"
    echo "(pushing the tag triggers the PyPI publish workflow)"
else
    echo ""
    echo "Done (no tag created). Push with:"
    echo "  git push"
fi

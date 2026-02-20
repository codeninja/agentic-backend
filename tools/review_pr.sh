#!/usr/bin/env bash
# Usage: review_pr.sh <issue_number> <worktree_path>
# Generates a diff + issue body for review context
set -euo pipefail

ISSUE=$1
WORKTREE=$2

echo "=== ISSUE #${ISSUE} SPEC ==="
gh issue view "$ISSUE" --json body -q .body

echo ""
echo "=== DIFF (main..branch) ==="
cd "$WORKTREE"
git diff main --stat
echo "---"
git diff main -- '*.py'

echo ""
echo "=== TEST RESULTS ==="
uv run pytest -q 2>&1 | tail -20

echo ""
echo "=== LINT ==="
uv run ruff check . 2>&1 | tail -5

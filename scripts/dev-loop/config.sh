#!/usr/bin/env bash
# =============================================================================
# Config — constants and directory setup for the dev loop
# =============================================================================

REPO="codeninja/ninja-stack"
PROJECT_NUM=4
PROJECT_OWNER="codeninja"
PROJECT_ID="PVT_kwHNOkLOAT6Qtg"
FIELD_ID="PVTSSF_lAHNOkLOAT6Qts4Pf31M"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORKTREE_BASE="/tmp/ns-worktrees"
LOG_DIR="$PROJECT_ROOT/.dev-loop-logs"
BOUNCE_FILE="$PROJECT_ROOT/.dev-loop-bounces"
MAX_BOUNCES=2
MIN_TODO_FOR_AUDIT=5

# Concurrency limits per agent type
MAX_TRIAGE_AGENTS=2
MAX_PLANNING_AGENTS=2
MAX_IMPLEMENT_AGENTS=3
MAX_REVIEW_AGENTS=2
MAX_AUDIT_AGENTS=1

# Rate limit thresholds
RATE_LIMIT_THRESHOLD=1000
RATE_LIMIT_CACHE="$PROJECT_ROOT/.dev-loop-rate-limit"
RATE_LIMIT_CHECK_INTERVAL=30

# Board data cache
BOARD_CACHE_FILE="$PROJECT_ROOT/.dev-loop-board-cache"
BOARD_CACHE_LOCK="$PROJECT_ROOT/.dev-loop-board-cache.lock"
BOARD_CACHE_TTL=60

# PID tracking
LOOP_PIDS_FILE="$PROJECT_ROOT/.dev-loop-loop-pids"
AGENT_PIDS_DIR="$PROJECT_ROOT/.dev-loop-agents"

# Board status option IDs
STATUS_TRIAGE="7075b0bd"
STATUS_PLANNING="5860e624"
STATUS_TODO="398c03ac"
STATUS_IN_PROGRESS="20fd4c4d"
STATUS_AI_REVIEW="35df9b65"
STATUS_REJECTED="1b81d027"
STATUS_IN_REVIEW="bbfc519d"
STATUS_DONE="873d8d61"
STATUS_NEED_HUMAN="f96e10cc"

# ninja-board CLI — resolve from venv or PATH
NINJA_BOARD="${PROJECT_ROOT}/.venv/bin/ninja-board"
if [[ ! -x "$NINJA_BOARD" ]]; then
    NINJA_BOARD="$(command -v ninja-board 2>/dev/null || echo "uv run python -m ninja_devloop.cli")"
fi

mkdir -p "$LOG_DIR" "$WORKTREE_BASE" "$AGENT_PIDS_DIR"

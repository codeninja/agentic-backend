#!/usr/bin/env bash
# =============================================================================
# NinjaStack Autonomous Development Loop
# =============================================================================
# Continuously monitors the GitHub project board and orchestrates Claude Code
# agents to implement, review, and merge tickets.
#
# Usage:     ./scripts/dev-loop.sh
# Stop:      touch stop.txt      (immediate abort)
# Shutdown:  touch shutdown.txt   (graceful — waits for agents, then exits)
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
REPO="codeninja/ninja-stack"
PROJECT_NUM=4
PROJECT_OWNER="codeninja"
PROJECT_ID="PVT_kwHNOkLOAT6Qtg"
FIELD_ID="PVTSSF_lAHNOkLOAT6Qts4Pf31M"
CYCLE_DELAY=180  # 3 minutes between cycles
MAX_IN_PROGRESS=3
MIN_TODO_FOR_AUDIT=5
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKTREE_BASE="/tmp/ns-worktrees"
PIDS_FILE="$PROJECT_ROOT/.dev-loop-pids"
LOG_DIR="$PROJECT_ROOT/.dev-loop-logs"
BOUNCE_FILE="$PROJECT_ROOT/.dev-loop-bounces"  # tracks review/reject cycles per issue
MAX_BOUNCES=2

# Board status option IDs (from project field config)
STATUS_TRIAGE="7075b0bd"
STATUS_PLANNING="5860e624"
STATUS_TODO="398c03ac"
STATUS_IN_PROGRESS="20fd4c4d"
STATUS_AI_REVIEW="35df9b65"
STATUS_REJECTED="1b81d027"
STATUS_IN_REVIEW="bbfc519d"
STATUS_DONE="873d8d61"
STATUS_NEED_HUMAN="f96e10cc"

mkdir -p "$LOG_DIR" "$WORKTREE_BASE"
touch "$PIDS_FILE"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
die() { log "FATAL: $*"; exit 1; }

check_stop() {
    if [[ -f "$PROJECT_ROOT/stop.txt" ]]; then
        log "🛑 stop.txt detected — aborting."
        exit 0
    fi
}

# Graceful shutdown: no new actions, wait for running agents, clean up
check_shutdown() {
    if [[ -f "$PROJECT_ROOT/shutdown.txt" ]]; then
        log "🔻 shutdown.txt detected — initiating graceful shutdown..."
        log "  Waiting for running agents to finish..."
        while any_agents_running; do
            clean_pids
            log "  ⏳ Agents still running — checking again in 30s..."
            sleep 30
        done
        log "  All agents finished."
        rm -f "$PROJECT_ROOT/shutdown.txt"
        log "  Removed shutdown.txt."
        log "🛑 Graceful shutdown complete."
        exit 0
    fi
}

# Get board items as JSON
get_board() {
    gh project item-list "$PROJECT_NUM" --owner "$PROJECT_OWNER" --format json 2>/dev/null
}

# Count items by status
count_status() {
    local status="$1"
    get_board | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(sum(1 for i in data['items'] if i.get('status') == '$status'))
"
}

# Get issue numbers by status
issues_by_status() {
    local status="$1"
    get_board | python3 -c "
import json, sys
data = json.load(sys.stdin)
for item in data['items']:
    if item.get('status') == '$status':
        c = item.get('content', {})
        num = c.get('number')
        if num: print(num)
"
}

# Get project item ID for an issue number
get_item_id() {
    local issue_num="$1"
    get_board | python3 -c "
import json, sys
data = json.load(sys.stdin)
for item in data['items']:
    c = item.get('content', {})
    if c.get('number') == $issue_num:
        print(item['id'])
        break
"
}

# Move issue to a status on the board
set_status() {
    local issue_num="$1"
    local status_id="$2"
    local item_id
    item_id=$(get_item_id "$issue_num")
    if [[ -z "$item_id" ]]; then
        log "  ⚠️  Could not find board item for #$issue_num"
        return 1
    fi
    gh api graphql -f query="mutation {
        updateProjectV2ItemFieldValue(input: {
            projectId: \"$PROJECT_ID\",
            itemId: \"$item_id\",
            fieldId: \"$FIELD_ID\",
            value: { singleSelectOptionId: \"$status_id\" }
        }) { projectV2Item { id } }
    }" >/dev/null 2>&1
}

# Check if any tracked PIDs are still running
any_agents_running() {
    if [[ ! -s "$PIDS_FILE" ]]; then
        return 1
    fi
    while IFS= read -r pid; do
        if kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
    done < "$PIDS_FILE"
    # All dead — clean up
    > "$PIDS_FILE"
    return 1
}

# Track a PID
track_pid() {
    echo "$1" >> "$PIDS_FILE"
}

# Clean dead PIDs from tracking
clean_pids() {
    if [[ ! -s "$PIDS_FILE" ]]; then return; fi
    local alive=""
    while IFS= read -r pid; do
        if kill -0 "$pid" 2>/dev/null; then
            alive+="$pid"$'\n'
        fi
    done < "$PIDS_FILE"
    echo -n "$alive" > "$PIDS_FILE"
}

# Get Todo issues sorted by priority (high > medium > low), excluding critical (human-only)
get_prioritized_todo_issues() {
    local todo_nums
    todo_nums=$(issues_by_status "Todo")
    [[ -z "$todo_nums" ]] && return

    # Fetch labels for each issue and sort by priority
    local sorted=""
    for num in $todo_nums; do
        local labels
        labels=$(gh issue view "$num" --repo "$REPO" --json labels -q '[.labels[].name] | join(",")' 2>/dev/null)

        local weight=50  # default: untagged = medium
        if echo "$labels" | grep -q "priority: critical"; then
            weight=1
        elif echo "$labels" | grep -q "priority: high"; then
            weight=10
        elif echo "$labels" | grep -q "priority: medium"; then
            weight=50
        elif echo "$labels" | grep -q "priority: low"; then
            weight=90
        fi
        sorted+="${weight} ${num}"$'\n'
    done

    echo "$sorted" | sort -n | awk '{print $2}' | grep -v '^$'
}

# ---------------------------------------------------------------------------
# Bounce tracking — count review↔rejected cycles per issue
# ---------------------------------------------------------------------------
get_bounce_count() {
    local issue_num="$1"
    if [[ -f "$BOUNCE_FILE" ]]; then
        grep -c "^${issue_num}$" "$BOUNCE_FILE" 2>/dev/null || echo 0
    else
        echo 0
    fi
}

record_bounce() {
    local issue_num="$1"
    echo "$issue_num" >> "$BOUNCE_FILE"
}

# Escalate to Need Human and notify via OpenClaw → Claw → Dallas
escalate_to_human() {
    local issue_num="$1"
    local title="$2"
    local bounces="$3"
    log "  🚨 #$issue_num has bounced $bounces times — escalating to Need Human"
    set_status "$issue_num" "$STATUS_NEED_HUMAN"
    # Notify via OpenClaw system event → wakes Claw who notifies Dallas
    openclaw system event --text "🚨 Dev Loop Escalation: Issue #$issue_num ($title) has failed AI review $bounces times and has been moved to Need Human. Please review manually: https://github.com/$REPO/issues/$issue_num" --mode now 2>/dev/null || true
}

# Get issue title
get_issue_title() {
    gh issue view "$1" --repo "$REPO" --json title -q '.title' 2>/dev/null
}

# Get issue body
get_issue_body() {
    gh issue view "$1" --repo "$REPO" --json body -q '.body' 2>/dev/null
}

# Get PR number for a branch
get_pr_for_branch() {
    gh pr list --repo "$REPO" --head "$1" --json number -q '.[0].number' 2>/dev/null
}

# ---------------------------------------------------------------------------
# Phase 1: Audit — if ≤ MIN_TODO tickets, spawn gap analysis
# ---------------------------------------------------------------------------
phase_audit() {
    local todo_count
    todo_count=$(count_status "Todo")
    log "📋 Todo: $todo_count tickets"

    if (( todo_count <= MIN_TODO_FOR_AUDIT )); then
        log "🔍 ≤$MIN_TODO_FOR_AUDIT tickets in Todo — spawning audit agent..."
        local audit_log="$LOG_DIR/audit-$(date +%s).log"

        claude --dangerously-skip-permissions -p "You are auditing the NinjaStack project for gaps, bugs, and security issues.

PROJECT ROOT: $PROJECT_ROOT
REPO: $REPO

Your task:
1. Read the README.md to understand the project vision
2. Read the implementation plans in docs/ and implementation_plans/
3. Examine the source code in libs/ and apps/
4. Identify: security vulnerabilities, logic flaws, missing implementations vs the vision, broken integrations
5. For EACH issue found, create a GitHub issue using: gh issue create --repo $REPO --title '<title>' --label 'bug' --label 'priority: <high|medium|low>' --body '<detailed body>'
   IMPORTANT: NEVER use 'priority: critical' — that label is reserved for human-created tickets only. Use 'priority: high' as your maximum.
6. After creating each issue, add it to project board 4: gh project item-add $PROJECT_NUM --owner $PROJECT_OWNER --url <issue_url>
7. Do NOT create duplicates — first run: gh issue list --repo $REPO --state open --json title,number
   and check existing titles before creating new ones

Focus on actionable, specific issues. Each issue should have:
- Clear description of the problem
- Current vs expected behavior
- Affected files
- Impact assessment

ORGANIZATION:
- Group related issues under Epic issues. An Epic is a GitHub issue with the 'epic' label that describes a broad goal.
- Before creating individual issues, check if a relevant Epic already exists: gh issue list --repo $REPO --label epic --state open --json title,number
- If no Epic exists for the area, create one first: gh issue create --repo $REPO --title 'Epic: <area>' --label 'epic' --body '<vision-level description of the goal>'
- Each individual issue should reference its parent Epic in the body: 'Part of #<epic_number>'
- Use 'enhancement' label for new features, 'bug' for defects
- Assign priority labels: 'priority: high', 'priority: medium', or 'priority: low' (NEVER 'priority: critical' — reserved for humans)

Do NOT create issues for things that are already tracked." \
            --output-format text \
            > "$audit_log" 2>&1 &
        track_pid $!
        log "  🤖 Audit agent started (PID $!, log: $audit_log)"
    fi
}

# ---------------------------------------------------------------------------
# Phase 2: Implement — pick Todo tickets, spawn Claude workers
# ---------------------------------------------------------------------------
phase_implement() {
    local in_progress_count
    in_progress_count=$(count_status "In Progress")
    log "🔨 In Progress: $in_progress_count tickets"

    if (( in_progress_count >= MAX_IN_PROGRESS )); then
        log "  ⏸️  Already $in_progress_count in progress (max $MAX_IN_PROGRESS), skipping."
        return
    fi

    # Prioritize rejected tickets first, then todo sorted by priority
    local rejected_issues
    rejected_issues=$(issues_by_status "Rejected")
    local todo_issues
    todo_issues=$(get_prioritized_todo_issues)

    # Merge: rejected first, then prioritized todo
    local all_issues
    all_issues=$(echo -e "${rejected_issues}\n${todo_issues}" | grep -v '^$')

    local slots=$(( MAX_IN_PROGRESS - in_progress_count ))
    local started=0

    while IFS= read -r issue_num && (( started < slots )); do
        [[ -z "$issue_num" ]] && continue
        check_stop

        local title
        title=$(get_issue_title "$issue_num")
        local body
        body=$(get_issue_body "$issue_num")
        local branch="fix/issue-${issue_num}"
        local worktree="$WORKTREE_BASE/issue-${issue_num}"
        local impl_log="$LOG_DIR/impl-${issue_num}-$(date +%s).log"

        # Skip if worktree already exists (previous run still active)
        if [[ -d "$worktree" ]]; then
            log "  ⏭️  #$issue_num worktree already exists, skipping."
            continue
        fi

        log "  🚀 Starting implementation of #$issue_num: $title"
        set_status "$issue_num" "$STATUS_IN_PROGRESS"

        # Create worktree
        (
            cd "$PROJECT_ROOT"
            git fetch origin main 2>/dev/null
            git worktree add -b "$branch" "$worktree" origin/main 2>/dev/null || \
                git worktree add "$worktree" "$branch" 2>/dev/null
        )

        # Spawn Claude Code to implement
        claude --dangerously-skip-permissions -p "You are implementing a fix for GitHub issue #$issue_num in the NinjaStack project.

ISSUE TITLE: $title

ISSUE BODY:
$body

WORKING DIRECTORY: $worktree
BRANCH: $branch

Your task:
1. Read the issue carefully and understand the requirements
2. Read relevant source files to understand the current implementation
3. Implement the fix/feature as described in the issue
4. Write or update tests to cover your changes
5. Run the test suite: cd $worktree && uv sync && uv run pytest --tb=short
6. Ensure ALL tests pass (not just your new ones)
7. Commit your changes with a descriptive message: git add -A && git commit -m 'fix: <description> (closes #$issue_num)'
8. Push: git push -u origin $branch
9. Create a PR: gh pr create --repo $REPO --head $branch --base main --title 'fix: $title' --body 'Closes #$issue_num\n\n<summary of changes>'

IMPORTANT:
- Do NOT merge the PR — it needs review first
- Make sure tests pass before pushing
- Keep changes focused on the issue scope" \
            --output-format text \
            > "$impl_log" 2>&1 &
        track_pid $!
        log "  🤖 Implementation agent started for #$issue_num (PID $!, log: $impl_log)"
        (( started++ ))
    done <<< "$all_issues"
}

# ---------------------------------------------------------------------------
# Phase 3: AI Review — review PRs in AI Review status
# ---------------------------------------------------------------------------
phase_review() {
    local review_issues
    review_issues=$(issues_by_status "AI Review")

    if [[ -z "$review_issues" ]]; then
        return
    fi

    while IFS= read -r issue_num; do
        [[ -z "$issue_num" ]] && continue
        check_stop

        local title
        title=$(get_issue_title "$issue_num")
        local body
        body=$(get_issue_body "$issue_num")
        local branch="fix/issue-${issue_num}"
        local pr_num
        pr_num=$(get_pr_for_branch "$branch")
        local review_log="$LOG_DIR/review-${issue_num}-$(date +%s).log"

        if [[ -z "$pr_num" ]]; then
            log "  ⚠️  No PR found for #$issue_num (branch $branch), skipping review."
            continue
        fi

        log "  🔎 Reviewing PR #$pr_num for issue #$issue_num: $title"
        local review_dir="$WORKTREE_BASE/review-${issue_num}"

        # Create fresh worktree for review
        (
            cd "$PROJECT_ROOT"
            git fetch origin "$branch" main 2>/dev/null
            rm -rf "$review_dir" 2>/dev/null
            git worktree add "$review_dir" "origin/$branch" 2>/dev/null || true
        )

        claude --dangerously-skip-permissions -p "You are a code reviewer for the NinjaStack project.

ISSUE #$issue_num: $title

ISSUE BODY:
$body

PR #$pr_num on branch: $branch
REVIEW DIRECTORY: $review_dir

PROJECT VISION (from README):
NinjaStack is a schema-first agentic backend framework. It transforms database schemas into fully functional agentic backends with AI agents, GraphQL APIs, authentication, RBAC, and deployment manifests. Key principles: explicit > implicit, composition > inheritance, constraints > convention, model-agnostic via LiteLLM.

Your task:
1. Run: cd $review_dir && git diff origin/main..HEAD --stat
2. Review ALL changed files carefully
3. Run tests: uv sync && uv run pytest --tb=short
4. Evaluate against these criteria:
   a. Does the code correctly implement what the issue describes?
   b. Are there tests covering the changes?
   c. Do all tests pass?
   d. Is the code consistent with the project's architecture and patterns?
   e. Are there security concerns?
   f. Does it align with the project vision (schema-first, model-agnostic, explicit contracts)?

IF THE CODE PASSES REVIEW:
- Run: gh pr review $pr_num --repo $REPO --approve --body 'AI Review: APPROVED. <brief summary of what was reviewed and why it passes>'
- Then output exactly: REVIEW_RESULT=APPROVED

IF THE CODE FAILS REVIEW:
- Run: gh pr review $pr_num --repo $REPO --request-changes --body 'AI Review: CHANGES REQUESTED.\n\n<detailed list of issues found, with file names and line numbers>\n\nPlease address these issues and re-request review.'
- Then output exactly: REVIEW_RESULT=REJECTED

Be thorough but fair. Only reject for real issues, not style preferences." \
            --output-format text \
            > "$review_log" 2>&1

        # Parse result and update board
        if grep -q "REVIEW_RESULT=APPROVED" "$review_log"; then
            log "  ✅ PR #$pr_num APPROVED — merging and moving to Done"
            gh pr merge "$pr_num" --repo "$REPO" --squash --delete-branch 2>/dev/null || true
            set_status "$issue_num" "$STATUS_DONE"
            # Cleanup worktrees
            (cd "$PROJECT_ROOT" && git worktree remove "$review_dir" 2>/dev/null || true)
            (cd "$PROJECT_ROOT" && git worktree remove "$WORKTREE_BASE/issue-${issue_num}" 2>/dev/null || true)
        elif grep -q "REVIEW_RESULT=REJECTED" "$review_log"; then
            record_bounce "$issue_num"
            local bounces
            bounces=$(get_bounce_count "$issue_num")
            if (( bounces >= MAX_BOUNCES )); then
                escalate_to_human "$issue_num" "$title" "$bounces"
            else
                log "  ❌ PR #$pr_num REJECTED (bounce $bounces/$MAX_BOUNCES) — moving to Rejected for rework"
                set_status "$issue_num" "$STATUS_REJECTED"
            fi
            (cd "$PROJECT_ROOT" && git worktree remove "$review_dir" 2>/dev/null || true)
        else
            log "  ⚠️  Review result unclear for #$issue_num — check log: $review_log"
        fi
    done <<< "$review_issues"
}

# ---------------------------------------------------------------------------
# Phase 4: Promote — move completed implementations to AI Review
# ---------------------------------------------------------------------------
phase_promote() {
    # Check In Progress items for completed PRs
    local in_progress_issues
    in_progress_issues=$(issues_by_status "In Progress")

    if [[ -z "$in_progress_issues" ]]; then
        return
    fi

    while IFS= read -r issue_num; do
        [[ -z "$issue_num" ]] && continue

        local branch="fix/issue-${issue_num}"
        local pr_num
        pr_num=$(get_pr_for_branch "$branch")

        if [[ -n "$pr_num" ]]; then
            # PR exists — check if CI passed
            local pr_state
            pr_state=$(gh pr view "$pr_num" --repo "$REPO" --json mergeable,statusCheckRollup -q '.mergeable' 2>/dev/null)

            # If PR exists, promote to AI Review
            log "  📤 PR #$pr_num exists for #$issue_num — promoting to AI Review"
            set_status "$issue_num" "$STATUS_AI_REVIEW"
        fi
    done <<< "$in_progress_issues"
}

# ---------------------------------------------------------------------------
# Main Loop
# ---------------------------------------------------------------------------
main() {
    log "============================================"
    log "🥷 NinjaStack Dev Loop Starting"
    log "  Project: $REPO (board #$PROJECT_NUM)"
    log "  Cycle delay: ${CYCLE_DELAY}s"
    log "  Max in progress: $MAX_IN_PROGRESS"
    log "  Worktrees: $WORKTREE_BASE"
    log "  Logs: $LOG_DIR"
    log "  Stop: touch $PROJECT_ROOT/stop.txt"
    log "============================================"

    local cycle=0
    while true; do
        check_stop
        (( cycle++ ))
        log ""
        log "═══════════════ Cycle $cycle ═══════════════"

        # Clean up dead PIDs
        clean_pids

        # Skip if agents from previous cycle are still running
        if any_agents_running; then
            log "⏳ Agents still running from previous cycle — waiting..."
            sleep "$CYCLE_DELAY"
            continue
        fi

        # Pull latest main
        (cd "$PROJECT_ROOT" && git pull --rebase origin main 2>/dev/null || true)

        # Phase 1: Check if we need more tickets
        check_shutdown
        phase_audit

        # Phase 2: Promote completed work to review
        check_shutdown
        phase_promote

        # Phase 3: Review PRs awaiting AI review
        check_shutdown
        phase_review

        # Phase 4: Start implementation on available tickets
        check_shutdown
        phase_implement

        # Board summary
        log ""
        log "📊 Board Status:"
        get_board | python3 -c "
import json, sys
data = json.load(sys.stdin)
statuses = {}
for item in data['items']:
    s = item.get('status', 'No Status')
    statuses[s] = statuses.get(s, 0) + 1
for s in ['Todo', 'In Progress', 'AI Review', 'Rejected', 'In Review', 'Done']:
    print(f'  {s}: {statuses.get(s, 0)}')
"

        log ""
        check_shutdown
        log "💤 Sleeping ${CYCLE_DELAY}s until next cycle..."
        sleep "$CYCLE_DELAY"
    done
}

main "$@"

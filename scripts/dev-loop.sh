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
set -uo pipefail
# Note: NOT using set -e — individual failures are handled per-phase

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
        rm -f "$PROJECT_ROOT/stop.txt"
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
    local found_alive=false
    while IFS= read -r pid; do
        [[ -z "$pid" ]] && continue
        if kill -0 "$pid" 2>/dev/null && [[ -d "/proc/$pid" ]]; then
            found_alive=true
            break
        fi
    done < "$PIDS_FILE"
    if $found_alive; then
        return 0
    fi
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
7. Then set the board status. Use the following GraphQL mutation for EACH new item:
   - For bugs/defects that need verification → set to Triage (option ID: $STATUS_TRIAGE). The GitHub Actions triage workflow will validate and plan them automatically.
     gh api graphql -f query='mutation { updateProjectV2ItemFieldValue(input: { projectId: \"$PROJECT_ID\", itemId: \"<ITEM_ID>\", fieldId: \"$FIELD_ID\", value: { singleSelectOptionId: \"$STATUS_TRIAGE\" } }) { projectV2Item { id } } }'
   - For features, architectural changes, or enhancements → set to Planning (option ID: $STATUS_PLANNING):
     gh api graphql -f query='mutation { updateProjectV2ItemFieldValue(input: { projectId: \"$PROJECT_ID\", itemId: \"<ITEM_ID>\", fieldId: \"$FIELD_ID\", value: { singleSelectOptionId: \"$STATUS_PLANNING\" } }) { projectV2Item { id } } }'
   - Epics should always go to Planning.
   Get the item ID from the gh project item-add output (--format json) or by querying the board.
8. Do NOT create duplicates — first run: gh issue list --repo $REPO --state open --json title,number
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

    # Collect up to $slots candidates
    local -a candidates=()
    while IFS= read -r issue_num; do
        [[ -z "$issue_num" ]] && continue
        (( ${#candidates[@]} >= slots )) && break

        # Skip if worktree already exists (previous run still active)
        if [[ -d "$WORKTREE_BASE/issue-${issue_num}" ]]; then
            log "  ⏭️  #$issue_num worktree already exists, skipping."
            continue
        fi
        candidates+=("$issue_num")
    done <<< "$all_issues"

    if (( ${#candidates[@]} == 0 )); then
        log "  No candidates available."
        return
    fi

    # Spawn developer agents in parallel — each validates + implements
    local started=0
    for issue_num in "${candidates[@]}"; do
        check_stop
        local title
        title=$(get_issue_title "$issue_num")
        local body
        body=$(get_issue_body "$issue_num")
        local branch="fix/issue-${issue_num}"
        local worktree="$WORKTREE_BASE/issue-${issue_num}"
        local impl_log="$LOG_DIR/impl-${issue_num}-$(date +%s).log"

        log "  🚀 Starting developer for #$issue_num: $title"
        set_status "$issue_num" "$STATUS_IN_PROGRESS"

        # Create worktree and draft PR (always rebased on latest main)
        (
            cd "$PROJECT_ROOT"
            git fetch origin main 2>/dev/null
            if git worktree add -b "$branch" "$worktree" origin/main 2>/dev/null; then
                : # new branch, already on latest main
            else
                # Existing branch — check it out and rebase onto latest main
                git worktree add "$worktree" "$branch" 2>/dev/null
                cd "$worktree"
                git rebase origin/main 2>/dev/null || git rebase --abort 2>/dev/null
            fi
        )
        (
            cd "$worktree"
            git commit --allow-empty -m "wip: starting work on #$issue_num" 2>/dev/null
            git push -u origin "$branch" --force-with-lease 2>/dev/null
            gh pr create --repo "$REPO" --head "$branch" --base main \
                --title "fix: $title" \
                --body "Closes #$issue_num" \
                --draft 2>/dev/null
        )
        local draft_pr
        draft_pr=$(get_pr_for_branch "$branch")
        log "  📝 Draft PR #$draft_pr created for #$issue_num"

        # Single developer agent: validates THEN implements (or bails)
        claude --dangerously-skip-permissions -p "You are a developer assigned to GitHub issue #$issue_num in the NinjaStack project.

ISSUE TITLE: $title

ISSUE BODY:
$body

WORKING DIRECTORY: $worktree
BRANCH: $branch
DRAFT PR: #$draft_pr (already created)
REPO: $REPO

## PHASE 1: VALIDATION

Before writing any code, verify this ticket is still valid:
1. Read the relevant source files mentioned in the issue
2. Check if the problem still exists in the current codebase
3. Check if another PR or recent commit already fixed this (run: git log --oneline -20 in the main project at $PROJECT_ROOT)
4. Verify the proposed fix makes sense given the current architecture

If the issue is ALREADY RESOLVED or NOT NEEDED:
- Run: gh issue comment $issue_num --repo $REPO --body 'Dev Validation: This issue is already resolved. <explanation>'
- Run: gh issue close $issue_num --repo $REPO
- Run: gh pr close $draft_pr --repo $REPO --delete-branch
- Output: RESULT=UNNECESSARY
- Stop here. Do not continue to Phase 2.

If the issue NEEDS CLARIFICATION or has unclear/conflicting requirements:
- Run: gh issue comment $issue_num --repo $REPO --body 'Dev Validation: This ticket needs further planning. <explanation of what needs clarification>'
- Run: gh pr close $draft_pr --repo $REPO --delete-branch
- Output: RESULT=NEEDS_PLANNING
- Stop here. Do not continue to Phase 2.

If the issue is VALID and the problem exists, continue to Phase 2.

## PHASE 2: IMPLEMENTATION

QUALITY STANDARDS — NON-NEGOTIABLE:
- Write PRODUCTION-QUALITY code. No stubs, no mocks-as-implementation, no TODO placeholders, no shortcuts.
- Do not cut corners. If the issue requires a persistence layer, implement a real persistence layer. If it requires validation, implement real validation.
- Every public function must have docstrings. Every edge case mentioned in the issue must be handled.
- Do not introduce workarounds or hacks. Solve the root problem.
- Your code must be consistent with the project's architectural principles: explicit > implicit, composition > inheritance, constraints > convention.
- If you cannot implement the full solution properly, output RESULT=NEEDS_PLANNING with an explanation rather than shipping incomplete work.

1. Read the issue carefully and understand the requirements
2. Read relevant source files to understand the current implementation
3. Implement the fix/feature as described in the issue
4. Write or update tests to cover your changes
5. Run the test suite: cd $worktree && uv sync && uv run pytest --tb=short
6. Ensure ALL tests pass (not just your new ones)
7. Commit your changes: git add -A && git commit -m 'fix: <description> (closes #$issue_num)'
8. Push: git push origin $branch
9. Update the PR body: gh pr edit $draft_pr --repo $REPO --body 'Closes #$issue_num\n\n<summary of changes>'
10. Mark PR ready for review: gh pr ready $draft_pr --repo $REPO
11. Leave a handoff comment on the issue summarizing what you did and what the reviewer should focus on:
    gh issue comment $issue_num --repo $REPO --body '**Developer Handoff:**
    
    **What was done:**
    - <list of changes made, files modified>
    
    **Tests:**
    - <test results summary>
    
    **What the reviewer should check:**
    - <areas of concern, edge cases, architectural decisions made>
    
    **Next steps if approved:**
    - <any follow-up work needed, related issues>'
12. Output: RESULT=IMPLEMENTED

IMPORTANT:
- A draft PR already exists — do NOT create a new one
- Do NOT merge the PR — it needs review first
- Make sure tests pass before pushing
- Keep changes focused on the issue scope
- Your code WILL BE EVALUATED by an AI reviewer for: code quality, security best practices, and completeness of the solution against acceptance criteria. Incomplete or insecure implementations will be rejected." \
            --output-format text \
            > "$impl_log" 2>&1 &
        track_pid $!
        log "  🤖 Developer agent started for #$issue_num (PID $!, log: $impl_log)"
        started=$(( started + 1 ))
    done

    log "  🚀 $started developer agents spawned in parallel"
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

        # Create fresh worktree for review (rebased on latest main)
        (
            cd "$PROJECT_ROOT"
            git fetch origin "$branch" main 2>/dev/null
            rm -rf "$review_dir" 2>/dev/null
            git worktree remove "$review_dir" 2>/dev/null || true
            git worktree add "$review_dir" "origin/$branch" 2>/dev/null || true
            cd "$review_dir"
            # Rebase the review copy onto latest main so diff only shows branch changes
            git checkout -b "review-${issue_num}" 2>/dev/null || true
            git rebase origin/main 2>/dev/null || git rebase --abort 2>/dev/null
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
1. Run: cd $review_dir && git log --oneline origin/main..HEAD (to see branch commits)
2. Run: cd $review_dir && git diff origin/main...HEAD --stat (three dots = only changes introduced by this branch)
3. Review ALL changed files from that diff carefully — ONLY evaluate changes introduced by this branch, not pre-existing code
4. Run tests: uv sync && uv run pytest --tb=short
5. Evaluate against these criteria:
   a. Does the code correctly implement what the issue describes?
   b. Are there tests covering the changes?
   c. Do all tests pass?
   d. Is the code consistent with the project's architecture and patterns?
   e. Are there security concerns?
   f. Does it align with the project vision (schema-first, model-agnostic, explicit contracts)?

VIOLATIONS:
- If the developer missed something from the issue, misunderstood the requirements, or if tests are missing/failing → CHANGES REQUESTED
- If the code works but has identifiable security issues → CHANGES REQUESTED
- If the code implements the solution in a way that violates the project vision or architectural principles → CHANGES REQUESTED
- If the developer cheats tests, removes vital functionality, or introduces new issues → CHANGES REQUESTED
- If the developer introduces a workaround instead of addressing the root problem → HUMAN REVIEW NEEDED (escalate to Need Human)

IF THE CODE PASSES REVIEW:
- Run: gh pr review $pr_num --repo $REPO --approve --body 'AI Review: APPROVED. <brief summary of what was reviewed and why it passes>'
- Leave a handoff comment on the issue:
  gh issue comment $issue_num --repo $REPO --body '**Reviewer Handoff (APPROVED):**

  **What was reviewed:**
  - <files examined, tests verified>
  
  **Verdict:** Code correctly implements the ticket requirements and aligns with project vision.
  
  **Notes for future work:**
  - <any observations, potential improvements, or related areas to watch>'
- If you identified follow-up work during the review (edge cases not covered, related areas needing attention, tech debt introduced, documentation gaps, etc.), create a ticket for EACH follow-up item:
  gh issue create --repo $REPO --title '<descriptive title>' --label '<bug|enhancement>' --label 'priority: <high|medium|low>' --body '<description referencing the original issue #$issue_num and explaining what needs to happen next>'
  NEVER use 'priority: critical' — reserved for humans.
  Then add each to the project board: gh project item-add $PROJECT_NUM --owner $PROJECT_OWNER --url <issue_url>
- Then output exactly: REVIEW_RESULT=APPROVED

IF THE CODE FAILS REVIEW:
- Run: gh pr review $pr_num --repo $REPO --request-changes --body 'AI Review: CHANGES REQUESTED.\n\n<detailed list of issues found, with file names and line numbers>\n\nPlease address these issues and re-request review.'
- Leave a handoff comment on the issue:
  gh issue comment $issue_num --repo $REPO --body '**Reviewer Handoff (CHANGES REQUESTED):**

  **What was reviewed:**
  - <files examined, tests verified>
  
  **Issues found:**
  - <numbered list of specific problems with file:line references>
  
  **What the next developer should do:**
  - <clear actionable steps to fix each issue>
  
  **What NOT to change:**
  - <parts of the implementation that are correct and should be preserved>'
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
# Phase 3b: Planning — review tickets returned from dev validation
# ---------------------------------------------------------------------------
phase_planning() {
    local planning_issues
    planning_issues=$(issues_by_status "Planning")

    if [[ -z "$planning_issues" ]]; then
        return
    fi

    while IFS= read -r issue_num; do
        [[ -z "$issue_num" ]] && continue
        check_stop

        local title
        title=$(get_issue_title "$issue_num")
        local body
        body=$(get_issue_body "$issue_num")
        local comments
        comments=$(gh issue view "$issue_num" --repo "$REPO" --json comments -q '[.comments[-3:][].body] | join("\n---\n")' 2>/dev/null)
        local planning_log="$LOG_DIR/planning-${issue_num}-$(date +%s).log"

        log "  📐 Planning review for #$issue_num: $title"

        claude --dangerously-skip-permissions -p "You are a technical planner reviewing a ticket that was returned from development validation.

PROJECT ROOT: $PROJECT_ROOT
REPO: $REPO
ISSUE #$issue_num: $title

ISSUE BODY:
$body

RECENT COMMENTS (developer feedback):
$comments

Your task:
1. Read the developer's feedback in the comments
2. Examine the current codebase to understand the context
3. Decide one of three outcomes:

OPTION A — CLOSE: The issue is genuinely not needed. Close it.
  - Run: gh issue comment $issue_num --repo $REPO --body 'Planning Review: Confirmed this issue is not needed. <reason>'
  - Run: gh issue close $issue_num --repo $REPO
  - Output: PLANNING_RESULT=CLOSED

OPTION B — REVISE AND RETURN: The issue is valid but needs clarification. Update it and send back.
  - Run: gh issue edit $issue_num --repo $REPO --body '<revised body with clearer requirements, acceptance criteria, and implementation hints>'
  - Run: gh issue comment $issue_num --repo $REPO --body '**Planner Handoff (REVISED):**
  
    **What changed:**
    - <list of clarifications, added acceptance criteria, etc.>
    
    **What the developer should do:**
    - <specific implementation guidance>
    
    **Key decisions made:**
    - <architectural choices, scope decisions>'
  - Output: PLANNING_RESULT=REVISED

OPTION C — ESCALATE: The issue requires human architectural decision.
  - Run: gh issue comment $issue_num --repo $REPO --body '**Planner Handoff (ESCALATE):**
  
    **Why this needs human input:**
    - <specific questions or decisions needed>
    
    **Options considered:**
    - <tradeoffs analyzed>
    
    **Recommendation:**
    - <what the planner would suggest, if any>'
  - Output: PLANNING_RESULT=ESCALATE

Output the verdict as the LAST line." \
            --output-format text \
            > "$planning_log" 2>&1

        if grep -q "PLANNING_RESULT=CLOSED" "$planning_log"; then
            log "  🗑️  #$issue_num closed by planner"
            set_status "$issue_num" "$STATUS_DONE"
        elif grep -q "PLANNING_RESULT=REVISED" "$planning_log"; then
            log "  📝 #$issue_num revised — returning to Todo"
            set_status "$issue_num" "$STATUS_TODO"
        elif grep -q "PLANNING_RESULT=ESCALATE" "$planning_log"; then
            log "  🚨 #$issue_num needs human input — moving to Need Human"
            set_status "$issue_num" "$STATUS_NEED_HUMAN"
            openclaw system event --text "📐 Dev Loop Planning Escalation: Issue #$issue_num ($title) needs human architectural input. See: https://github.com/$REPO/issues/$issue_num" --mode now 2>/dev/null || true
        else
            log "  ⚠️  Planning result unclear for #$issue_num — check log: $planning_log"
        fi
    done <<< "$planning_issues"
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
            # Only promote if PR is no longer a draft (agent marked it ready)
            local is_draft
            is_draft=$(gh pr view "$pr_num" --repo "$REPO" --json isDraft -q '.isDraft' 2>/dev/null)

            if [[ "$is_draft" == "false" ]]; then
                log "  📤 PR #$pr_num is ready for review — promoting #$issue_num to AI Review"
                set_status "$issue_num" "$STATUS_AI_REVIEW"
            else
                log "  ⏳ PR #$pr_num for #$issue_num is still a draft — waiting"
            fi
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
        cycle=$(( cycle + 1 ))
        log ""
        log "═══════════════ Cycle $cycle ═══════════════"

        # Clean up dead PIDs
        clean_pids

        # Clean dead PIDs first, then check if any are still alive
        clean_pids
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

        # Phase 3b: Handle tickets returned to Planning
        check_shutdown
        phase_planning

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

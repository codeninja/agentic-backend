#!/usr/bin/env bash
# =============================================================================
# Implement agent — pick Todo/Rejected tickets, spawn developers
# =============================================================================

_spawn_implement_agent() {
    local issue_num="$1" title="$2" body="$3" branch="$4" worktree="$5" draft_pr="$6" impl_log="$7"

    claude --dangerously-skip-permissions -p "You are a developer assigned to GitHub issue #$issue_num in the NinjaStack project.

ISSUE TITLE: $title

ISSUE BODY:
$body

WORKING DIRECTORY: $worktree
BRANCH: $branch
DRAFT PR: #$draft_pr (already created)
REPO: $REPO

## PHASE 0: SYNC WITH MAIN
Before anything else, ensure your branch is up to date:
1. cd $worktree
2. git fetch origin main
3. git rebase origin/main (if conflicts, abort and output RESULT=NEEDS_PLANNING)
4. Verify with: git log --oneline origin/main..HEAD

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
- Stop here.

If the issue NEEDS CLARIFICATION:
- Run: gh issue comment $issue_num --repo $REPO --body 'Dev Validation: This ticket needs further planning. <explanation>'
- Run: gh pr close $draft_pr --repo $REPO --delete-branch
- Output: RESULT=NEEDS_PLANNING
- Stop here.

If the issue is VALID, continue to Phase 2.

## PHASE 2: IMPLEMENTATION

QUALITY STANDARDS — NON-NEGOTIABLE:
- Write PRODUCTION-QUALITY code. No stubs, no mocks-as-implementation, no TODO placeholders.
- Every public function must have docstrings. Every edge case mentioned in the issue must be handled.
- Do not introduce workarounds or hacks. Solve the root problem.
- If you cannot implement the full solution properly, output RESULT=NEEDS_PLANNING rather than shipping incomplete work.

1. Read the issue carefully and understand the requirements
2. Read relevant source files to understand the current implementation
3. Implement the fix/feature as described in the issue
4. Write or update tests to cover your changes
5. Run the test suite: cd $worktree && uv sync && uv run pytest --tb=short
6. Ensure ALL tests pass
7. Commit: git add -A && git commit -m 'fix: <description> (closes #$issue_num)'
8. Push: git push origin $branch
9. Update PR body: gh pr edit $draft_pr --repo $REPO --body 'Closes #$issue_num\n\n<summary of changes>'
10. Mark PR ready: gh pr ready $draft_pr --repo $REPO
11. Leave a handoff comment:
    gh issue comment $issue_num --repo $REPO --body '**Developer Handoff:**

    **What was done:**
    - <changes made, files modified>

    **Tests:**
    - <test results summary>

    **What the reviewer should check:**
    - <areas of concern, edge cases>'
12. Output: RESULT=IMPLEMENTED

IMPORTANT:
- A draft PR already exists — do NOT create a new one
- Do NOT merge the PR — it needs review first
- Keep changes focused on the issue scope" \
        --output-format text \
        > "$impl_log" 2>&1

    # Parse result
    if grep -q "RESULT=IMPLEMENTED" "$impl_log"; then
        log "[implement] ✅ #$issue_num implemented — awaiting promotion to AI Review"
    elif grep -q "RESULT=UNNECESSARY" "$impl_log"; then
        log "[implement] 🗑️  #$issue_num already resolved — closed"
        set_status "$issue_num" "Done"
        cleanup_worktree "$worktree"
    elif grep -q "RESULT=NEEDS_PLANNING" "$impl_log"; then
        log "[implement] 📐 #$issue_num needs planning"
        set_status "$issue_num" "Planning"
        cleanup_worktree "$worktree"
    else
        log "[implement] ⚠️  Result unclear for #$issue_num — check $impl_log"
    fi
}

loop_implement() {
    while check_loop_stop; do
        wait_for_rate_limit "implement" || return
        local active
        active=$(count_active_agents "implement")
        if (( active >= MAX_IMPLEMENT_AGENTS )); then
            log "[implement] ⏳ All implement agents busy ($active/$MAX_IMPLEMENT_AGENTS)"
            sleep 60; continue
        fi

        # Prioritize rejected tickets first, then todo sorted by priority
        local rejected_issues todo_issues all_issues
        rejected_issues=$(issues_by_status "Rejected")
        todo_issues=$(get_prioritized_todo_issues)
        all_issues=$(echo -e "${rejected_issues}\n${todo_issues}" | grep -v '^$')

        if [[ -z "$all_issues" ]]; then
            log "[implement] 💤 No issues to implement"
            sleep 60; continue
        fi

        local slots=$(( MAX_IMPLEMENT_AGENTS - active ))
        local count=0

        while IFS= read -r issue_num; do
            [[ -z "$issue_num" ]] && continue
            (( count >= slots )) && break
            check_loop_stop || return

            # Skip if worktree already exists
            if [[ -d "$WORKTREE_BASE/issue-${issue_num}" ]]; then
                continue
            fi

            # Get context from board cache
            local ctx title body branch worktree impl_log
            ctx=$(get_issue_context "$issue_num")
            title=$(echo "$ctx" | python3 -c "import json,sys; print(json.load(sys.stdin).get('title',''))" 2>/dev/null)
            body=$(echo "$ctx" | python3 -c "import json,sys; print(json.load(sys.stdin).get('body',''))" 2>/dev/null)
            branch="fix/issue-${issue_num}"
            worktree="$WORKTREE_BASE/issue-${issue_num}"
            impl_log="$LOG_DIR/impl-${issue_num}-$(date +%s).log"

            log "[implement] 🚀 Starting developer for #$issue_num: $title"
            set_status "$issue_num" "In Progress"

            # Create worktree and draft PR
            create_implement_worktree "$issue_num" "$branch" "$worktree"
            local draft_pr
            draft_pr=$(get_pr_for_branch "$branch")
            log "[implement] 📝 Draft PR #$draft_pr for #$issue_num"

            _spawn_implement_agent "$issue_num" "$title" "$body" "$branch" "$worktree" "$draft_pr" "$impl_log" &
            track_agent_pid "implement" $!
            count=$(( count + 1 ))
        done <<< "$all_issues"

        sleep 60
    done
}

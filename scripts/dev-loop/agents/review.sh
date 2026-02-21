#!/usr/bin/env bash
# =============================================================================
# Review agent — AI code review of PRs
# =============================================================================

_spawn_review_agent() {
    local issue_num="$1" title="$2" body="$3" pr_num="$4" branch="$5" review_dir="$6" review_log="$7"

    claude --dangerously-skip-permissions -p "You are a code reviewer for the NinjaStack project.

ISSUE #$issue_num: $title

ISSUE BODY:
$body

PR #$pr_num on branch: $branch
REVIEW DIRECTORY: $review_dir

PROJECT VISION:
NinjaStack is a schema-first agentic backend framework. Key principles: explicit > implicit, composition > inheritance, constraints > convention, model-agnostic via LiteLLM.

Your task:
1. Run: cd $review_dir && git log --oneline origin/main..HEAD
2. Run: cd $review_dir && git diff origin/main...HEAD --stat
3. Review ALL changed files — ONLY evaluate changes introduced by this branch
4. Run tests: uv sync && uv run pytest --tb=short
5. Evaluate:
   a. Does the code correctly implement what the issue describes?
   b. Are there tests covering the changes?
   c. Do all tests pass?
   d. Is the code consistent with the project's architecture?
   e. Are there security concerns?

VIOLATIONS:
- Missing requirements, failing tests, security issues → CHANGES REQUESTED
- Workaround instead of root fix → HUMAN REVIEW NEEDED

IF APPROVED:
- Run: gh pr review $pr_num --repo $REPO --approve --body 'AI Review: APPROVED. <summary>'
- Leave a handoff comment on the issue
- If follow-up work identified, create tickets:
  gh issue create --repo $REPO --title '<title>' --label '<bug|enhancement>' --label 'triage' --label 'priority: <high|medium|low>' --body '<description referencing #$issue_num>'
  NEVER use 'priority: critical' — reserved for humans.
  Then add each to the project board AND set status to Triage:
    ITEM_ID=\$(gh project item-add $PROJECT_NUM --owner $PROJECT_OWNER --url <issue_url> --format json | jq -r '.id')
    gh api graphql -f query='mutation { updateProjectV2ItemFieldValue(input: { projectId: \"$PROJECT_ID\", itemId: \"'\"\$ITEM_ID\"'\", fieldId: \"$FIELD_ID\", value: { singleSelectOptionId: \"$STATUS_TRIAGE\" } }) { projectV2Item { id } } }'
- Output exactly: REVIEW_RESULT=APPROVED

IF REJECTED:
- Run: gh pr review $pr_num --repo $REPO --request-changes --body 'AI Review: CHANGES REQUESTED.\n\n<issues found>'
- Leave a handoff comment with specific fixes needed
- Output exactly: REVIEW_RESULT=REJECTED

Be thorough but fair. Only reject for real issues, not style preferences." \
        --output-format text \
        > "$review_log" 2>&1

    if grep -q "REVIEW_RESULT=APPROVED" "$review_log"; then
        log "[review] ✅ PR #$pr_num APPROVED — merging"
        gh pr merge "$pr_num" --repo "$REPO" --squash --delete-branch 2>/dev/null || true
        set_status "$issue_num" "Done"
        cleanup_worktree "$review_dir"
        cleanup_worktree "$WORKTREE_BASE/issue-${issue_num}"
    elif grep -q "REVIEW_RESULT=REJECTED" "$review_log"; then
        record_bounce "$issue_num"
        local bounces
        bounces=$(get_bounce_count "$issue_num")
        if (( bounces >= MAX_BOUNCES )); then
            escalate_to_human "$issue_num" "$title" "$bounces"
        else
            log "[review] ❌ PR #$pr_num REJECTED (bounce $bounces/$MAX_BOUNCES) → Rejected"
            set_status "$issue_num" "Rejected"
        fi
        cleanup_worktree "$review_dir"
    else
        log "[review] ⚠️  Result unclear for #$issue_num — check $review_log"
    fi
}

loop_review() {
    while check_loop_stop; do
        wait_for_rate_limit "review" || return
        local active
        active=$(count_active_agents "review")
        if (( active >= MAX_REVIEW_AGENTS )); then
            sleep 60; continue
        fi

        local review_issues
        review_issues=$(issues_by_status "AI Review")
        if [[ -z "$review_issues" ]]; then
            sleep 60; continue
        fi

        local slots=$(( MAX_REVIEW_AGENTS - active ))
        local count=0

        while IFS= read -r issue_num; do
            [[ -z "$issue_num" ]] && continue
            (( count >= slots )) && break
            check_loop_stop || return

            # Get context from board cache
            local ctx title body branch pr_num
            ctx=$(get_issue_context "$issue_num")
            title=$(echo "$ctx" | python3 -c "import json,sys; print(json.load(sys.stdin).get('title',''))" 2>/dev/null)
            body=$(echo "$ctx" | python3 -c "import json,sys; print(json.load(sys.stdin).get('body',''))" 2>/dev/null)
            branch="fix/issue-${issue_num}"
            pr_num=$(get_pr_for_branch "$branch")

            if [[ -z "$pr_num" ]]; then
                log "[review] ⚠️  No PR for #$issue_num (branch $branch), skipping"
                continue
            fi

            local review_dir="$WORKTREE_BASE/review-${issue_num}"
            local review_log="$LOG_DIR/review-${issue_num}-$(date +%s).log"

            log "[review] 🔎 Reviewing PR #$pr_num for #$issue_num: $title"

            # Create fresh worktree for review
            create_review_worktree "$issue_num" "$branch" "$review_dir"

            _spawn_review_agent "$issue_num" "$title" "$body" "$pr_num" "$branch" "$review_dir" "$review_log" &
            track_agent_pid "review" $!
            count=$(( count + 1 ))
        done <<< "$review_issues"

        sleep 60
    done
}

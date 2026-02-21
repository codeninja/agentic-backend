#!/usr/bin/env bash
# =============================================================================
# Planning agent — design work for complex issues
# =============================================================================

_spawn_planning_agent() {
    local issue_num="$1" title="$2" body="$3" comments="$4" planning_log="$5"

    claude --dangerously-skip-permissions -p "You are a technical planner for the NinjaStack project.

PROJECT ROOT: $PROJECT_ROOT
REPO: $REPO
ISSUE #$issue_num: $title

ISSUE BODY:
$body

RECENT COMMENTS (context from triage or developer feedback):
$comments

Your task:
1. Read the comments for context (triage analysis or developer feedback)
2. Examine the current codebase to understand the context
3. Decide one of three outcomes:

OPTION A — CLOSE: The issue is genuinely not needed.
  - Run: gh issue comment $issue_num --repo $REPO --body 'Planning Review: Confirmed this issue is not needed. <reason>'
  - Run: gh issue close $issue_num --repo $REPO
  - Output: PLANNING_RESULT=CLOSED

OPTION B — REVISE AND RETURN: The issue is valid but needs clarification. Update it and send back.
  - Run: gh issue edit $issue_num --repo $REPO --body '<revised body with clearer requirements, acceptance criteria, and implementation hints>'
  - Run: gh issue comment $issue_num --repo $REPO --body '**Planner Handoff (REVISED):**

    **What changed:**
    - <list of clarifications, added acceptance criteria>

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
    - <what the planner would suggest>'
  - Output: PLANNING_RESULT=ESCALATE

Output the verdict as the LAST line." \
        --output-format text \
        > "$planning_log" 2>&1

    if grep -q "PLANNING_RESULT=CLOSED" "$planning_log"; then
        log "[planning] 🗑️  #$issue_num closed"
        set_status "$issue_num" "Done"
    elif grep -q "PLANNING_RESULT=REVISED" "$planning_log"; then
        log "[planning] 📝 #$issue_num revised → Todo"
        set_status "$issue_num" "Todo"
    elif grep -q "PLANNING_RESULT=ESCALATE" "$planning_log"; then
        log "[planning] 🚨 #$issue_num → Need Human"
        set_status "$issue_num" "Need Human"
        openclaw system event --text "📐 Dev Loop Planning Escalation: Issue #$issue_num ($title) needs human input. See: https://github.com/$REPO/issues/$issue_num" --mode now 2>/dev/null || true
    else
        log "[planning] ⚠️  Result unclear for #$issue_num — check $planning_log"
    fi
}

loop_planning() {
    while check_loop_stop; do
        wait_for_rate_limit "planning" || return
        local active
        active=$(count_active_agents "planning")
        if (( active >= MAX_PLANNING_AGENTS )); then
            log "[planning] ⏳ All planning agents busy ($active/$MAX_PLANNING_AGENTS)"
            sleep 60; continue
        fi

        local planning_issues
        planning_issues=$(issues_by_status "Planning")
        if [[ -z "$planning_issues" ]]; then
            log "[planning] 💤 No issues in Planning"
            sleep 60; continue
        fi

        local slots=$(( MAX_PLANNING_AGENTS - active ))
        local count=0

        while IFS= read -r issue_num; do
            [[ -z "$issue_num" ]] && continue
            (( count >= slots )) && break
            check_loop_stop || return

            # Get context from board cache
            local ctx title body comments
            ctx=$(get_issue_context "$issue_num")
            title=$(echo "$ctx" | python3 -c "import json,sys; print(json.load(sys.stdin).get('title',''))" 2>/dev/null)
            body=$(echo "$ctx" | python3 -c "import json,sys; print(json.load(sys.stdin).get('body',''))" 2>/dev/null)
            comments=$(echo "$ctx" | python3 -c "
import json,sys
d = json.load(sys.stdin)
cs = d.get('comments', [])[-3:]
print('\n---\n'.join(c.get('body','') for c in cs))
" 2>/dev/null)
            local planning_log="$LOG_DIR/planning-${issue_num}-$(date +%s).log"

            log "[planning] 📐 Planning #$issue_num: $title"

            _spawn_planning_agent "$issue_num" "$title" "$body" "$comments" "$planning_log" &
            track_agent_pid "planning" $!
            count=$(( count + 1 ))
        done <<< "$planning_issues"

        sleep 60
    done
}

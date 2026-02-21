#!/usr/bin/env bash
# =============================================================================
# Triage agent — categorize and route new issues
# =============================================================================

_spawn_triage_agent() {
    local issue_num="$1" title="$2" body="$3" labels="$4" triage_log="$5"

    claude --dangerously-skip-permissions -p "You are a triage agent for the NinjaStack project.

PROJECT ROOT: $PROJECT_ROOT
REPO: $REPO

ISSUE #$issue_num: $title

ISSUE BODY:
$body

CURRENT LABELS: $labels

Your task: Read this issue, examine the relevant codebase, and make a triage decision.

## STEP 1: UNDERSTAND THE ISSUE
Read the issue title and body carefully. Determine:
- Is this a bug report, feature request, enhancement, refactoring task, or documentation gap?
- Is it clearly written with enough detail to act on?
- Does it reference specific files, modules, or behaviors?

## STEP 2: EXAMINE THE CODEBASE
1. Read CLAUDE.md at $PROJECT_ROOT to understand the project architecture
2. If the issue references specific files or modules, read them
3. Search the codebase for keywords from the issue to find related code
4. Check for duplicates using the board context already available.

## STEP 3: CATEGORIZE AND PRIORITIZE
Assign a category label (if not already present):
- 'bug' for defects, 'enhancement' for improvements, 'security' for security issues

Assign a priority label (if not already present):
- 'priority: high' — broken functionality, security issues, blocks other work
- 'priority: medium' — important but not urgent
- 'priority: low' — nice-to-have, polish
- NEVER assign 'priority: critical' — reserved for humans

Apply labels:
  gh issue edit $issue_num --repo $REPO --add-label '<category>' --add-label 'priority: <level>'

Remove the triage label once categorized:
  gh issue edit $issue_num --repo $REPO --remove-label 'triage'

## STEP 4: DECIDE DESTINATION

### OPTION A — TODO (ready for implementation)
The issue is clear, actionable, and scoped. A developer can pick it up immediately.
- Ensure the issue body has clear acceptance criteria. If missing, edit the issue to add them.
- Leave a triage comment:
  gh issue comment $issue_num --repo $REPO --body '**Triage Analysis:**

  **Category:** <bug/enhancement/security/etc.>
  **Priority:** <high/medium/low> — <justification>
  **Affected area:** <libs/ninja-X, apps/ninja-Y>
  **Relevant files:** <key files>

  **Assessment:** <what the issue is and why this priority>

  **Implementation hints:**
  - <suggestion 1>
  - <suggestion 2>

  **Ready for development.**'
- Output: TRIAGE_RESULT=TODO

### OPTION B — PLANNING (needs architectural planning)
The issue is valid but needs design work before implementation.
- Leave a triage comment explaining why it needs planning and what the planner should decide
- Output: TRIAGE_RESULT=PLANNING

### OPTION C — NEED HUMAN (requires human decision)
The issue involves product direction, breaking API changes, or decisions outside AI scope.
- Leave a comment explaining why human input is needed
- Run: gh issue edit $issue_num --repo $REPO --add-label 'needs-human'
- Output: TRIAGE_RESULT=NEED_HUMAN

### OPTION D — CLOSE (invalid, duplicate, or already resolved)
- Leave a comment explaining the closure reason, reference the duplicate if applicable
- Run: gh issue close $issue_num --repo $REPO --reason '<not_planned|completed|duplicate>'
- Output: TRIAGE_RESULT=CLOSED

## RULES
- Always examine the actual code, not just the issue description
- Be conservative with CLOSE — when in doubt, send to PLANNING
- Preserve the original issue body when adding acceptance criteria
- Your output MUST end with exactly one of: TRIAGE_RESULT=TODO, TRIAGE_RESULT=PLANNING, TRIAGE_RESULT=NEED_HUMAN, or TRIAGE_RESULT=CLOSED" \
        --output-format text \
        > "$triage_log" 2>&1

    # Parse result and update board
    if grep -q "TRIAGE_RESULT=TODO" "$triage_log"; then
        log "[triage] ✅ #$issue_num → Todo"
        set_status "$issue_num" "Todo"
    elif grep -q "TRIAGE_RESULT=PLANNING" "$triage_log"; then
        log "[triage] 📐 #$issue_num → Planning"
        set_status "$issue_num" "Planning"
    elif grep -q "TRIAGE_RESULT=NEED_HUMAN" "$triage_log"; then
        log "[triage] 🚨 #$issue_num → Need Human"
        set_status "$issue_num" "Need Human"
    elif grep -q "TRIAGE_RESULT=CLOSED" "$triage_log"; then
        log "[triage] 🗑️  #$issue_num closed"
        set_status "$issue_num" "Done"
    else
        log "[triage] ⚠️  Result unclear for #$issue_num — check $triage_log"
    fi
}

loop_triage() {
    while check_loop_stop; do
        wait_for_rate_limit "triage" || return
        local active
        active=$(count_active_agents "triage")
        if (( active >= MAX_TRIAGE_AGENTS )); then
            log "[triage] ⏳ All triage agents busy ($active/$MAX_TRIAGE_AGENTS)"
            sleep 60; continue
        fi

        local triage_issues
        triage_issues=$(issues_by_status "Triage")
        if [[ -z "$triage_issues" ]]; then
            log "[triage] 💤 No issues in Triage"
            sleep 60; continue
        fi

        local slots=$(( MAX_TRIAGE_AGENTS - active ))
        local count=0

        while IFS= read -r issue_num; do
            [[ -z "$issue_num" ]] && continue
            (( count >= slots )) && break
            check_loop_stop || return

            # Get all context from board cache (0 API calls)
            local ctx title body labels
            ctx=$(get_issue_context "$issue_num")
            title=$(echo "$ctx" | python3 -c "import json,sys; print(json.load(sys.stdin).get('title',''))" 2>/dev/null)
            body=$(echo "$ctx" | python3 -c "import json,sys; print(json.load(sys.stdin).get('body',''))" 2>/dev/null)
            labels=$(echo "$ctx" | python3 -c "import json,sys; print(','.join(json.load(sys.stdin).get('labels',[])))" 2>/dev/null)
            local triage_log="$LOG_DIR/triage-${issue_num}-$(date +%s).log"

            log "[triage] 🔍 Triaging #$issue_num: $title"

            _spawn_triage_agent "$issue_num" "$title" "$body" "$labels" "$triage_log" &
            track_agent_pid "triage" $!
            count=$(( count + 1 ))
        done <<< "$triage_issues"

        sleep 60
    done
}
